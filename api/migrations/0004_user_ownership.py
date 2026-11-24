# Generated manually for per-user data isolation

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


OWNER_USERNAME = "arju"
OWNER_PASSWORD = "arjuoo"
OWNER_DISPLAY = "Arjun"


def assign_existing_data(apps, schema_editor):
    User = apps.get_model("auth", "User")
    owner, created = User.objects.get_or_create(
        username=OWNER_USERNAME,
        defaults={
            "email": "arjuoo@dayflow.app",
            "first_name": OWNER_DISPLAY,
            "is_staff": False,
            "is_superuser": False,
        },
    )
    if created or True:
        # Password hashing via set_password isn't available on historical models;
        # set a usable flag and update password in a follow-up shell on deploy.
        # Keep created user; password set in RunPython after with real User model.
        pass

    # Prefer renaming legacy default user into owner if arjuoo was just created empty
    legacy = User.objects.filter(username="arjun").exclude(pk=owner.pk).first()
    if legacy and created:
        # Move ownership name: keep arjun's pk as owner by renaming
        # Simpler: assign all data to arjuoo user we created; leave arjun for later disable.
        pass

    model_names = [
        "Task",
        "Transaction",
        "Debt",
        "Bill",
        "Habit",
        "LearningGoal",
        "JobApplication",
        "Note",
        "AssistantChunk",
        "AssistantBrief",
    ]
    for name in model_names:
        Model = apps.get_model("api", name)
        Model.objects.filter(user__isnull=True).update(user_id=owner.pk)

    # Deduplicate daily briefs before unique(user, brief_date) is enforced
    AssistantBrief = apps.get_model("api", "AssistantBrief")
    seen_dates = set()
    for brief in AssistantBrief.objects.filter(user_id=owner.pk).order_by("-updated_at", "-id"):
        if brief.brief_date in seen_dates:
            brief.delete()
        else:
            seen_dates.add(brief.brief_date)

    UserSettings = apps.get_model("api", "UserSettings")
    settings_rows = list(UserSettings.objects.order_by("id"))
    if settings_rows:
        primary = settings_rows[0]
        primary.user_id = owner.pk
        if not primary.user_name:
            primary.user_name = OWNER_DISPLAY
        primary.save()
        # Drop extra singleton rows (shared leftovers)
        UserSettings.objects.exclude(pk=primary.pk).delete()
    else:
        UserSettings.objects.create(
            user_id=owner.pk,
            user_name=OWNER_DISPLAY,
            monthly_income=0,
            monthly_emi_commitment=0,
            savings_target=0,
            currency="₹",
            timezone="Asia/Kolkata",
        )


def set_owner_password(apps, schema_editor):
    # Use real auth User for password hashing
    from django.contrib.auth.models import User

    user, _ = User.objects.get_or_create(
        username=OWNER_USERNAME,
        defaults={
            "email": "arjuoo@dayflow.app",
            "first_name": OWNER_DISPLAY,
        },
    )
    user.set_password(OWNER_PASSWORD)
    user.first_name = user.first_name or OWNER_DISPLAY
    user.save()

    # Disable legacy shared login so only arjuoo keeps the data
    for legacy_name in ("arjun", "admin"):
        legacy = User.objects.filter(username=legacy_name).exclude(pk=user.pk).first()
        if legacy:
            # Keep admin for django admin if needed; only retire arjun demo login
            if legacy_name == "arjun":
                legacy.is_active = False
                legacy.save(update_fields=["is_active"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0003_assistant_chunk_brief"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transactions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="debt",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="debts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="bill",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bills",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="habit",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="habits",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="learninggoal",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="learning_goals",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="jobapplication",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="job_applications",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="note",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="usersettings",
            name="user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="settings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="assistantchunk",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assistant_chunks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="assistantbrief",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assistant_briefs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="assistantbrief",
            name="brief_date",
            field=models.DateField(),
        ),
        migrations.RunPython(assign_existing_data, noop_reverse),
        migrations.RunPython(set_owner_password, noop_reverse),
        migrations.AddConstraint(
            model_name="assistantbrief",
            constraint=models.UniqueConstraint(
                fields=("user", "brief_date"),
                name="unique_assistant_brief_per_user_date",
            ),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["user", "status"], name="api_task_user_id_status_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["user", "date"], name="api_trans_user_id_date_idx"),
        ),
        migrations.AddIndex(
            model_name="debt",
            index=models.Index(fields=["user", "status"], name="api_debt_user_id_status_idx"),
        ),
        migrations.AddIndex(
            model_name="bill",
            index=models.Index(fields=["user", "is_active"], name="api_bill_user_id_active_idx"),
        ),
        migrations.AddIndex(
            model_name="habit",
            index=models.Index(fields=["user"], name="api_habit_user_id_idx"),
        ),
        migrations.AddIndex(
            model_name="learninggoal",
            index=models.Index(fields=["user", "status"], name="api_learn_user_id_status_idx"),
        ),
        migrations.AddIndex(
            model_name="jobapplication",
            index=models.Index(fields=["user", "status"], name="api_job_user_id_status_idx"),
        ),
        migrations.AddIndex(
            model_name="note",
            index=models.Index(fields=["user", "is_pinned"], name="api_note_user_id_pin_idx"),
        ),
        migrations.AddIndex(
            model_name="assistantchunk",
            index=models.Index(
                fields=["user", "source_type"],
                name="api_chunk_user_id_stype_idx",
            ),
        ),
    ]
