# Generated manually for Niva v3 Phase 8 — Activity Event Log

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0007_niva_intelligence_lab'),
    ]

    operations = [
        migrations.CreateModel(
            name='NivaActivityEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=64)),
                ('entity_type', models.CharField(blank=True, default='', max_length=40)),
                ('entity_id', models.IntegerField(blank=True, null=True)),
                ('summary', models.CharField(max_length=280)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='niva_activity_events',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='nivaactivityevent',
            index=models.Index(fields=['user', '-created_at'], name='api_nivaact_user_id_c_idx'),
        ),
        migrations.AddIndex(
            model_name='nivaactivityevent',
            index=models.Index(fields=['user', 'kind', '-created_at'], name='api_nivaact_user_kind_idx'),
        ),
        migrations.AddIndex(
            model_name='nivaactivityevent',
            index=models.Index(fields=['user', 'entity_type', '-created_at'], name='api_nivaact_user_ent_idx'),
        ),
    ]
