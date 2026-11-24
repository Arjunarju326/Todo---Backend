# Niva v3 Phase 11 — reply language setting

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_niva_activity_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='nivacompanionsettings',
            name='reply_language',
            field=models.CharField(
                choices=[
                    ('auto', 'Auto (mirror user)'),
                    ('en', 'English'),
                    ('manglish', 'Manglish'),
                ],
                default='auto',
                max_length=20,
            ),
        ),
    ]
