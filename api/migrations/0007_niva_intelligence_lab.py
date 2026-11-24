# Generated manually for Niva Intelligence Lab (Sprint 1)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0006_niva_v2_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='NivaEvalSuite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=80, unique=True)),
                ('name', models.CharField(max_length=160)),
                ('version', models.CharField(default='1.0', max_length=40)),
                ('description', models.TextField(blank=True, default='')),
                ('scenario_count', models.IntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['slug']},
        ),
        migrations.CreateModel(
            name='NivaTrace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_id', models.CharField(db_index=True, max_length=64)),
                ('source', models.CharField(choices=[('prod', 'Production'), ('eval', 'Evaluation')], default='prod', max_length=10)),
                ('message_preview', models.CharField(blank=True, default='', max_length=240)),
                ('message_hash', models.CharField(blank=True, default='', max_length=64)),
                ('primary_intent', models.CharField(blank=True, default='', max_length=64)),
                ('intent_confidence', models.FloatField(blank=True, null=True)),
                ('tools', models.JSONField(blank=True, default=list)),
                ('response_type', models.CharField(blank=True, default='', max_length=64)),
                ('conversation_id', models.IntegerField(blank=True, null=True)),
                ('model_name', models.CharField(blank=True, default='', max_length=120)),
                ('latency_ms', models.IntegerField(blank=True, null=True)),
                ('llm_latency_ms', models.IntegerField(blank=True, null=True)),
                ('tool_latency_ms', models.IntegerField(blank=True, null=True)),
                ('memory_count', models.IntegerField(default=0)),
                ('search_count', models.IntegerField(default=0)),
                ('token_usage', models.JSONField(blank=True, default=dict)),
                ('success', models.BooleanField(default=True)),
                ('error_status', models.CharField(blank=True, default='', max_length=120)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='niva_traces', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='NivaEvalScenario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scenario_id', models.CharField(max_length=32)),
                ('category', models.CharField(db_index=True, max_length=40)),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('input_text', models.TextField()),
                ('history', models.JSONField(blank=True, default=list)),
                ('fixtures', models.JSONField(blank=True, default=dict)),
                ('expect', models.JSONField(blank=True, default=dict)),
                ('weight', models.FloatField(default=1.0)),
                ('tags', models.JSONField(blank=True, default=list)),
                ('is_active', models.BooleanField(default=True)),
                ('suite', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scenarios', to='api.nivaevalsuite')),
            ],
            options={'ordering': ['scenario_id']},
        ),
        migrations.CreateModel(
            name='NivaEvalRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(blank=True, default='', max_length=160)),
                ('mode', models.CharField(default='intent', max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('aggregate', models.JSONField(blank=True, default=dict)),
                ('meta', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='niva_eval_runs', to=settings.AUTH_USER_MODEL)),
                ('suite', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='runs', to='api.nivaevalsuite')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='NivaEvalResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scenario_key', models.CharField(max_length=32)),
                ('category', models.CharField(blank=True, default='', max_length=40)),
                ('passed', models.BooleanField(default=False)),
                ('score', models.FloatField(default=0.0)),
                ('weight', models.FloatField(default=1.0)),
                ('metrics', models.JSONField(blank=True, default=dict)),
                ('actual', models.JSONField(blank=True, default=dict)),
                ('diffs', models.JSONField(blank=True, default=list)),
                ('critical_fail', models.BooleanField(default=False)),
                ('latency_ms', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='api.nivaevalrun')),
                ('scenario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='results', to='api.nivaevalscenario')),
            ],
            options={'ordering': ['scenario_key']},
        ),
        migrations.CreateModel(
            name='NivaMetricSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric', models.CharField(max_length=80)),
                ('value', models.FloatField()),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('captured_at', models.DateTimeField(auto_now_add=True)),
                ('run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='metric_snapshots', to='api.nivaevalrun')),
                ('suite', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='metric_snapshots', to='api.nivaevalsuite')),
            ],
            options={'ordering': ['-captured_at']},
        ),
        migrations.AddIndex(
            model_name='nivatrace',
            index=models.Index(fields=['source', '-created_at'], name='api_nivatrace_source_idx'),
        ),
        migrations.AddIndex(
            model_name='nivatrace',
            index=models.Index(fields=['primary_intent', '-created_at'], name='api_nivatrace_intent_idx'),
        ),
        migrations.AddIndex(
            model_name='nivatrace',
            index=models.Index(fields=['user', '-created_at'], name='api_nivatrace_user_idx'),
        ),
        migrations.AddIndex(
            model_name='nivaevalscenario',
            index=models.Index(fields=['suite', 'category'], name='api_nivaevalsc_suite_cat_idx'),
        ),
        migrations.AddConstraint(
            model_name='nivaevalscenario',
            constraint=models.UniqueConstraint(fields=('suite', 'scenario_id'), name='unique_niva_eval_scenario_per_suite'),
        ),
        migrations.AddIndex(
            model_name='nivaevalresult',
            index=models.Index(fields=['run', 'passed'], name='api_nivaevalres_run_pass_idx'),
        ),
        migrations.AddIndex(
            model_name='nivaevalresult',
            index=models.Index(fields=['run', 'category'], name='api_nivaevalres_run_cat_idx'),
        ),
        migrations.AddIndex(
            model_name='nivametricsnapshot',
            index=models.Index(fields=['metric', '-captured_at'], name='api_nivametric_metric_idx'),
        ),
    ]
