"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from core import views
from formula1 import views as f1_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('soccer/', views.soccer_dashboard, name='soccer_home'),
    path('soccer/matches/', views.matches, name='soccer_matches'),
    path('soccer/match/<int:pk>/', views.match_detail, name='soccer_match_detail'),
    path('f1/', f1_views.dashboard, name='f1_home'),
    path('f1/calendar/', f1_views.calendar, name='f1_calendar'),
    path('f1/race/<int:pk>/', f1_views.race_detail, name='f1_race_detail'),
    path('f1/standings/', f1_views.standings, name='f1_standings'),
    path('f1/results/', f1_views.results, name='f1_results'),
    path('predictions/', views.all_predictions, name='predictions'),
    path('matches/', views.matches, name='matches'),
    path('matches/<int:pk>/', views.match_detail, name='match_detail'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('history/', views.history, name='history'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('faq/', views.faq_page, name='faq'),
    path('help/errors/', views.error_codes_page, name='error_codes'),
    path('support/', views.support_page, name='support'),
    path('support/tickets/submit/', views.submit_ticket, name='submit_ticket'),
    path('support/tickets/<str:reference>/', views.ticket_confirmation, name='ticket_confirmation'),
    path('assistant/chat/', views.assistant_chat, name='assistant_chat'),
    path('assistant/feedback/', views.assistant_feedback, name='assistant_feedback'),
    path('health/', views.health_check, name='health'),
]

handler404 = 'core.error_views.page_not_found'
handler500 = 'core.error_views.server_error'
