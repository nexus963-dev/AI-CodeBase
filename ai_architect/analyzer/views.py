from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.urls import reverse_lazy
from django.db.models import Sum
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

# We'll keep the existing views for now, but we'll update them later to use real data
def add_project(request):
    return HttpResponse("<h1>Add Project</h1><p>This is the add project page.</p>")

def analyze_project(request, project_id):
    return HttpResponse(f"<h1>Analyze Project {project_id}</h1><p>This is the analyze project page for project {project_id}.</p>")

def chat_interface(request, project_id):
    return HttpResponse(f"<h1>Chat Interface</h1><p>This is the chat interface for project {project_id}.</p>")