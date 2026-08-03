from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.db.models import Sum
from django.utils import timezone
from django.conf import settings
from pathlib import Path
import threading
import logging
import json
import re
import shutil
import subprocess
import sys
import time

# Import your models
from .models import Project, AnalysisJob

# knowledge_base is the ONLY interface to parser data. It links the parser's
# (global) PostgreSQL output to this app's Project / AnalysisJob / User
# records (write path) and exposes all project-scoped reads; nothing here
# ever touches parser tables or SQL directly.
from . import knowledge_base

# llm_service is the ONLY Django <-> LLM interface. The project_ask API below
# reuses it rather than calling any provider (Gemini) directly.
from . import llm_service

logger = logging.getLogger(__name__)


class CloneError(Exception):
    """Raised when `git clone` fails (non-zero exit, timeout, or missing git)."""

def home(request):
    return render(request, 'analyzer/home.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember')

        # Authenticate using email (since we are using email as username)
        try:
            user_obj = User.objects.get(email=email)
            username = user_obj.username
        except User.DoesNotExist:
            # Use a dummy username to avoid user enumeration
            username = None

        if username is None:
            # Simulate failed authentication to prevent timing attacks
            user = None
        else:
            user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            # Set session expiry based on "Remember me"
            if not remember_me:
                # Session expires when browser closes
                request.session.set_expiry(0)
            else:
                # Session lasts for 2 weeks
                request.session.set_expiry(1209600)  # 2 weeks in seconds

            messages.success(request, f"Welcome back, {user.username}!")
            return redirect('analyzer:dashboard')
        else:
            messages.error(request, "Invalid email or password.")
            return render(request, 'analyzer/login.html')
    else:
        # If user is already authenticated, redirect to dashboard
        if request.user.is_authenticated:
            return redirect('analyzer:dashboard')
        return render(request, 'analyzer/login.html')

def signup_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        terms = request.POST.get('terms')  # Will be 'on' if checked

        # Basic validation
        if not name or not email or not password:
            messages.error(request, "Name, email, and password are required.")
            return render(request, 'analyzer/signup.html')

        if not terms:
            messages.error(request, "You must agree to the Terms of Service.")
            return render(request, 'analyzer/signup.html')

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, 'analyzer/signup.html')

        # Check if email already exists (since we'll use email as username)
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return render(request, 'analyzer/signup.html')

        # Create user with email as username
        user = User.objects.create_user(username=email, email=email, password=password)
        # Set first name to the provided name (optional)
        user.first_name = name
        user.save()

        # Log in the user
        login(request, user)
        messages.success(request, f"Account created successfully! Welcome, {user.username}.")
        return redirect('analyzer:dashboard')
    else:
        # If user is already authenticated, redirect to dashboard
        if request.user.is_authenticated:
            return redirect('analyzer:dashboard')
        # Ensure session is saved to get sessionid cookie for CSRF protection
        if not request.session.get('_csrf_dummy'):
            request.session['_csrf_dummy'] = True
            request.session.save()
        return render(request, 'analyzer/signup.html')

@login_required
def dashboard(request):
    # Optimized queries to prevent N+1
    user_projects = Project.objects.filter(owner=request.user).prefetch_related(
        'analysis_jobs'
    )
    project_count = user_projects.count()

    # Get completed analysis jobs count
    completed_jobs_count = AnalysisJob.objects.filter(
        project__owner=request.user, 
        status='completed'
    ).count()

    # Get total files analyzed across all projects
    total_files_analyzed = AnalysisJob.objects.filter(
        project__owner=request.user
    ).aggregate(total=Sum('files_analyzed'))['total'] or 0

    # Get the latest analysis job for each project (for the project cards)
    projects_with_status = []
    for project in user_projects:
        # Use prefetched jobs instead of making a new query
        latest_job = project.analysis_jobs.order_by('-created_at').first()
        projects_with_status.append({
            'project': project,
            'latest_job': latest_job
        })

    context = {
        'projects': user_projects,
        'projects_with_status': projects_with_status,
        'project_count': project_count,
        'completed_jobs_count': completed_jobs_count,
        'total_files_analyzed': total_files_analyzed,
    }
    return render(request, 'analyzer/dashboard.html', context)

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('analyzer:home')

