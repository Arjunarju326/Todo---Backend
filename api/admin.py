from django.contrib import admin
from .models import (
    Task, Transaction, Debt, Bill, Habit,
    LearningGoal, JobApplication, Note, UserSettings,
    AssistantMemory, NivaCompanionSettings, NivaDailyPlan,
    NivaSkillProgress, NivaConversation,
    NivaTrace, NivaEvalSuite, NivaEvalScenario, NivaEvalRun,
    NivaEvalResult, NivaMetricSnapshot, NivaActivityEvent,
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
admin.site.register(AssistantMemory)
admin.site.register(NivaCompanionSettings)
admin.site.register(NivaDailyPlan)
admin.site.register(NivaSkillProgress)
admin.site.register(NivaConversation)
admin.site.register(NivaTrace)
admin.site.register(NivaEvalSuite)
admin.site.register(NivaEvalScenario)
admin.site.register(NivaEvalRun)
admin.site.register(NivaEvalResult)
admin.site.register(NivaMetricSnapshot)
admin.site.register(NivaActivityEvent)

