from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.urls import reverse_lazy
from django.db.models import Sum
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
import json
import os
import subprocess
import threading
import time
from datetime import datetime

from .models import Project, AnalysisJob

def home(request):
    return render(request, 'analyzer/home.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember')

        # Authenticate using email (since we are using email as username)
        # Django's authenticate function uses username by default, so we need to get the user by email first
        try:
            user_obj = User.objects.get(email=email)
            username = user_obj.username
        except User.DoesNotExist:
            # If email not found, we still want to authenticate to avoid user enumeration
            # But we'll use a dummy username to avoid leaking information
            username = email  # This will fail authentication

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
    # Get the current user's projects
    user_projects = Project.objects.filter(owner=request.user)
    project_count = user_projects.count()

    # Get completed analysis jobs count
    completed_jobs_count = AnalysisJob.objects.filter(project__owner=request.user, status='completed').count()

    # Get total files analyzed across all projects
    total_files_analyzed = AnalysisJob.objects.filter(project__owner=request.user).aggregate(total=Sum('files_analyzed'))['total'] or 0

    # Get the latest analysis job for each project (for the project cards)
    projects_with_status = []
    for project in user_projects:
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
            import re
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
            # Validation successful
            print("Validation Successful")
            # Note: Not saving to database, not redirecting, not calling parser, not starting threads
            # Just re-render the form
            return render(request, 'analyzer/add_project.html')
        else:
            # Validation failed - re-render form with messages
            # Note: Without template modifications to display messages,
            # the user won't see them, but they are added to the message framework
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
            return JsonResponse({'error': 'Project not found'}, status=404)

    return JsonResponse({'error': 'Invalid request'}, status=400)

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
        analysis_job.started_at = datetime.now()
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
        cmd = [
            'python',
            os.path.join(settings.BASE_DIR, 'repo_parser.py'),
            '--repo-url', repo_url,
            '--to-path', repo_path
        ]

        # Set environment variables for database connection (use Django's database settings)
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
            project.last_analyzed = datetime.now()

            analysis_job.status = 'completed'
            analysis_job.completed_at = datetime.now()
            analysis_job.progress = 100

            # TODO: Extract actual metrics from stdout or database
            # For now, we'll set some placeholder values - in a real implementation,
            # we would query the database for actual counts
            try:
                # Try to get actual counts from the database
                from django.db import connection
                with connection.cursor() as cursor:
                    # Count files
                    cursor.execute("SELECT COUNT(*) FROM files")
                    analysis_job.files_analyzed = cursor.fetchone()[0]

                    # Count entities by type
                    cursor.execute("SELECT COUNT(*) FROM code_entities WHERE type = 'function'")
                    analysis_job.functions_found = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM code_entities WHERE type = 'class'")
                    analysis_job.classes_found = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM code_entities WHERE type = 'method'")
                    analysis_job.methods_found = cursor.fetchone()[0]

                    # Count relationships
                    cursor.execute("SELECT COUNT(*) FROM relationships")
                    analysis_job.relationships_found = cursor.fetchone()[0]
            except:
                # If we can't get the actual counts, keep the placeholder values
                analysis_job.files_analyzed = 0
                analysis_job.functions_found = 0
                analysis_job.classes_found = 0
                analysis_job.methods_found = 0
                analysis_job.relationships_found = 0

            # Combine stdout and stderr for logs
            combined_logs = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            analysis_job.logs = combined_logs

            messages.success(None, f"Analysis of {project.name} completed successfully!")
        else:
            # Failure
            project.analysis_status = 'failed'

            analysis_job.status = 'failed'
            analysis_job.completed_at = datetime.now()

            # Store error message
            error_msg = stderr[:500] if stderr else "Unknown error occurred"
            # We could add an error_message field to AnalysisJob if needed

            # Combine stdout and stderr for logs
            combined_logs = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            analysis_job.logs = combined_logs

            messages.error(None, f"Analysis of {project.name} failed: {error_msg}")

        project.save()
        analysis_job.save()

    except Project.DoesNotExist:
        pass  # Project was deleted
    except subprocess.TimeoutExpired:
        # Handle timeout
        try:
            project = Project.objects.get(id=project_id)
            project.analysis_status = 'failed'
            project.save()

            analysis_job = AnalysisJob.objects.filter(project=project).order_by('-created_at').first()
            if analysis_job:
                analysis_job.status = 'failed'
                analysis_job.completed_at = datetime.now()
                analysis_job.progress = 0
                analysis_job.save()
        except:
            pass
    except Exception as e:
        # Handle any other exceptions
        try:
            project = Project.objects.get(id=project_id)
            project.analysis_status = 'failed'
            project.save()

            analysis_job = AnalysisJob.objects.filter(project=project).order_by('-created_at').first()
            if analysis_job:
                analysis_job.status = 'failed'
                analysis_job.completed_at = datetime.now()
                analysis_job.progress = 0
                analysis_job.save()
        except:
            pass

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
                # For now, we're not storing logs in the database

                analysis_job.save()

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

@login_required
def chat_interface(request, project_id):
    return render(request, 'analyzer/chat.html')


def add_project_form(request):
    """View to receive the Add Project form data without processing.
    This view is used solely for connecting the form to Django.
    It does not validate, save, or redirect.
    """
    if request.method == 'POST':
        # For debugging, we can print the data to console (optional)
        # print(request.POST)
        return HttpResponse("Form received")
    else:
        return HttpResponse("Method not allowed", status=405)