@login_required
def add_project(request):
    if request.method == 'POST':
        # Extract form data
        project_name = request.POST.get('project-name', '').strip()
        repo_url = request.POST.get('repo-url', '').strip()
        branch = request.POST.get('branch', '').strip()
        description = request.POST.get('description', '').strip()

        # Validation flags
        is_valid = True

        # Project Name validation
        if not project_name:
            messages.error(request, "Project name is required.")
            is_valid = False

        # GitHub Repository URL validation
        if not repo_url:
            messages.error(request, "GitHub repository URL is required.")
            is_valid = False
        else:
            # Regex for HTTPS GitHub URL: https://github.com/user/repository(.git)?
            # Regex for SSH GitHub URL: git@github.com:user/repository.git
            https_pattern = r'^https://github.com/[^/]+/[^/]+(\.git)?/?$'
            ssh_pattern = r'^git@github.com:[^/]+/[^/]+\.git$'

            if not (re.match(https_pattern, repo_url) or re.match(ssh_pattern, repo_url)):
                messages.error(request, "Please enter a valid GitHub repository URL (HTTPS or SSH format).")
                is_valid = False

        # Branch validation (optional, default to main if empty)
        if not branch:
            branch = 'main'

        # Description is optional, no validation needed

        if is_valid:
            # Validation successful - save to database
            try:
                project = Project(
                    name=project_name,
                    description=description,
                    github_url=repo_url,
                    owner=request.user,
                    is_private=False,  # Assuming public repos only for now
                    analysis_status='pending'  # Set to pending as requested
                )
                project.save()

                logger.info("[STEP 1] Analysis requested")

                # Create the analysis job synchronously so the dashboard
                # immediately shows the pending state before the background
                # worker picks it up.
                analysis_job = AnalysisJob.objects.create(
                    project=project,
                    status='pending'
                )
                logger.info("Analysis Job created (id=%s)", analysis_job.id)

                # Start the background worker.
                # NOTE: For development this is a daemon thread. When moving to
                # production, this is the single seam to replace with Celery/RQ:
                #   run_repository_analysis.delay(analysis_job.id)
                analysis_thread = threading.Thread(
                    target=run_repository_analysis,
                    args=(analysis_job.id,),
                    daemon=True  # Allow thread to exit when main process ends
                )
                analysis_thread.start()
                logger.info("Background thread started")

                # Redirect to dashboard after successful save
                return redirect('analyzer:dashboard')
            except Exception as e:
                # If database saving fails, show error message
                logger.exception(f"Failed to save project: {str(e)}")
                messages.error(request, f"Failed to save project: {str(e)}")
                # Re-render the form to allow user to correct issues
                return render(request, 'analyzer/add_project.html')
    else:
        # GET request - just render the form
        return render(request, 'analyzer/add_project.html')

@login_required
def analyze_project(request, project_id):
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
        latest_job = project.analysis_jobs.order_by('-created_at').first()

        # Prepare data for template
        context = {
            'project': project,
            'latest_job': latest_job,
            'is_analyzing': latest_job and latest_job.status in ['pending', 'running'],
        }
        return render(request, 'analyzer/analyzing.html', context)
    except Project.DoesNotExist:
        logger.warning(f"Project {project_id} not found for user {request.user.id}")
        messages.error(request, "Project not found.")
        return redirect('analyzer:dashboard')

