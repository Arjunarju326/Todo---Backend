from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_bill"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantChunk",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("source_type", models.CharField(max_length=20)),
                ("source_id", models.CharField(blank=True, default="", max_length=64)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("content", models.TextField()),
                ("embedding", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="AssistantBrief",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("brief_date", models.DateField(unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="assistantchunk",
            index=models.Index(
                fields=["source_type", "source_id"],
                name="api_assista_source__7f1b2a_idx",
            ),
        ),
    ]
