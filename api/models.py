from django.conf import settings
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
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
        null=True,
        blank=True,
    )
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
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return self.title

class TransactionType(models.TextChoices):
    INCOME = 'INCOME', 'Income'
    EXPENSE = 'EXPENSE', 'Expense'
    DEBT_PAYMENT = 'DEBT_PAYMENT', 'Debt Payment'
    TRANSFER = 'TRANSFER', 'Transfer'

class Transaction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions',
        null=True,
        blank=True,
    )
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
        indexes = [models.Index(fields=['user', 'date'])]

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
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='debts',
        null=True,
        blank=True,
    )
    person_name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=DebtType.choices)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=DebtStatus.choices, default=DebtStatus.PENDING)
    notes = models.TextField(blank=True, default='')
    repayments = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', '-created_at']
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return f"{self.person_name} ({self.type}) - {self.total_amount}"


class Bill(models.Model):
    """Recurring plans like mobile recharge — remind before plan_days elapse."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bills',
        null=True,
        blank=True,
    )
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
        indexes = [models.Index(fields=['user', 'is_active'])]

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
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='habits',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='ROUTINE')
    target_days_per_week = models.IntegerField(default=7)
    streak = models.IntegerField(default=0)
    completed_dates = models.JSONField(default=list, blank=True)
    icon = models.CharField(max_length=50, default='CheckCircle')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user'])]

    def __str__(self):
        return self.name

class LearningGoalStatus(models.TextChoices):
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    PAUSED = 'PAUSED', 'Paused'

class LearningGoal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_goals',
        null=True,
        blank=True,
    )
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
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return self.title

class JobApplicationStatus(models.TextChoices):
    APPLIED = 'APPLIED', 'Applied'
    INTERVIEWING = 'INTERVIEWING', 'Interviewing'
    OFFER = 'OFFER', 'Offer'
    REJECTED = 'REJECTED', 'Rejected'

class JobApplication(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='job_applications',
        null=True,
        blank=True,
    )
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
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return f"{self.company} - {self.role}"

class Note(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notes',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default='')
    category = models.CharField(max_length=50, default='GENERAL')
    is_pinned = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [models.Index(fields=['user', 'is_pinned'])]

    def __str__(self):
        return self.title

class UserSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='settings',
        null=True,
        blank=True,
    )
    user_name = models.CharField(max_length=100, default='Arjun')
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=15000)
    monthly_emi_commitment = models.DecimalField(max_digits=12, decimal_places=2, default=4500)
    savings_target = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    currency = models.CharField(max_length=10, default='₹')
    timezone = models.CharField(max_length=100, default='Asia/Kolkata')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings for {self.user_name}"


class AssistantSourceType(models.TextChoices):
    TASK = 'TASK', 'Task'
    HABIT = 'HABIT', 'Habit'
    LEARNING = 'LEARNING', 'Learning'
    NOTE = 'NOTE', 'Note'
    KNOWLEDGE = 'KNOWLEDGE', 'Knowledge'
    PROFILE = 'PROFILE', 'Profile'
    MEMORY = 'MEMORY', 'Memory'
    SUMMARY = 'SUMMARY', 'Conversation Summary'
    JOURNAL = 'JOURNAL', 'Journal'
    LEARNING_NOTE = 'LEARNING_NOTE', 'Learning Note'


class AssistantMemory(models.Model):
    """Per-user long-term facts Niva should remember across chats."""

    CATEGORY_CHOICES = [
        ('profile', 'Profile'),
        ('goal', 'Goal'),
        ('active_context', 'Active Context'),
        ('preference', 'Preference'),
        ('episodic', 'Episodic'),
        ('routine', 'Routine'),
        ('temporary', 'Temporary'),
        ('learning', 'Learning'),
        ('general', 'General'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('superseded', 'Superseded'),
        ('archived', 'Archived'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assistant_memories',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='general')
    key = models.CharField(max_length=150, blank=True, default='')
    confidence = models.FloatField(default=1.0)
    importance = models.IntegerField(default=5)
    explicit = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)
    source_message = models.TextField(blank=True, default='')
    last_accessed = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', 'key']),
            models.Index(fields=['user', 'category', 'status']),
        ]

    def __str__(self):
        return self.title


class AssistantChunk(models.Model):
    """RAG chunk with optional pgvector embedding (768 dims for text-embedding-004)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assistant_chunks',
        null=True,
        blank=True,
    )
    source_type = models.CharField(max_length=20, choices=AssistantSourceType.choices)
    source_id = models.CharField(max_length=64, blank=True, default='')
    title = models.CharField(max_length=255, blank=True, default='')
    content = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['user', 'source_type']),
        ]
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.source_type}:{self.title or self.source_id}"