@login_required
def analyze_project_status(request, project_id):
    """AJAX endpoint to get analysis status"""
    if request.method == 'GET':
        try:
            project = Project.objects.get(id=project_id, owner=request.user)
            latest_job = project.analysis_jobs.order_by('-created_at').first()

            if latest_job:
                # Get logs as a list of non-empty lines, limited to last 100 lines
                log_lines = []
                if latest_job.logs:
                    log_lines = [line.strip() for line in latest_job.logs.split('\n') if line.strip()]
                    if len(log_lines) > 100:
                        log_lines = log_lines[-100:]
                data = {
                    'status': latest_job.status,
                    'progress': latest_job.progress,  # Now we have this field
                    'logs': log_lines,
                    'completed_at': latest_job.completed_at.isoformat() if latest_job.completed_at else None,
                }
            else:
                data = {
                    'status': 'no_job',
                    'progress': 0,
                    'logs': [],
                    'completed_at': None,
                }

            return JsonResponse(data)
        except Project.DoesNotExist:
            logger.warning(f"Project {project_id} not found for status check")
            return JsonResponse({'error': 'Project not found'}, status=404)

    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@require_http_methods(["POST"])
def delete_project(request, project_id):
    """Delete a project and its analysis jobs.
    Ownership is verified so users can only delete their own projects.
    """
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
        project_name = project.name
        project.delete()  # AnalysisJobs cascade via the FK relationship
        messages.success(request, f"Project '{project_name}' deleted successfully.")
        logger.info(f"User {request.user.id} deleted project {project_id}")
    except Project.DoesNotExist:
        logger.warning(f"Delete denied: project {project_id} not found for user {request.user.id}")
        messages.error(request, "Project not found.")
    return redirect('analyzer:dashboard')

def _mark_job_failed(analysis_job_id, message):
    """Mark an AnalysisJob and its project as failed with a log message."""
    try:
        analysis_job = AnalysisJob.objects.get(id=analysis_job_id)
        analysis_job.status = 'failed'
        analysis_job.completed_at = timezone.now()
        analysis_job.progress = 0
        analysis_job.logs = message
        analysis_job.save()

        project = analysis_job.project
        project.analysis_status = 'failed'
        project.save()
    except Exception:
        logger.exception(f"Error while marking job {analysis_job_id} as failed")


