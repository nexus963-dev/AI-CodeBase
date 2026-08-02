from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.db.models import Sum
from django.utils import timezone
from django.db import connection
import os
import subprocess
import threading
import logging
import sys
import json
import re
from datetime import datetime

# Import your models
from .models import Project, AnalysisJob, File, CodeEntity, Relationship

logger = logging.getLogger(__name__)

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
                
                # Start the analysis in background
                # TODO: Consider migrating to Celery/RQ for production
                analysis_thread = threading.Thread(
                    target=run_repository_analysis,
                    args=(project.id,),
                    daemon=True  # Allow thread to exit when main process ends
                )
                analysis_thread.start()
                
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

def run_repository_analysis(project_id):
    """Background function to run the repository analysis pipeline"""
    try:
        project = Project.objects.get(id=project_id)

        # Update project status to analyzing
        project.analysis_status = 'analyzing'
        project.save()

        # Get or create analysis job
        analysis_job = project.analysis_jobs.order_by('-created_at').first()
        if not analysis_job:
            analysis_job = AnalysisJob.objects.create(project=project)

        # Update job status
        analysis_job.status = 'running'
        analysis_job.started_at = timezone.now()
        analysis_job.progress = 0
        analysis_job.save()

        # Prepare parameters for repo_parser.py
        repo_url = project.github_url
        # Extract repo name from URL for directory name
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        # Use media directory for storing repositories
        repo_path = os.path.join(settings.MEDIA_ROOT, 'repos', repo_name)

        # Ensure media directory exists
        os.makedirs(os.path.join(settings.MEDIA_ROOT, 'repos'), exist_ok=True)

        # Build command to run repo_parser.py
        # repo_parser.py lives at the repo root, one level above settings.BASE_DIR
        # Use the same interpreter running Django so the parser has access to
        # the same installed packages (pygit2, tree-sitter, psycopg2).
        cmd = [
            sys.executable,
            os.path.join(settings.BASE_DIR.parent, 'repo_parser.py'),
            '--repo-url', repo_url,
            '--to-path', repo_path
        ]

        # Set environment variables for database connection
        env = os.environ.copy()
        db_settings = settings.DATABASES['default']
        env['DB_HOST'] = db_settings.get('HOST', 'localhost')
        env['DB_NAME'] = db_settings.get('NAME', 'postgres')
        env['DB_USER'] = db_settings.get('USER', 'postgres')
        env['DB_PASSWORD'] = db_settings.get('PASSWORD', 'postgres')
        env['DB_PORT'] = str(db_settings.get('PORT', 5432))

        # Run the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=settings.BASE_DIR
        )

        # Wait for completion with timeout
        stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout

        # Update based on result
        if process.returncode == 0:
            # Success - update project and job
            project.analysis_status = 'completed'
            project.last_analyzed = timezone.now()

            analysis_job.status = 'completed'
            analysis_job.completed_at = timezone.now()
            analysis_job.progress = 100

            # Try to get actual counts from the database
            try:
                # The unmanaged analysis tables (files, code_entities, relationships)
                # are not project-scoped, so counts reflect all analyzed repositories.
                # Count files
                analysis_job.files_analyzed = File.objects.count()

                # Count entities by type
                analysis_job.functions_found = CodeEntity.objects.filter(
                    type='function'
                ).count()

                analysis_job.classes_found = CodeEntity.objects.filter(
                    type='class'
                ).count()

                analysis_job.methods_found = CodeEntity.objects.filter(
                    type='method'
                ).count()

                # Count relationships
                analysis_job.relationships_found = Relationship.objects.count()

                logger.info(f"Analysis of {project.name} completed with {analysis_job.files_analyzed} files analyzed")
            except Exception as e:
                # If we can't get the actual counts, log the error
                logger.warning(f"Could not retrieve analysis metrics for project {project.id}: {str(e)}")
                analysis_job.files_analyzed = 0
                analysis_job.functions_found = 0
                analysis_job.classes_found = 0
                analysis_job.methods_found = 0
                analysis_job.relationships_found = 0

            # Combine stdout and stderr for logs
            combined_logs = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            analysis_job.logs = combined_logs

            logger.info(f"Analysis of {project.name} completed successfully")
        else:
            # Failure
            project.analysis_status = 'failed'

            analysis_job.status = 'failed'
            analysis_job.completed_at = timezone.now()

            # Store error message
            error_msg = stderr[:500] if stderr else "Unknown error occurred"
            
            # Combine stdout and stderr for logs
            combined_logs = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            analysis_job.logs = combined_logs

            logger.error(f"Analysis of {project.name} failed: {error_msg}")

        project.save()
        analysis_job.save()

    except Project.DoesNotExist as e:
        logger.exception(f"Project {project_id} not found during analysis")
    except subprocess.TimeoutExpired as e:
        # Handle timeout
        logger.exception(f"Analysis of project {project_id} timed out after 300 seconds")
        try:
            project = Project.objects.get(id=project_id)
            project.analysis_status = 'failed'
            project.save()

            analysis_job = AnalysisJob.objects.filter(project=project).order_by('-created_at').first()
            if analysis_job:
                analysis_job.status = 'failed'
                analysis_job.completed_at = timezone.now()
                analysis_job.progress = 0
                analysis_job.save()
        except Project.DoesNotExist:
            logger.warning(f"Project {project_id} was deleted during analysis")
        except Exception as e:
            logger.exception(f"Unexpected error handling timeout for project {project_id}")
    except Exception as e:
        # Handle any other exceptions
        logger.exception(f"Unexpected error during analysis of project {project_id}: {str(e)}")
        try:
            project = Project.objects.get(id=project_id)
            project.analysis_status = 'failed'
            project.save()

            analysis_job = AnalysisJob.objects.filter(project=project).order_by('-created_at').first()
            if analysis_job:
                analysis_job.status = 'failed'
                analysis_job.completed_at = timezone.now()
                analysis_job.progress = 0
                analysis_job.save()
        except Project.DoesNotExist:
            logger.warning(f"Project {project_id} was deleted during analysis")
        except Exception as nested_e:
            logger.exception(f"Error while handling exception for project {project_id}: {str(nested_e)}")

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
    # Verify project ownership
    try:
        Project.objects.get(id=project_id, owner=request.user)
        return render(request, 'analyzer/chat.html')
    except Project.DoesNotExist:
        logger.warning(f"Chat interface access denied for project {project_id}")
        messages.error(request, "Project not found.")
        return redirect('analyzer:dashboard')

def add_project_form(request):
    """View to receive the Add Project form data without processing."""
    if request.method == 'POST':
        logger.debug(f"Add project form data: {request.POST}")
        return HttpResponse("Form received")
    else:
        return HttpResponse("Method not allowed", status=405)