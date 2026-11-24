"""Ranked memory retrieval — hybrid RAG + keyword, relevance over dumps."""

from __future__ import annotations

import re
from typing import Any

from django.utils import timezone

from api.models import AssistantMemory


def _score(
    query: str,
    memory: AssistantMemory,
    *,
    wanted_categories: list[str] | None = None,
) -> float:
    q = (query or "").lower()
    blob = f"{memory.title} {memory.content} {' '.join(memory.tags or [])}".lower()
    relevance = 0.0
    if q and q in blob:
        relevance += 1.0
    tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    stop = {"the", "and", "for", "you", "what", "where", "who", "how", "are", "is", "my", "me"}
    hits = sum(1 for t in tokens if t not in stop and t in blob)
    if tokens:
        relevance += min(1.0, hits / max(1, len([t for t in tokens if t not in stop])))

    if wanted_categories and memory.category in wanted_categories:
        relevance = min(1.0, relevance + 0.25)
    if memory.key and memory.key.lower() in q:
        relevance = min(1.0, relevance + 0.35)

    importance = min(1.0, max(0.0, (memory.importance or 5) / 10.0))
    confidence = min(1.0, max(0.0, float(memory.confidence or 1.0)))
    age_days = 0.0
    if memory.updated_at:
        age_days = max(0.0, (timezone.now() - memory.updated_at).total_seconds() / 86400.0)
    temporal = max(0.0, 1.0 - min(age_days, 90) / 90.0)
    explicit = 1.0 if memory.explicit else 0.4

    return (
        0.40 * relevance
        + 0.20 * importance
        + 0.15 * confidence
        + 0.15 * temporal
        + 0.10 * explicit
    )


def _keyword_rank(
    query: str,
    user=None,
    *,
    limit: int = 5,
    categories: list[str] | None = None,
    min_score: float = 0.35,
) -> list[AssistantMemory]:
    now = timezone.now()
    qs = AssistantMemory.objects.filter(user=user, is_active=True, status="active")
    rows = list(qs[:100])
    scored: list[tuple[float, AssistantMemory]] = []
    for m in rows:
        if m.expires_at and m.expires_at < now:
            continue
        if categories and m.category not in categories and m.category != "general":
            s = _score(query, m, wanted_categories=categories)
            if s < 0.55:
                continue
        else:
            s = _score(query, m, wanted_categories=categories)
        if s >= min_score:
            scored.append((s, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:limit]]


def _memories_from_rag_hits(hits, user) -> list[AssistantMemory]:
    """Map RAG MEMORY / LEARNING_NOTE chunks back to AssistantMemory rows."""
    ids: list[int] = []
    for h in hits:
        meta = h.chunk.metadata if isinstance(h.chunk.metadata, dict) else {}
        mid = meta.get("memory_id")
        if mid is None:
            sid = (h.chunk.source_id or "").split("#")[0]
            if sid.isdigit():
                mid = int(sid)
        if mid is not None:
            try:
                ids.append(int(mid))
            except (TypeError, ValueError):
                pass
    if not ids:
        return []
    by_id = {
        m.id: m
        for m in AssistantMemory.objects.filter(
            user=user, id__in=ids, is_active=True, status="active"
        )
    }
    out: list[AssistantMemory] = []
    seen = set()
    for mid in ids:
        if mid in seen:
            continue
        m = by_id.get(mid)
        if m:
            out.append(m)
            seen.add(mid)
    return out


def rank_and_retrieve(
    query: str,
    user=None,
    *,
    limit: int = 5,
    categories: list[str] | None = None,
    min_score: float = 0.35,
) -> list[AssistantMemory]:
    """
    Hybrid path: vector RAG chunks (top 3–5) merged with keyword memory rank.
    Prefer RAG hits when embeddings exist; always cap at `limit`.
    """
    limit = max(1, min(limit, 5))
    now = timezone.now()
    rag_memories: list[AssistantMemory] = []
    try:
        from api.niva.services.rag.retrieve import hybrid_retrieve
        from api.models import AssistantSourceType

        types = [
            AssistantSourceType.MEMORY,
            AssistantSourceType.LEARNING_NOTE,
            AssistantSourceType.NOTE,
            AssistantSourceType.JOURNAL,
            AssistantSourceType.SUMMARY,
        ]
        hits = hybrid_retrieve(
            query,
            user=user,
            limit=limit,
            source_types=types,
            min_score=0.16,
        )
        rag_memories = _memories_from_rag_hits(hits, user)
    except Exception:
        rag_memories = []

    keyword = _keyword_rank(
        query, user, limit=limit, categories=categories, min_score=min_score
    )

    merged: list[AssistantMemory] = []
    seen: set[int] = set()
    for m in rag_memories + keyword:
        if m.id in seen:
            continue
        if m.expires_at and m.expires_at < now:
            continue
        merged.append(m)
        seen.add(m.id)
        if len(merged) >= limit:
            break

    for m in merged:
        try:
            m.last_accessed = now
            m.save(update_fields=["last_accessed"])
        except Exception:
            pass
    return merged


def memories_as_context(memories: list[AssistantMemory]) -> str:
    if not memories:
        return ""
    lines = [f"- [{m.category}:{m.key or 'fact'}] {m.title}: {m.content[:200]}" for m in memories]
    return "Relevant personal memories:\n" + "\n".join(lines)
