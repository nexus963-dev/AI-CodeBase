from django.shortcuts import render
from django.http import HttpResponse


def home(request):
    return render(request, 'analyzer/home.html')


def login(request):
    return render(request, 'analyzer/login.html')


def signup(request):
    return render(request, 'analyzer/signup.html')


def dashboard(request):
    return render(request, 'analyzer/dashboard.html')


def add_project(request):
    return HttpResponse("<h1>Add Project</h1><p>This is the add project page.</p>")


def analyze_project(request, project_id):
    return HttpResponse(f"<h1>Analyze Project {project_id}</h1><p>This is the analyze project page for project {project_id}.</p>")


def chat_interface(request, project_id):
    return HttpResponse(f"<h1>Chat Interface</h1><p>This is the chat interface for project {project_id}.</p>")