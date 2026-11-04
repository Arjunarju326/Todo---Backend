from django.contrib import admin
from .models import (
    Task, Transaction, Debt, Bill, Habit,
    LearningGoal, JobApplication, Note, UserSettings
)

admin.site.register(Task)
admin.site.register(Transaction)
admin.site.register(Debt)
admin.site.register(Bill)
admin.site.register(Habit)
admin.site.register(LearningGoal)
admin.site.register(JobApplication)
admin.site.register(Note)
admin.site.register(UserSettings)

