# Niva v3 Phase 14 — companion nudge settings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_niva_reply_language'),
    ]

    operations = [
        migrations.AddField(
            model_name='nivacompanionsettings',
            name='spend_alerts_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='nivacompanionsettings',
            name='overdue_nudge_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='nivacompanionsettings',
            name='last_overdue_nudge_on',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='nivacompanionsettings',
            name='last_spend_alert_on',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='nivacompanionsettings',
            name='last_weekly_review_on',
            field=models.DateField(blank=True, null=True),
        ),
    ]