class AssistantBrief(models.Model):
    """Cached daily briefing for Smrti popup."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assistant_briefs',
        null=True,
        blank=True,
    )
    brief_date = models.DateField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'brief_date'],
                name='unique_assistant_brief_per_user_date',
            ),
        ]

    def __str__(self):
        return f"Smrti brief {self.brief_date}"


class NivaConversation(models.Model):
    """Chat thread for Niva v2 continuity."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_conversations',
    )
    title = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['user', '-updated_at'])]

    def __str__(self):
        return self.title or f"Conversation {self.id}"


class NivaConversationSummary(models.Model):
    conversation = models.OneToOneField(
        NivaConversation,
        on_delete=models.CASCADE,
        related_name='summary',
    )
    summary = models.TextField(blank=True, default='')
    current_topic = models.CharField(max_length=255, blank=True, default='')
    unresolved_items = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Summary for {self.conversation_id}"


class NivaDailyPlan(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_daily_plans',
    )
    plan_date = models.DateField()
    summary = models.TextField(blank=True, default='')
    focus_task_id = models.IntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'plan_date'],
                name='unique_niva_daily_plan_per_user_date',
            ),
        ]
        ordering = ['-plan_date']

    def __str__(self):
        return f"Plan {self.plan_date}"


class NivaCompanionSettings(models.Model):
    REPLY_LANGUAGE_CHOICES = [
        ('auto', 'Auto (mirror user)'),
        ('en', 'English'),
        ('manglish', 'Manglish'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_settings',
    )
    response_verbosity = models.CharField(max_length=20, default='normal')
    reply_language = models.CharField(
        max_length=20,
        choices=REPLY_LANGUAGE_CHOICES,
        default='auto',
    )
    morning_briefing_enabled = models.BooleanField(default=False)
    morning_briefing_time = models.TimeField(null=True, blank=True)
    evening_review_enabled = models.BooleanField(default=False)
    evening_review_time = models.TimeField(null=True, blank=True)
    weekly_review_enabled = models.BooleanField(default=False)
    weekly_review_weekday = models.IntegerField(default=6)  # Sunday
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    learning_reminders = models.BooleanField(default=False)
    web_research_enabled = models.BooleanField(default=True)
    proactive_enabled = models.BooleanField(default=False)
    # Phase 14 — opt-in nudges (off by default)
    spend_alerts_enabled = models.BooleanField(default=False)
    overdue_nudge_enabled = models.BooleanField(default=False)
    last_overdue_nudge_on = models.DateField(null=True, blank=True)
    last_spend_alert_on = models.DateField(null=True, blank=True)
    last_weekly_review_on = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Niva settings for user {self.user_id}"


class NivaSkillProgress(models.Model):
    LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_skills',
    )
    skill = models.CharField(max_length=120)
    current_level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='beginner')
    target_level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='intermediate')
    roadmap = models.JSONField(default=list, blank=True)
    completed_topics = models.JSONField(default=list, blank=True)
    weak_topics = models.JSONField(default=list, blank=True)
    last_practice_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'skill'],
                name='unique_niva_skill_per_user',
            ),
        ]
        ordering = ['skill']

    def __str__(self):
        return f"{self.skill} ({self.current_level})"


class NivaLearningSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_learning_sessions',
    )
    skill = models.ForeignKey(
        NivaSkillProgress,
        on_delete=models.CASCADE,
        related_name='sessions',
        null=True,
        blank=True,
    )
    topic = models.CharField(max_length=255)
    duration_minutes = models.IntegerField(default=25)
    score = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.topic} ({self.duration_minutes}m)"


