"""Activity event log — source of truth for “what did I do?”."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from api.models import NivaActivityEvent

logger = logging.getLogger(__name__)

# Avoid recursive/noisy logging while writing digests or bulk imports
_SUPPRESS = False


def suppress_activity_logging(enabled: bool = True) -> None:
    global _SUPPRESS
    _SUPPRESS = enabled


def record_event(
    *,
    user,
    kind: str,
    summary: str,
    entity_type: str = "",
    entity_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> NivaActivityEvent | None:
    if _SUPPRESS or user is None or not getattr(user, "id", None):
        return None
    summary = (summary or "").strip()[:280]
    if not summary:
        return None
    try:
        return NivaActivityEvent.objects.create(
            user=user,
            kind=(kind or "unknown")[:64],
            entity_type=(entity_type or "")[:40],
            entity_id=entity_id,
            summary=summary,
            payload=payload or {},
        )
    except Exception:
        logger.exception("Failed to record NivaActivityEvent kind=%s", kind)
        return None


def _period_bounds(period: str, *, now=None) -> tuple[datetime, datetime, str]:
    """Return (start, end, label) in local time, timezone-aware."""
    now = now or timezone.localtime()
    today = now.date()
    period = (period or "today").strip().lower().replace(" ", "_").replace("-", "_")

    def day_range(d):
        start = timezone.make_aware(datetime.combine(d, datetime.min.time()))
        end = start + timedelta(days=1)
        return start, end

    if period in ("today", "innu"):
        start, end = day_range(today)
        return start, end, "today"
    if period in ("yesterday", "innale"):
        start, end = day_range(today - timedelta(days=1))
        return start, end, "yesterday"
    if period in ("this_week", "week", "ee_aazhcha", "ee_azhcha"):
        # Monday-start week
        start_d = today - timedelta(days=today.weekday())
        start, _ = day_range(start_d)
        end = day_range(today)[1]
        return start, end, "this week"
    if period in ("last_week", "kazhinja_aazhcha", "kazhinja_azhcha"):
        start_d = today - timedelta(days=today.weekday() + 7)
        end_d = start_d + timedelta(days=7)
        start, _ = day_range(start_d)
        end, _ = day_range(end_d)
        return start, end, "last week"
    if period in ("this_month", "month", "ee_maasam"):
        start_d = today.replace(day=1)
        start, _ = day_range(start_d)
        end = day_range(today)[1]
        return start, end, "this month"
    # Default: last 7 days inclusive
    start, _ = day_range(today - timedelta(days=6))
    end = day_range(today)[1]
    return start, end, "the last 7 days"


def parse_period_from_message(message: str) -> str:
    lower = (message or "").lower()
    if any(k in lower for k in ("innale", "yesterday")):
        return "yesterday"
    if any(k in lower for k in ("kazhinja aazhcha", "kazhinja azhcha", "last week")):
        return "last week"
    if any(k in lower for k in ("ee maasam", "this month", "ee masam")):
        return "this month"
    if any(k in lower for k in ("ee aazhcha", "ee azhcha", "this week", "past week")):
        return "this week"
    if any(k in lower for k in ("innu", "today")):
        return "today"
    return "today"


def events_for_period(
    user,
    *,
    period: str = "today",
    kind: str | None = None,
    include_digests: bool = False,
    limit: int = 80,
) -> tuple[list[NivaActivityEvent], str]:
    start, end, label = _period_bounds(period)
    qs: QuerySet = NivaActivityEvent.objects.filter(
        user=user,
        created_at__gte=start,
        created_at__lt=end,
    )
    if not include_digests:
        qs = qs.exclude(kind="digest.daily")
    if kind:
        kind = kind.strip()
        if "." in kind:
            qs = qs.filter(kind=kind)
        else:
            qs = qs.filter(Q(kind=kind) | Q(kind__startswith=f"{kind}."))
    rows = list(qs.order_by("-created_at")[:limit])
    return rows, label


def summarize_events(events: list[NivaActivityEvent]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for e in events:
        root = (e.kind or "other").split(".", 1)[0]
        counts[root] = counts.get(root, 0) + 1
    return {
        "total": len(events),
        "by_entity": counts,
        "task_completed": sum(1 for e in events if e.kind == "task.completed"),
        "transactions": sum(1 for e in events if e.kind.startswith("transaction.")),
        "habit_logs": sum(1 for e in events if e.kind == "habit.logged"),
        "notes": sum(1 for e in events if e.kind.startswith("note.")),
        "goals": sum(1 for e in events if e.kind.startswith("goal.")),
    }


def build_user_facing_summary(events: list[NivaActivityEvent], period_label: str) -> str:
    if not events:
        return f"I don’t see any logged Dayflow activity for {period_label}."
    stats = summarize_events(events)
    bits: list[str] = []
    if stats["task_completed"]:
        bits.append(f"finished {stats['task_completed']} task(s)")
    task_other = stats["by_entity"].get("task", 0) - stats["task_completed"]
    if task_other > 0:
        bits.append(f"updated {task_other} other task action(s)")
    if stats["transactions"]:
        bits.append(f"logged {stats['transactions']} transaction(s)")
    if stats["habit_logs"]:
        bits.append(f"kept {stats['habit_logs']} habit check-in(s)")
    if stats["goals"]:
        bits.append(f"touched {stats['goals']} goal update(s)")
    if stats["notes"]:
        bits.append(f"wrote {stats['notes']} note action(s)")
    if not bits:
        bits.append(f"{stats['total']} action(s)")
    head = f"For {period_label}, you " + ", ".join(bits) + "."
    recent_lines = []
    for e in events[:8]:
        when = timezone.localtime(e.created_at).strftime("%H:%M")
        recent_lines.append(f"• {when} — {e.summary}")
    return head + "\n\nRecent:\n" + "\n".join(recent_lines)


def build_daily_digest_line(events: list[NivaActivityEvent], day_label: str) -> str:
    stats = summarize_events(events)
    if not events:
        return f"{day_label}: no Dayflow activity logged."
    parts = [f"{day_label}: {stats['total']} actions"]
    if stats["task_completed"]:
        parts.append(f"{stats['task_completed']} tasks done")
    if stats["transactions"]:
        parts.append(f"{stats['transactions']} money logs")
    if stats["habit_logs"]:
        parts.append(f"{stats['habit_logs']} habit logs")
    if stats["notes"]:
        parts.append(f"{stats['notes']} note edits")
    if stats["goals"]:
        parts.append(f"{stats['goals']} goal updates")
    return "; ".join(parts) + "."


def write_daily_digest_for_user(user, *, day=None) -> NivaActivityEvent | None:
    """Idempotent: one digest.daily per user per calendar day."""
    day = day or (timezone.localdate() - timedelta(days=1))
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    end = start + timedelta(days=1)
    existing = NivaActivityEvent.objects.filter(
        user=user,
        kind="digest.daily",
        created_at__gte=start,
        created_at__lt=end + timedelta(hours=12),  # digest may be written next morning
        payload__digest_date=day.isoformat(),
    ).first()
    if existing:
        return existing

    events = list(
        NivaActivityEvent.objects.filter(
            user=user,
            created_at__gte=start,
            created_at__lt=end,
        )
        .exclude(kind="digest.daily")
        .order_by("created_at")[:200]
    )
    label = day.isoformat()
    summary = build_daily_digest_line(events, label)
    suppress_activity_logging(True)
    try:
        return NivaActivityEvent.objects.create(
            user=user,
            kind="digest.daily",
            entity_type="digest",
            entity_id=None,
            summary=summary[:280],
            payload={
                "digest_date": day.isoformat(),
                "event_count": len(events),
                "stats": summarize_events(events),
            },
        )
    finally:
        suppress_activity_logging(False)


def run_daily_digests(*, for_day=None) -> dict[str, int]:
    """Write yesterday's (or for_day) digests for users who had activity."""
    from django.contrib.auth import get_user_model

    day = for_day or (timezone.localdate() - timedelta(days=1))
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    end = start + timedelta(days=1)
    User = get_user_model()
    user_ids = (
        NivaActivityEvent.objects.filter(created_at__gte=start, created_at__lt=end)
        .exclude(kind="digest.daily")
        .values_list("user_id", flat=True)
        .distinct()
    )
    written = 0
    skipped = 0
    for uid in user_ids:
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        before = NivaActivityEvent.objects.filter(
            user=user, kind="digest.daily", payload__digest_date=day.isoformat()
        ).exists()
        ev = write_daily_digest_for_user(user, day=day)
        if before:
            skipped += 1
        elif ev:
            written += 1
    return {"written": written, "skipped": skipped, "day": day.isoformat()}
