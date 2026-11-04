from django.db import models
from django.utils import timezone

class TaskCategory(models.TextChoices):
    WORK = 'WORK', 'Work'
    PERSONAL = 'PERSONAL', 'Personal'
    FINANCE = 'FINANCE', 'Finance'
    LEARNING = 'LEARNING', 'Learning'

class TaskPriority(models.TextChoices):
    HIGH = 'HIGH', 'High'
    MEDIUM = 'MEDIUM', 'Medium'
    LOW = 'LOW', 'Low'

class TaskStatus(models.TextChoices):
    TODO = 'TODO', 'Todo'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    DONE = 'DONE', 'Done'

class Task(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=50, choices=TaskCategory.choices, default=TaskCategory.PERSONAL)
    priority = models.CharField(max_length=20, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.TODO)
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_important = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', '-priority', '-created_at']

    def __str__(self):
        return self.title

class TransactionType(models.TextChoices):
    INCOME = 'INCOME', 'Income'
    EXPENSE = 'EXPENSE', 'Expense'
    DEBT_PAYMENT = 'DEBT_PAYMENT', 'Debt Payment'
    TRANSFER = 'TRANSFER', 'Transfer'

class Transaction(models.Model):
    title = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100, default='OTHER')
    date = models.DateTimeField(default=timezone.now)
    is_recurring = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.type}: {self.title} - {self.amount}"

class DebtType(models.TextChoices):
    OWED_BY_ME = 'OWED_BY_ME', 'Owed by Me'
    OWED_TO_ME = 'OWED_TO_ME', 'Owed to Me'

class DebtStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partially Paid'
    SETTLED = 'SETTLED', 'Settled'

class Debt(models.Model):
    person_name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=DebtType.choices)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=DebtStatus.choices, default=DebtStatus.PENDING)
    notes = models.TextField(blank=True, default='')
    repayments = models.JSONField(default=list, blank=True)  # [{amount: float, date: str, notes: str}]
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return f"{self.person_name} ({self.type}) - {self.total_amount}"


class Bill(models.Model):
    """Recurring plans like mobile recharge — remind before plan_days elapse."""
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    category = models.CharField(max_length=50, default='MOBILE')
    recharge_date = models.DateField(default=timezone.localdate)
    plan_days = models.PositiveIntegerField(default=28)
    remind_days_before = models.PositiveIntegerField(default=3)
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['recharge_date', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.plan_days}d)"

    @property
    def expires_on(self):
        from datetime import timedelta
        return self.recharge_date + timedelta(days=self.plan_days)

    @property
    def days_left(self):
        return (self.expires_on - timezone.localdate()).days

    @property
    def reminder_status(self):
        left = self.days_left
        if left < 0:
            return 'EXPIRED'
        if left <= self.remind_days_before:
            return 'ABOUT_TO_EXPIRE'
        return 'ACTIVE'

class Habit(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='ROUTINE')
    target_days_per_week = models.IntegerField(default=7)
    streak = models.IntegerField(default=0)
    completed_dates = models.JSONField(default=list, blank=True)  # ['YYYY-MM-DD']
    icon = models.CharField(max_length=50, default='CheckCircle')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class LearningGoalStatus(models.TextChoices):
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    PAUSED = 'PAUSED', 'Paused'

class LearningGoal(models.Model):
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='OTHER')
    platform_or_course = models.CharField(max_length=255, blank=True, default='')
    progress_percentage = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=LearningGoalStatus.choices, default=LearningGoalStatus.IN_PROGRESS)
    weekly_target_hours = models.DecimalField(max_digits=6, decimal_places=1, default=5.0)
    logged_hours = models.DecimalField(max_digits=6, decimal_places=1, default=0.0)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-progress_percentage', '-created_at']

    def __str__(self):
        return self.title

class JobApplicationStatus(models.TextChoices):
    APPLIED = 'APPLIED', 'Applied'
    INTERVIEWING = 'INTERVIEWING', 'Interviewing'
    OFFER = 'OFFER', 'Offer'
    REJECTED = 'REJECTED', 'Rejected'

class JobApplication(models.Model):
    company = models.CharField(max_length=255)
    role = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=JobApplicationStatus.choices, default=JobApplicationStatus.APPLIED)
    location = models.CharField(max_length=100, default='Remote')
    applied_date = models.DateTimeField(default=timezone.now)
    salary_estimate = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    follow_up_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-applied_date', '-created_at']

    def __str__(self):
        return f"{self.company} - {self.role}"

class Note(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default='')
    category = models.CharField(max_length=50, default='GENERAL')
    is_pinned = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return self.title

class UserSettings(models.Model):
    user_name = models.CharField(max_length=100, default='Arjun')
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=15000)
    monthly_emi_commitment = models.DecimalField(max_digits=12, decimal_places=2, default=4500)
    savings_target = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    currency = models.CharField(max_length=10, default='₹')
    timezone = models.CharField(max_length=100, default='Asia/Kolkata')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings for {self.user_name}"