class NivaResearchCache(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_research_cache',
        null=True,
        blank=True,
    )
    query_hash = models.CharField(max_length=64)
    query = models.CharField(max_length=500)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['query_hash', 'expires_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return self.query[:80]


# --- Niva Intelligence Lab (v2.1 Sprint 1) — additive observability / eval ---


class NivaTrace(models.Model):
    """Optional per-turn trace for prod (flag) or eval runs."""

    SOURCE_CHOICES = [
        ('prod', 'Production'),
        ('eval', 'Evaluation'),
    ]

    request_id = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='niva_traces',
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='prod')
    message_preview = models.CharField(max_length=240, blank=True, default='')
    message_hash = models.CharField(max_length=64, blank=True, default='')
    primary_intent = models.CharField(max_length=64, blank=True, default='')
    intent_confidence = models.FloatField(null=True, blank=True)
    tools = models.JSONField(default=list, blank=True)
    response_type = models.CharField(max_length=64, blank=True, default='')
    conversation_id = models.IntegerField(null=True, blank=True)
    model_name = models.CharField(max_length=120, blank=True, default='')
    latency_ms = models.IntegerField(null=True, blank=True)
    llm_latency_ms = models.IntegerField(null=True, blank=True)
    tool_latency_ms = models.IntegerField(null=True, blank=True)
    memory_count = models.IntegerField(default=0)
    search_count = models.IntegerField(default=0)
    token_usage = models.JSONField(default=dict, blank=True)
    success = models.BooleanField(default=True)
    error_status = models.CharField(max_length=120, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source', '-created_at']),
            models.Index(fields=['primary_intent', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.request_id} {self.primary_intent}"


class NivaEvalSuite(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    version = models.CharField(max_length=40, default='1.0')
    description = models.TextField(blank=True, default='')
    scenario_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slug']

    def __str__(self):
        return f"{self.slug}@{self.version}"


class NivaEvalScenario(models.Model):
    suite = models.ForeignKey(
        NivaEvalSuite,
        on_delete=models.CASCADE,
        related_name='scenarios',
    )
    scenario_id = models.CharField(max_length=32)
    category = models.CharField(max_length=40, db_index=True)
    title = models.CharField(max_length=255, blank=True, default='')
    input_text = models.TextField()
    history = models.JSONField(default=list, blank=True)
    fixtures = models.JSONField(default=dict, blank=True)
    expect = models.JSONField(default=dict, blank=True)
    weight = models.FloatField(default=1.0)
    tags = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['scenario_id']
        constraints = [
            models.UniqueConstraint(
                fields=['suite', 'scenario_id'],
                name='unique_niva_eval_scenario_per_suite',
            ),
        ]
        indexes = [
            models.Index(fields=['suite', 'category']),
        ]

    def __str__(self):
        return f"{self.scenario_id} ({self.category})"


class NivaEvalRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    suite = models.ForeignKey(
        NivaEvalSuite,
        on_delete=models.CASCADE,
        related_name='runs',
    )
    label = models.CharField(max_length=160, blank=True, default='')
    mode = models.CharField(max_length=20, default='intent')  # intent | full
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    aggregate = models.JSONField(default=dict, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='niva_eval_runs',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Run {self.id} {self.suite.slug} ({self.status})"


class NivaEvalResult(models.Model):
    run = models.ForeignKey(
        NivaEvalRun,
        on_delete=models.CASCADE,
        related_name='results',
    )
    scenario = models.ForeignKey(
        NivaEvalScenario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='results',
    )
    scenario_key = models.CharField(max_length=32)
    category = models.CharField(max_length=40, blank=True, default='')
    passed = models.BooleanField(default=False)
    score = models.FloatField(default=0.0)
    weight = models.FloatField(default=1.0)
    metrics = models.JSONField(default=dict, blank=True)
    actual = models.JSONField(default=dict, blank=True)
    diffs = models.JSONField(default=list, blank=True)
    critical_fail = models.BooleanField(default=False)
    latency_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scenario_key']
        indexes = [
            models.Index(fields=['run', 'passed']),
            models.Index(fields=['run', 'category']),
        ]

    def __str__(self):
        return f"{self.scenario_key} {'PASS' if self.passed else 'FAIL'}"


class NivaMetricSnapshot(models.Model):
    suite = models.ForeignKey(
        NivaEvalSuite,
        on_delete=models.CASCADE,
        related_name='metric_snapshots',
        null=True,
        blank=True,
    )
    run = models.ForeignKey(
        NivaEvalRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='metric_snapshots',
    )
    metric = models.CharField(max_length=80)
    value = models.FloatField()
    payload = models.JSONField(default=dict, blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-captured_at']
        indexes = [
            models.Index(fields=['metric', '-captured_at']),
        ]

    def __str__(self):
        return f"{self.metric}={self.value}"


# --- Niva v3 Phase 15: daily usage / cost tracking ---


class NivaUsageDaily(models.Model):
    """Per-user daily counters for chat, search, embeds, router calls."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_usage_daily',
    )
    day = models.DateField(db_index=True)
    chat_turns = models.PositiveIntegerField(default=0)
    search_calls = models.PositiveIntegerField(default=0)
    embed_calls = models.PositiveIntegerField(default=0)
    router_calls = models.PositiveIntegerField(default=0)
    approx_tokens = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'day'],
                name='unique_niva_usage_per_user_day',
            ),
        ]
        ordering = ['-day']

    def __str__(self):
        return f"usage {self.user_id} {self.day}"


# --- Niva v3 Phase 8: Activity event log ---


class NivaActivityEvent(models.Model):
    """User-scoped audit of Dayflow actions for companion recall (not NivaTrace)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='niva_activity_events',
    )
    kind = models.CharField(max_length=64)  # e.g. task.completed, transaction.created, digest.daily
    entity_type = models.CharField(max_length=40, blank=True, default='')
    entity_id = models.IntegerField(null=True, blank=True)
    summary = models.CharField(max_length=280)  # short English line
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'kind', '-created_at']),
            models.Index(fields=['user', 'entity_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.kind}: {self.summary[:60]}"
