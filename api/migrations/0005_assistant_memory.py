from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0004_user_ownership"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantMemory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("content", models.TextField()),
                ("tags", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("source_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistant_memories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="assistantmemory",
            index=models.Index(fields=["user", "is_active"], name="api_assista_user_id_mem_act_idx"),
        ),
        migrations.AddIndex(
            model_name="assistantmemory",
            index=models.Index(fields=["user", "-updated_at"], name="api_assista_user_id_mem_upd_idx"),
        ),
        migrations.AlterField(
            model_name="assistantchunk",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("TASK", "Task"),
                    ("HABIT", "Habit"),
                    ("LEARNING", "Learning"),
                    ("NOTE", "Note"),
                    ("KNOWLEDGE", "Knowledge"),
                    ("PROFILE", "Profile"),
                    ("MEMORY", "Memory"),
                ],
                max_length=20,
            ),
        ),
    ]
