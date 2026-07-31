# from django.urls import path
# from . import views
# from django.contrib.auth import views as auth_views

# urlpatterns = [
#     path('', views.home, name='home'),
#     path('login/', views.login_view, name='login'),
#     path('signup/', views.signup_view, name='signup'),
#     path('dashboard/', views.dashboard, name='dashboard'),
#     path('logout/', views.logout_view, name='logout'),
#     path('add-project/', views.add_project, name='add_project'),
#     path('analyze/<int:project_id>/', views.analyze_project, name='analyze_project'),
#     path('chat/<int:project_id>/', views.chat_interface, name='chat_interface'),

#     # Password reset URLs
#     path('password-reset/', auth_views.PasswordResetView.as_view(template_name='authentication/password_reset_form.html'), name='password_reset'),
#     path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='authentication/password_reset_done.html'), name='password_reset_done'),
#     path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='authentication/password_reset_confirm.html'), name='password_reset_confirm'),
#     path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='authentication/password_reset_complete.html'), name='password_reset_complete'),
# ]
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'analyzer'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('add-project/', views.add_project, name='add_project'),

    # Project routes
    path('analyze/<int:project_id>/', views.analyze_project, name='analyze_project'),
    path('chat/<int:project_id>/', views.chat_interface, name='chat_interface'),

    # Password reset URLs
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='authentication/password_reset_form.html'
        ),
        name='password_reset'
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='authentication/password_reset_done.html'
        ),
        name='password_reset_done'
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='authentication/password_reset_confirm.html'
        ),
        name='password_reset_confirm'
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='authentication/password_reset_complete.html'
        ),
        name='password_reset_complete'
    ),
]