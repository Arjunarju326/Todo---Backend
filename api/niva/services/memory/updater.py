"""Canonical memory upsert / consolidate for Niva v2."""

from __future__ import annotations

import re
from typing import Any

from django.utils import timezone

from api.models import AssistantMemory


def _fingerprint(title: str, content: str) -> str:
    blob = f"{title} {content}".lower()
    blob = re.sub(r"[^a-z0-9]+", " ", blob)
    return re.sub(r"\s+", " ", blob).strip()


def upsert_canonical_memory(
    *,
    user,
    title: str,
    content: str,
    key: str = "",
    category: str = "general",
    tags: list[str] | None = None,
    importance: int = 5,
    confidence: float = 1.0,
    explicit: bool = True,
    source_message: str = "",
    expires_at=None,
) -> tuple[AssistantMemory, str]:
    """Returns (memory, action) where action is ADD|UPDATE|IGNORE."""
    title = (title or "").strip()[:255]
    content = (content or "").strip()[:4000]
    key = (key or "").strip()[:150]
    tags = [str(t).strip()[:40] for t in (tags or []) if str(t).strip()][:8]
    if key and key not in tags:
        tags.append(key)

    if not title or not content:
        return None, "IGNORE"  # type: ignore

    existing = None
    qs = AssistantMemory.objects.filter(user=user, is_active=True, status="active")
    if key:
        existing = qs.filter(key=key).first()
    if not existing:
        existing = qs.filter(title__iexact=title).first()
    if not existing:
        fp = _fingerprint(title, content)
        for m in qs[:80]:
            if _fingerprint(m.title, m.content) == fp:
                existing = m
                break

    if existing:
        same = (
            _fingerprint(existing.title, existing.content)
            == _fingerprint(title, content)
            and (existing.key or "") == key
        )
        if same:
            return existing, "IGNORE"
        # Supersede near-duplicates with same key
        if key:
            for other in qs.filter(key=key).exclude(id=existing.id):
                other.status = "superseded"
                other.is_active = False
                other.save(update_fields=["status", "is_active", "updated_at"])
        existing.title = title
        existing.content = content
        existing.tags = tags
        existing.category = category or existing.category
        existing.key = key or existing.key
        existing.importance = importance
        existing.confidence = confidence
        existing.explicit = explicit
        existing.source_message = (source_message or "")[:2000]
        existing.expires_at = expires_at
        existing.status = "active"
        existing.is_active = True
        existing.save()
        _reindex_memory(existing)
        return existing, "UPDATE"

    mem = AssistantMemory.objects.create(
        user=user,
        title=title,
        content=content,
        tags=tags,
        category=category,
        key=key,
        importance=importance,
        confidence=confidence,
        explicit=explicit,
        source_message=(source_message or "")[:2000],
        expires_at=expires_at,
        status="active",
        is_active=True,
    )
    _reindex_memory(mem)
    return mem, "ADD"


def _reindex_memory(mem: AssistantMemory) -> None:
    try:
        from api.niva.services.rag.indexer import index_memory_document

        index_memory_document(mem, force_embed=True)
    except Exception:
        pass


def consolidate_user_memories(user) -> dict[str, int]:
    """Deactivate expired/duplicate memories."""
    now = timezone.now()
    expired = 0
    for m in AssistantMemory.objects.filter(user=user, is_active=True, expires_at__lt=now):
        m.is_active = False
        m.status = "archived"
        m.save(update_fields=["is_active", "status", "updated_at"])
        expired += 1

    dupes = 0
    seen: dict[str, AssistantMemory] = {}
    for m in AssistantMemory.objects.filter(user=user, is_active=True, status="active").order_by(
        "-updated_at"
    ):
        k = m.key or _fingerprint(m.title, m.content)
        if k in seen:
            m.is_active = False
            m.status = "superseded"
            m.save(update_fields=["is_active", "status", "updated_at"])
            dupes += 1
        else:
            seen[k] = m
    return {"expired": expired, "duplicates": dupes}
