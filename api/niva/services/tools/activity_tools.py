"""Activity recall tools — answer from NivaActivityEvent, never invent."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from api.niva.services.activity import (
    build_user_facing_summary,
    events_for_period,
    parse_period_from_message,
    summarize_events,
)


def get_activity(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    period = entities.get("period") or parse_period_from_message(message)
    kind = entities.get("kind") or entities.get("activity_kind")
    events, label = events_for_period(user, period=period, kind=kind, limit=80)
    stats = summarize_events(events)
    reply = build_user_facing_summary(events, label)
    return {
        "ok": True,
        "user_message": reply,
        "response_type": "activity_timeline",
        "data": {
            "period": label,
            "stats": stats,
            "events": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "entityType": e.entity_type,
                    "entityId": e.entity_id,
                    "summary": e.summary,
                    "createdAt": timezone.localtime(e.created_at).isoformat(),
                }
                for e in events[:40]
            ],
        },
        "actions": [],
    }
