from rest_framework import serializers
from .models import (
    Task, Transaction, Debt, Bill, Habit,
    LearningGoal, JobApplication, Note, UserSettings
)

class TaskSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    dueDate = serializers.DateTimeField(source='due_date', required=False, allow_null=True)
    completedAt = serializers.DateTimeField(source='completed_at', required=False, allow_null=True)
    isImportant = serializers.BooleanField(source='is_important', required=False, default=False)

    class Meta:
        model = Task
        fields = [
            'id', '_id', 'title', 'description', 'category', 'priority',
            'status', 'due_date', 'dueDate', 'completed_at', 'completedAt',
            'is_important', 'isImportant', 'tags', 'created_at', 'updated_at'
        ]

    def get__id(self, obj):
        return str(obj.id)


class TransactionSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    amount = serializers.FloatField()
    isRecurring = serializers.BooleanField(source='is_recurring', required=False, default=False)

    class Meta:
        model = Transaction
        fields = [
            'id', '_id', 'title', 'type', 'amount', 'category',
            'date', 'is_recurring', 'isRecurring', 'notes', 'created_at'
        ]

    def get__id(self, obj):
        return str(obj.id)


class DebtSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    personName = serializers.CharField(source='person_name')
    totalAmount = serializers.FloatField(source='total_amount')
    paidAmount = serializers.FloatField(source='paid_amount', required=False, default=0)
    dueDate = serializers.DateTimeField(source='due_date', required=False, allow_null=True)

    class Meta:
        model = Debt
        fields = [
            'id', '_id', 'person_name', 'personName', 'type',
            'total_amount', 'totalAmount', 'paid_amount', 'paidAmount',
            'due_date', 'dueDate', 'status', 'notes', 'repayments', 'created_at'
        ]

    def get__id(self, obj):
        return str(obj.id)


class BillSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    amount = serializers.FloatField(required=False, default=0)
    rechargeDate = serializers.DateField(source='recharge_date')
    planDays = serializers.IntegerField(source='plan_days', required=False, default=28)
    remindDaysBefore = serializers.IntegerField(source='remind_days_before', required=False, default=3)
    isActive = serializers.BooleanField(source='is_active', required=False, default=True)
    expiresOn = serializers.SerializerMethodField()
    daysLeft = serializers.SerializerMethodField()
    reminderStatus = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = [
            'id', '_id', 'title', 'amount', 'category',
            'recharge_date', 'rechargeDate', 'plan_days', 'planDays',
            'remind_days_before', 'remindDaysBefore', 'notes',
            'is_active', 'isActive', 'expiresOn', 'daysLeft', 'reminderStatus',
            'created_at', 'updated_at',
        ]

    def get__id(self, obj):
        return str(obj.id)

    def get_expiresOn(self, obj):
        return obj.expires_on.isoformat()

    def get_daysLeft(self, obj):
        return obj.days_left

    def get_reminderStatus(self, obj):
        return obj.reminder_status


class HabitSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    targetDaysPerWeek = serializers.IntegerField(source='target_days_per_week', required=False, default=7)
    completedDates = serializers.ListField(source='completed_dates', child=serializers.CharField(), required=False)

    class Meta:
        model = Habit
        fields = [
            'id', '_id', 'name', 'category', 'target_days_per_week', 'targetDaysPerWeek',
            'streak', 'completed_dates', 'completedDates', 'icon', 'created_at'
        ]

    def get__id(self, obj):
        return str(obj.id)


class LearningGoalSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    platformOrCourse = serializers.CharField(source='platform_or_course', required=False, allow_blank=True, default='')
    progressPercentage = serializers.IntegerField(source='progress_percentage', required=False, default=0)
    weeklyTargetHours = serializers.FloatField(source='weekly_target_hours', required=False, default=5.0)
    loggedHours = serializers.FloatField(source='logged_hours', required=False, default=0.0)

    class Meta:
        model = LearningGoal
        fields = [
            'id', '_id', 'title', 'category', 'platform_or_course', 'platformOrCourse',
            'progress_percentage', 'progressPercentage', 'status',
            'weekly_target_hours', 'weeklyTargetHours', 'logged_hours', 'loggedHours',
            'notes', 'created_at'
        ]

    def get__id(self, obj):
        return str(obj.id)


class JobApplicationSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    appliedDate = serializers.DateTimeField(source='applied_date', required=False)
    salaryEstimate = serializers.CharField(source='salary_estimate', required=False, allow_blank=True, default='')
    followUpDate = serializers.DateTimeField(source='follow_up_date', required=False, allow_null=True)

    class Meta:
        model = JobApplication
        fields = [
            'id', '_id', 'company', 'role', 'status', 'location',
            'applied_date', 'appliedDate', 'salary_estimate', 'salaryEstimate',
            'notes', 'follow_up_date', 'followUpDate', 'created_at'
        ]

    def get__id(self, obj):
        return str(obj.id)


class NoteSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    isPinned = serializers.BooleanField(source='is_pinned', required=False, default=False)

    class Meta:
        model = Note
        fields = [
            'id', '_id', 'title', 'content', 'category',
            'is_pinned', 'isPinned', 'tags', 'created_at', 'updated_at'
        ]

    def get__id(self, obj):
        return str(obj.id)


class UserSettingsSerializer(serializers.ModelSerializer):
    _id = serializers.SerializerMethodField()
    userName = serializers.CharField(source='user_name', required=False)
    monthlyIncome = serializers.FloatField(source='monthly_income', required=False)
    monthlyEmiCommitment = serializers.FloatField(source='monthly_emi_commitment', required=False)
    savingsTarget = serializers.FloatField(source='savings_target', required=False)

    class Meta:
        model = UserSettings
        fields = [
            'id', '_id', 'user_name', 'userName', 'monthly_income', 'monthlyIncome',
            'monthly_emi_commitment', 'monthlyEmiCommitment', 'savings_target', 'savingsTarget',
            'currency', 'timezone', 'updated_at'
        ]

    def get__id(self, obj):
        return str(obj.id)

