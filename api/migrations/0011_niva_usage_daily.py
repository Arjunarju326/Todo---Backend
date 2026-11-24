# Niva v3 Phase 15 — daily usage tracking

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0010_niva_companion_nudges'),
    ]

    operations = [
        migrations.CreateModel(
            name='NivaUsageDaily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(db_index=True)),
                ('chat_turns', models.PositiveIntegerField(default=0)),
                ('search_calls', models.PositiveIntegerField(default=0)),
                ('embed_calls', models.PositiveIntegerField(default=0)),
                ('router_calls', models.PositiveIntegerField(default=0)),
                ('approx_tokens', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='niva_usage_daily',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-day']},
        ),
        migrations.AddConstraint(
            model_name='nivausagedaily',
            constraint=models.UniqueConstraint(
                fields=('user', 'day'),
                name='unique_niva_usage_per_user_day',
            ),
        ),
    ]
