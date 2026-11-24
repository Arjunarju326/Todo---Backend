"""Tavily client with optional DB cache."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from django.utils import timezone

from api.assistant_service import tavily_search as _raw_tavily
from api.models import NivaResearchCache


def search(
    query: str,
    *,
    user=None,
    topic: str = "general",
    max_results: int = 5,
    cache_ttl_minutes: int = 30,
) -> dict[str, Any] | None:
    q = (query or "").strip()
    if not q:
        return None
    qh = hashlib.sha256(f"{topic}:{q.lower()}".encode()).hexdigest()
    now = timezone.now()
    cached = (
        NivaResearchCache.objects.filter(query_hash=qh, expires_at__gt=now)
        .order_by("-created_at")
        .first()
    )
    if cached and isinstance(cached.payload, dict):
        return {**cached.payload, "cached": True}

    data = _raw_tavily(q, topic=topic, max_results=max_results, search_depth="basic")
    if not data:
        return None
    try:
        from api.niva.services.usage import record_usage

        record_usage(user, kind="search", amount=1)
    except Exception:
        pass
    try:
        NivaResearchCache.objects.create(
            user=user,
            query_hash=qh,
            query=q[:500],
            payload=data,
            expires_at=now + timedelta(minutes=cache_ttl_minutes),
        )
    except Exception:
        pass
    return data