def run_repository_analysis(analysis_job_id):
    """Background worker: clone the repository, then run the existing parser.

    Pipeline: pending -> cloning -> processing -> completed/failed.

    After a successful `git clone` into media/repos/<project_id>/, the
    existing parser (repo_parser.py) is invoked through its intended entry
    point for an already-local repository:

        python repo_parser.py --repo-path <clone_dir>

    The parser is reused exactly as-is — it is NOT rewritten, duplicated, or
    modified here. It connects to PostgreSQL itself (via its own DB_CONFIG /
    DB_* env vars) and stores its output there; this worker only waits for it,
    records the outcome, and then links that output to this project/job via
    knowledge_base (so Django can later retrieve only this project's data).

    This is the ONLY seam that changes when a real worker replaces the
    thread. To migrate to Celery/RQ later:
      1. Move this function into a tasks module (e.g. analyzer/tasks.py).
      2. Decorate with @shared_task (Celery) / @job (RQ) / @task (Dramatiq).
      3. In add_project, replace the threading.Thread(...) block with
         run_repository_analysis.delay(analysis_job.id).

    No AI, no embeddings, and no parser-output storage is implemented here.
    """
    try:
        analysis_job = AnalysisJob.objects.get(id=analysis_job_id)
        project = analysis_job.project

        # ---------------- Clone phase: pending -> cloning ----------------
        analysis_job.status = 'cloning'
        analysis_job.started_at = timezone.now()
        analysis_job.progress = 10
        analysis_job.save()

        project.analysis_status = 'cloning'
        project.save()

        log_lines = []

        clone_dir = Path(settings.MEDIA_ROOT) / 'repos' / str(project.id)
        if clone_dir.exists():
            # Safe re-clone: remove any previous clone for this project.
            shutil.rmtree(clone_dir)
        clone_dir.mkdir(parents=True, exist_ok=True)

        # Real clone via the system git binary.
        # NOTE: shallow single-branch clone keeps big repos fast; drop the
        # flags if a later phase needs full history.
        clone_result = subprocess.run(
            ['git', 'clone', '--depth', '1', '--single-branch',
             project.github_url, str(clone_dir)],
            capture_output=True,
            text=True,
            timeout=300,  # bail out of a hung clone
        )

        if clone_result.returncode != 0:
            error_msg = (clone_result.stderr or clone_result.stdout or 'git clone failed').strip()
            raise CloneError(f"git clone failed: {error_msg}")

        log_lines.append("[STEP 2] Repository cloned")
        logger.info("[STEP 2] Repository cloned (job id=%s)", analysis_job_id)
        logger.info("Clone location: %s", clone_dir)

        # ---------------- Parser phase: cloning -> processing ----------------
        analysis_job.status = 'processing'
        analysis_job.progress = 30
        analysis_job.save()

        project.analysis_status = 'processing'
        project.save()

        # Path to the existing parser (repo_parser.py sits next to the project root).
        parser_path = Path(settings.BASE_DIR).parent / 'repo_parser.py'
        if not parser_path.exists():
            raise CloneError(f"Parser not found at {parser_path}")

        log_lines.append("[STEP 3] Starting parser")
        logger.info("[STEP 3] Starting parser (job id=%s)", analysis_job_id)
        logger.info("Parser entry point: %s", parser_path)
        logger.info("Repository path passed to parser: %s", clone_dir)

        logger.info("Parser execution started (job id=%s)", analysis_job_id)

        # Invoke the existing parser on the already-cloned repository.
        # sys.executable ensures the parser runs with the same interpreter as
        # Django (the project venv), which has pygit2/tree-sitter/psycopg2.
        start_time = time.monotonic()
        try:
            parser_result = subprocess.run(
                [sys.executable, str(parser_path), '--repo-path', str(clone_dir)],
                capture_output=True,
                text=True,
                timeout=600,  # generous cap; bail out of a hung parser
            )
            elapsed = time.monotonic() - start_time
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start_time
            log_lines.append("[STEP 4] Parser failed")
            log_lines.append(f"Parser entry point: {parser_path}")
            log_lines.append(f"Repository path passed to parser: {clone_dir}")
            log_lines.append(f"Parser execution time: {elapsed:.2f}s")
            log_lines.append("Error: parser timed out after 600s")
            logger.error("[STEP 4] Parser failed (job id=%s): timed out after 600s", analysis_job_id)
            _mark_job_failed(analysis_job_id, "\n".join(log_lines))
            return

        if parser_result.returncode != 0:
            error_msg = (parser_result.stderr or parser_result.stdout or 'parser failed').strip()
            log_lines.append("[STEP 4] Parser failed")
            log_lines.append(f"Parser entry point: {parser_path}")
            log_lines.append(f"Repository path passed to parser: {clone_dir}")
            log_lines.append(f"Parser execution time: {elapsed:.2f}s")
            log_lines.append(f"Exit code: {parser_result.returncode}")
            log_lines.append(f"Error: {error_msg[:2000]}")
            logger.error("[STEP 4] Parser failed (job id=%s): %s", analysis_job_id, error_msg)
            _mark_job_failed(analysis_job_id, "\n".join(log_lines))
            return

        # ---------------- Link parser output to Project + AnalysisJob ----
        # The parser wrote globally; associate every row under this project's
        # clone directory with this project and job before serving it back.
        logger.info("Parser execution completed (job id=%s)", analysis_job_id)
        try:
            linked = knowledge_base.link_project_output(
                project.id, analysis_job_id, clone_dir,
            )
        except Exception as e:
            # The parse succeeded, but without linkage this project's data
            # cannot be scoped and would leak into other projects' queries.
            # Treat it as a failure so no unlinked (global) data is served.
            logger.exception("Linkage failed for project %s: %s", project.id, e)
            log_lines.append("[STEP 4] Parser completed but linking output to the project failed")
            log_lines.append(f"Error: {e}")
            _mark_job_failed(analysis_job_id, "\n".join(log_lines))
            return

        logger.info("Project linked successfully (project id=%s)", project.id)
        logger.info("AnalysisJob linked successfully (job id=%s)", analysis_job_id)
        logger.info("Files linked: %s", linked['files_linked'])
        logger.info("Entities linked: %s", linked['entities_linked'])
        logger.info("Relationships linked: %s", linked['relationships_linked'])

        # ---------------- processing -> completed ----------------
        log_lines.append("[STEP 4] Parser completed successfully")
        log_lines.append(f"Parser entry point: {parser_path}")
        log_lines.append(f"Repository path passed to parser: {clone_dir}")
        log_lines.append(f"Parser execution time: {elapsed:.2f}s")
        log_lines.append(f"Exit code: {parser_result.returncode}")

        analysis_job.status = 'completed'
        analysis_job.completed_at = timezone.now()
        analysis_job.progress = 100
        analysis_job.logs = "\n".join(log_lines)
        analysis_job.save()

        project.analysis_status = 'completed'
        project.last_analyzed = timezone.now()
        project.save()

        logger.info("[STEP 4] Parser completed successfully (job id=%s)", analysis_job_id)

    except (AnalysisJob.DoesNotExist, Project.DoesNotExist):
        logger.exception(f"AnalysisJob {analysis_job_id} (or its project) not found during analysis")
    except CloneError as e:
        logger.error("[STEP 4] Parser failed (job id=%s): %s", analysis_job_id, e)
        _mark_job_failed(analysis_job_id, f"Clone/parser failed: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during analysis of job {analysis_job_id}: {str(e)}")
        _mark_job_failed(analysis_job_id, f"Clone/parser failed: {str(e)}")

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def update_analysis_progress(request):
    """Endpoint for updating analysis progress (could be called by the analysis script)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            project_id = data.get('project_id')
            status = data.get('status')
            progress = data.get('progress', 0)
            logs = data.get('logs', [])

            project = Project.objects.get(id=project_id, owner=request.user)
            analysis_job = project.analysis_jobs.order_by('-created_at').first()

            if analysis_job:
                # Update fields
                if status:
                    analysis_job.status = status
                if progress is not None:
                    analysis_job.progress = progress
                # Note: For logs, we would need a separate model or storage mechanism
                analysis_job.save()
                logger.info(f"Updated analysis progress for project {project_id}: {status} {progress}%")
            else:
                logger.warning(f"No analysis job found for project {project_id}")

            return JsonResponse({'success': True})
        except json.JSONDecodeError as e:
            logger.exception(f"Invalid JSON in analysis progress update: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Project.DoesNotExist as e:
            logger.warning(f"Project {project_id} not found for progress update")
            return JsonResponse({'success': False, 'error': 'Project not found'}, status=404)
        except Exception as e:
            logger.exception(f"Error updating analysis progress: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

@login_required
def chat_interface(request, project_id):
    """Repository Chat page — the approved design, served to the project owner.

    The conversation, file tree, and symbol tree are intentionally static
    placeholders; this view only supplies the dynamic values the design shows
    (project name, branch, repository statistics, last-synced time) so the page
    renders identically while staying ready for the future AI backend. It does
    NOT wire the chat to any LLM.

    Access: unauthenticated users are redirected by @login_required; a project
    that does not exist is 404, and a project owned by someone else is 403 —
    mirroring analyze_project / delete_project.
    """
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        logger.warning("Chat access denied: project %s not found", project_id)
        return HttpResponse("Project not found.", status=404)

    if project.owner_id != request.user.id:
        logger.warning(
            "Chat access denied: user %s does not own project %s",
            request.user.id, project_id,
        )
        return HttpResponse("You do not have access to this project.", status=403)

    # Repository statistics for the Explorer header. Prefer the authoritative
    # parser summary; fall back to the latest AnalysisJob counts so the page
    # still renders if the parser database is unavailable.
    stats = {'files': 0, 'classes': 0}
    try:
        summary = knowledge_base.get_project_summary(project_id)
        stats = {
            'files': summary['files'],
            'classes': summary['classes'],
        }
    except Exception as e:
        logger.debug("Parser summary unavailable for project %s: %s", project_id, e)
        latest_job = project.analysis_jobs.order_by('-created_at').first()
        if latest_job:
            stats = {
                'files': latest_job.files_analyzed,
                'classes': latest_job.classes_found,
            }

    context = {
        'project': project,
        # Branch is not stored on Project; the pipeline always clones 'main'.
        'branch': 'main',
        'stats': stats,
    }
    return render(request, 'analyzer/chat.html', context)

@csrf_exempt
@require_http_methods(["POST"])
def project_ask(request, project_id):
    """Secure JSON API: ask a question about one of YOUR OWN repositories.

    POST /api/projects/<project_id>/ask/
    Body (JSON): {"question": "..."}

    Authentication
    --------------
    The request user must be authenticated (401 otherwise). No anonymous
    queries are allowed.

    Ownership
    ---------
    The project must belong to ``request.user`` (``owner_id`` match). If the
    project does not exist at all the response is 404; if it exists but belongs
    to a different user it is treated as 403 "forbidden" — a user can never
    query another user's repository. This mirrors the enforcement used by
    ``analyze_project`` / ``delete_project`` (scoped ``Project.objects.get(...,
    owner=request.user)``).

    Implementation
    --------------
    All question answering is delegated to ``llm_service`` — the ONLY Django
    <-> LLM interface — which reads parser data exclusively through
    ``context_builder`` -> ``knowledge_base``, each scoped by ``project_id``.
    This view adds no LLM logic of its own.

    CSRF note: ``@csrf_exempt`` matches the existing ``update_analysis_progress``
    endpoint. This is a token-authenticated API surface; for a cookie-only
    deployment, gate it behind a CSRF token or an Authorization header instead.
    """
    # 1. Authentication.
    if not request.user.is_authenticated:
        return JsonResponse(
            {'success': False, 'error': 'Authentication required.'},
            status=401,
        )

    # 2. Parse the JSON body and require a non-empty question.
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {'success': False, 'error': 'Request body must be valid JSON.'},
            status=400,
        )

    question = (payload.get('question') or '').strip()
    if not question:
        return JsonResponse(
            {'success': False, 'error': 'A non-empty "question" is required.'},
            status=400,
        )

    # 3. Project existence + ownership.
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        logger.warning("project_ask: project %s not found", project_id)
        return JsonResponse(
            {'success': False, 'error': 'Project not found.'},
            status=404,
        )

    if project.owner_id != request.user.id:
        logger.warning(
            "project_ask: denied - user %s does not own project %s",
            request.user.id, project_id,
        )
        return JsonResponse(
            {'success': False, 'error': 'You do not have access to this project.'},
            status=403,
        )

    # 4. Delegate to the LLM service. Its result is uniform:
    #    {answer, sources, metadata}; failures set metadata['error'].
    result = llm_service.answer_repository_question(project_id, question)
    meta = result.get('metadata') or {}

    if meta.get('error'):
        status = _ask_error_status(meta.get('error_type'))
        return JsonResponse(
            {
                'success': False,
                'error': meta.get('message', 'Question could not be answered.'),
                'error_type': meta.get('error_type'),
                'metadata': meta,
            },
            status=status,
        )

    # 5. Success — the spec'd response shape.
    return JsonResponse(
        {
            'success': True,
            'answer': result.get('answer'),
            'sources': result.get('sources', []),
            'metadata': meta,
        },
        status=200,
    )


def _ask_error_status(error_type):
    """Map an llm_service error_type to an appropriate HTTP status code.

    * empty_question / empty_repository -> 400 (bad request)
    * invalid_project                  -> 404 (not found)
    * repository_not_available         -> 503 (parser DB / repo data down)
    * missing_api_key / provider_sdk_missing / provider_error -> 502 (upstream)
    """
    if error_type in ('empty_question', 'empty_repository'):
        return 400
    if error_type == 'invalid_project':
        return 404
    if error_type == 'repository_not_available':
        return 503
    return 502


def add_project_form(request):
    """View to receive the Add Project form data without processing."""
    if request.method == 'POST':
        logger.debug(f"Add project form data: {request.POST}")
        return HttpResponse("Form received")
    else:
        return HttpResponse("Method not allowed", status=405)