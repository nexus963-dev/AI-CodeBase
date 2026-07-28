from django.urls import path
from . import views

app_name = 'analyzer'
urlpatterns = [
    # Home page with login/signup
    path('', views.home, name='home'),
    # Authentication
    path('login/', views.login, name='login'),
    path('signup/', views.signup, name='signup'),
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    # Add project form
    path('add-project/', views.add_project, name='add_project'),
    # Analysis page
    path('analyze/<int:project_id>/', views.analyze_project, name='analyze_project'),
    # AI chatbot interface
    path('chat/<int:project_id>/', views.chat_interface, name='chat_interface'),
]