from django.urls import path
from .views import (
    DashboardView, TasksView, FinanceView, GrowthView,
    HabitsView, NotesView, SettingsView, SeedView
)

urlpatterns = [
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

