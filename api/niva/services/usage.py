"""Per-user daily usage counters for cost control (chat / search / embeds / router)."""

from __future__ import annotations

import logging
from typing import Literal

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("niva.usage")

UsageKind = Literal["chat", "search", "embed", "router", "tokens"]


def _today():
    return timezone.localdate()


def record_usage(
    user,
    *,
    kind: UsageKind,
    amount: int = 1,
    approx_tokens: int = 0,
) -> None:
    if not user or not getattr(user, "id", None):
        return
    amount = max(0, int(amount or 0))
    approx_tokens = max(0, int(approx_tokens or 0))
    if amount == 0 and approx_tokens == 0:
        return
    try:
        from api.models import NivaUsageDaily

        obj, _ = NivaUsageDaily.objects.get_or_create(
            user=user,
            day=_today(),
            defaults={},
        )
        field_map = {
            "chat": "chat_turns",
            "search": "search_calls",
            "embed": "embed_calls",
            "router": "router_calls",
        }
        updates: dict = {}
        if kind in field_map and amount:
            updates[field_map[kind]] = F(field_map[kind]) + amount
        if approx_tokens:
            updates["approx_tokens"] = F("approx_tokens") + approx_tokens
        if updates:
            NivaUsageDaily.objects.filter(pk=obj.pk).update(**updates)
    except Exception as exc:
        logger.debug("usage record failed: %s", exc)


def get_usage_today(user) -> dict:
    if not user or not getattr(user, "id", None):
        return {}
    try:
        from api.models import NivaUsageDaily

        obj = NivaUsageDaily.objects.filter(user=user, day=_today()).first()
        if not obj:
            return {
                "day": _today().isoformat(),
                "chatTurns": 0,
                "searchCalls": 0,
                "embedCalls": 0,
                "routerCalls": 0,
                "approxTokens": 0,
            }
        return {
            "day": obj.day.isoformat(),
            "chatTurns": obj.chat_turns,
            "searchCalls": obj.search_calls,
            "embedCalls": obj.embed_calls,
            "routerCalls": obj.router_calls,
            "approxTokens": obj.approx_tokens,
        }
    except Exception:
        return {}
