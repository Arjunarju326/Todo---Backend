from django.urls import path
from .views import (
    DashboardView, TasksView, FinanceView, GrowthView,
    HabitsView, NotesView, SettingsView, SeedView,
    AuthLoginView, AuthLogoutView, AuthMeView, AuthRegisterView,
)

urlpatterns = [
    path('auth/login', AuthLoginView.as_view(), name='auth_login'),
    path('auth/login/', AuthLoginView.as_view(), name='auth_login_slash'),
    path('auth/logout', AuthLogoutView.as_view(), name='auth_logout'),
    path('auth/logout/', AuthLogoutView.as_view(), name='auth_logout_slash'),
    path('auth/me', AuthMeView.as_view(), name='auth_me'),
    path('auth/me/', AuthMeView.as_view(), name='auth_me_slash'),
    path('auth/register', AuthRegisterView.as_view(), name='auth_register'),
    path('auth/register/', AuthRegisterView.as_view(), name='auth_register_slash'),
    path('dashboard', DashboardView.as_view(), name='dashboard'),
    path('dashboard/', DashboardView.as_view(), name='dashboard_slash'),
    path('tasks', TasksView.as_view(), name='tasks'),
    path('tasks/', TasksView.as_view(), name='tasks_slash'),
    path('finance', FinanceView.as_view(), name='finance'),
    path('finance/', FinanceView.as_view(), name='finance_slash'),
    path('growth', GrowthView.as_view(), name='growth'),
    path('growth/', GrowthView.as_view(), name='growth_slash'),
    path('habits', HabitsView.as_view(), name='habits'),
    path('habits/', HabitsView.as_view(), name='habits_slash'),
    path('notes', NotesView.as_view(), name='notes'),
    path('notes/', NotesView.as_view(), name='notes_slash'),
    path('settings', SettingsView.as_view(), name='settings'),
    path('settings/', SettingsView.as_view(), name='settings_slash'),
    path('seed', SeedView.as_view(), name='seed'),
    path('seed/', SeedView.as_view(), name='seed_slash'),
]

