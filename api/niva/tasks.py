"""Proactive companion jobs.

Uses Celery when available; otherwise functions can be invoked via
`python manage.py niva_proactive` or a cron hitting the same helpers.
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone


def _in_quiet_hours(settings_obj, now) -> bool:
    start = settings_obj.quiet_hours_start
    end = settings_obj.quiet_hours_end
    if not start or not end:
        return False
    t = now.time()
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def _profile(user):
    try:
        from api.assistant_service import get_profile

        return get_profile(user)
    except Exception:
        return {"user_name": "there"}


def run_morning_briefings() -> dict:
    from api.models import NivaCompanionSettings
    from api.niva.services.companion import build_morning_checkin

    now = timezone.localtime()
    sent = 0
    skipped = 0
    for s in NivaCompanionSettings.objects.filter(
        morning_briefing_enabled=True, proactive_enabled=True
    ).select_related("user"):
        if _in_quiet_hours(s, now):
            skipped += 1
            continue
        if s.morning_briefing_time:
            target = datetime.combine(now.date(), s.morning_briefing_time)
            if abs((now.replace(tzinfo=None) - target).total_seconds()) > 15 * 60:
                continue
        try:
            build_morning_checkin(s.user, profile=_profile(s.user))
            # Also refresh classic briefing cache for Smrti popup
            try:
                from api.assistant_service import generate_briefing

                generate_briefing(force_refresh=True, user=s.user)
            except Exception:
                pass
            sent += 1
        except Exception:
            skipped += 1
    return {"sent": sent, "skipped": skipped}


def run_evening_reviews() -> dict:
    from api.models import NivaCompanionSettings
    from api.niva.services.companion import build_evening_checkin

    now = timezone.localtime()
    sent = 0
    for s in NivaCompanionSettings.objects.filter(
        evening_review_enabled=True, proactive_enabled=True
    ).select_related("user"):
        if _in_quiet_hours(s, now):
            continue
        if s.evening_review_time:
            target = datetime.combine(now.date(), s.evening_review_time)
            if abs((now.replace(tzinfo=None) - target).total_seconds()) > 15 * 60:
                continue
        try:
            build_evening_checkin(s.user, profile=_profile(s.user))
            sent += 1
        except Exception:
            pass
    return {"sent": sent}


def run_weekly_reviews() -> dict:
    from api.models import NivaCompanionSettings
    from api.niva.services.companion import build_weekly_review

    now = timezone.localtime()
    today = now.date()
    sent = 0
    skipped = 0
    for s in NivaCompanionSettings.objects.filter(
        weekly_review_enabled=True, proactive_enabled=True
    ).select_related("user"):
        if _in_quiet_hours(s, now):
            skipped += 1
            continue
        weekday = getattr(s, "weekly_review_weekday", 6)
        if now.weekday() != int(weekday or 6):
            continue
        if s.last_weekly_review_on == today:
            skipped += 1
            continue
        try:
            build_weekly_review(s.user, profile=_profile(s.user))
            s.last_weekly_review_on = today
            s.save(update_fields=["last_weekly_review_on", "updated_at"])
            sent += 1
        except Exception:
            skipped += 1
    return {"sent": sent, "skipped": skipped}


def run_overdue_nudges() -> dict:
    from api.models import NivaCompanionSettings
    from api.niva.services.companion import overdue_nudge

    now = timezone.localtime()
    today = now.date()
    sent = 0
    skipped = 0
    for s in NivaCompanionSettings.objects.filter(
        overdue_nudge_enabled=True, proactive_enabled=True
    ).select_related("user"):
        if _in_quiet_hours(s, now):
            skipped += 1
            continue
        if s.last_overdue_nudge_on == today:
            skipped += 1
            continue
        try:
            payload = overdue_nudge(s.user, settings_obj=s, profile=_profile(s.user))
            if not payload:
                skipped += 1
                continue
            s.last_overdue_nudge_on = today
            s.save(update_fields=["last_overdue_nudge_on", "updated_at"])
            sent += 1
        except Exception:
            skipped += 1
    return {"sent": sent, "skipped": skipped}


def run_spend_alerts() -> dict:
    from api.models import NivaCompanionSettings
    from api.niva.services.companion import spend_alert

    now = timezone.localtime()
    today = now.date()
    sent = 0
    skipped = 0
    for s in NivaCompanionSettings.objects.filter(
        spend_alerts_enabled=True, proactive_enabled=True
    ).select_related("user"):
        if _in_quiet_hours(s, now):
            skipped += 1
            continue
        if s.last_spend_alert_on == today:
            skipped += 1
            continue
        try:
            payload = spend_alert(s.user, profile=_profile(s.user))
            if not payload:
                skipped += 1
                continue
            s.last_spend_alert_on = today
            s.save(update_fields=["last_spend_alert_on", "updated_at"])
            sent += 1
        except Exception:
            skipped += 1
    return {"sent": sent, "skipped": skipped}


def run_memory_consolidation() -> dict:
    from api.models import NivaCompanionSettings
    from api.niva.services.memory.updater import consolidate_user_memories

    total = {"expired": 0, "duplicates": 0}
    for s in NivaCompanionSettings.objects.select_related("user"):
        stats = consolidate_user_memories(s.user)
        total["expired"] += stats.get("expired", 0)
        total["duplicates"] += stats.get("duplicates", 0)
    return total


def run_activity_digests() -> dict:
    """Summarize yesterday's activity events into one digest line per user."""
    from api.niva.services.activity import run_daily_digests

    return run_daily_digests()


# Optional Celery bindings
try:
    from celery import shared_task

    @shared_task(name="niva.morning_briefings")
    def celery_morning_briefings():
        return run_morning_briefings()

    @shared_task(name="niva.evening_reviews")
    def celery_evening_reviews():
        return run_evening_reviews()

    @shared_task(name="niva.consolidate_memories")
    def celery_consolidate_memories():
        return run_memory_consolidation()

    @shared_task(name="niva.activity_digests")
    def celery_activity_digests():
        return run_activity_digests()

    @shared_task(name="niva.weekly_reviews")
    def celery_weekly_reviews():
        return run_weekly_reviews()

    @shared_task(name="niva.overdue_nudges")
    def celery_overdue_nudges():
        return run_overdue_nudges()

    @shared_task(name="niva.spend_alerts")
    def celery_spend_alerts():
        return run_spend_alerts()

except ImportError:
    pass
