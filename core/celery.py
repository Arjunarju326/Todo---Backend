import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

try:
    from celery import Celery

    app = Celery("dayflow")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks(lambda: ["api.niva"])
except ImportError:
    app = None
