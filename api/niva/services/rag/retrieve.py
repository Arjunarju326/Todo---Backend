"""Hybrid keyword + vector retrieval with recency / importance ranking."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from api.models import AssistantChunk, AssistantSourceType
from api.niva.services.rag.indexer import FREE_TEXT_TYPES


@dataclass
class RagHit:
    chunk: AssistantChunk
    score: float
    vector_score: float
    keyword_score: float
    rank_features: dict[str, float]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _keyword_score(query: str, title: str, content: str) -> float:
    q = (query or "").lower()
    blob = f"{title} {content}".lower()
    if not q or not blob:
        return 0.0
    score = 0.0
    if q in blob:
        score += 1.0
    tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    stop = {"the", "and", "for", "you", "what", "where", "who", "how", "are", "is", "my", "me", "did", "about"}
    useful = [t for t in tokens if t not in stop]
    if useful:
        hits = sum(1 for t in useful if t in blob)
        score += min(1.0, hits / max(1, len(useful)))
    return min(1.0, score)


def _parse_meta_date(meta: dict[str, Any]) -> datetime | None:
    raw = meta.get("date") or meta.get("indexed_at")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return parse_datetime(str(raw))
    except Exception:
        return None


def _recency_score(chunk: AssistantChunk) -> float:
    meta = chunk.metadata if isinstance(chunk.metadata, dict) else {}
    dt = _parse_meta_date(meta) or chunk.updated_at or chunk.created_at
    if not dt:
        return 0.5
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    age_days = max(0.0, (timezone.now() - dt).total_seconds() / 86400.0)
    return max(0.0, 1.0 - min(age_days, 120) / 120.0)


def _importance_score(chunk: AssistantChunk) -> float:
    meta = chunk.metadata if isinstance(chunk.metadata, dict) else {}
    try:
        imp = float(meta.get("importance", 5))
    except (TypeError, ValueError):
        imp = 5.0
    return min(1.0, max(0.0, imp / 10.0))


def hybrid_retrieve(
    query: str,
    *,
    user=None,
    limit: int = 5,
    source_types: list[str] | None = None,
    min_score: float = 0.18,
) -> list[RagHit]:
    """
    Hybrid: vector cosine + keyword, then blend recency + importance.
    Returns top 3–5 chunks by default. Free-text sources only.
    """
    from api.assistant_service import embed_query

    limit = max(1, min(int(limit or 5), 5))
    types = list(source_types) if source_types else list(FREE_TEXT_TYPES)
    # Never pull TASK (or finance) into free-text RAG
    types = [t for t in types if t not in (AssistantSourceType.TASK, "TRANSACTION")]

    qs = AssistantChunk.objects.filter(user=user, source_type__in=types)
    chunks = list(qs.order_by("-updated_at")[:500])
    if not chunks:
        return []

    q_emb = embed_query(query) if query else []
    if q_emb:
        try:
            from api.niva.services.usage import record_usage

            record_usage(user, kind="embed", amount=1)
        except Exception:
            pass
    hits: list[RagHit] = []
    for c in chunks:
        emb = c.embedding if isinstance(c.embedding, list) else []
        v = _cosine(q_emb, emb) if q_emb and emb else 0.0
        k = _keyword_score(query, c.title or "", c.content or "")
        rec = _recency_score(c)
        imp = _importance_score(c)
        # Hybrid blend
        base = 0.55 * v + 0.25 * k
        if not q_emb or not emb:
            base = 0.70 * k + 0.10 * v
        score = 0.70 * base + 0.15 * rec + 0.15 * imp
        if score < min_score and k < 0.35 and v < 0.25:
            continue
        hits.append(
            RagHit(
                chunk=c,
                score=score,
                vector_score=v,
                keyword_score=k,
                rank_features={"recency": rec, "importance": imp},
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def chunks_as_context(hits: list[RagHit], *, max_chars: int = 2200) -> str:
    if not hits:
        return ""
    lines = ["Relevant notes / memories (retrieved):"]
    used = 0
    for h in hits:
        c = h.chunk
        meta = c.metadata if isinstance(c.metadata, dict) else {}
        kind = meta.get("type") or c.source_type
        piece = f"- [{kind}] {c.title}: {c.content[:400]}"
        if used + len(piece) > max_chars:
            break
        lines.append(piece)
        used += len(piece)
    return "\n".join(lines)


def hybrid_retrieve_as_dicts(
    query: str,
    *,
    user=None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    hits = hybrid_retrieve(query, user=user, limit=limit)
    out = []
    for h in hits:
        c = h.chunk
        meta = c.metadata if isinstance(c.metadata, dict) else {}
        out.append(
            {
                "id": c.id,
                "sourceType": c.source_type,
                "sourceId": c.source_id,
                "title": c.title,
                "content": c.content[:800],
                "score": round(h.score, 4),
                "vectorScore": round(h.vector_score, 4),
                "keywordScore": round(h.keyword_score, 4),
                "importance": meta.get("importance"),
                "date": meta.get("date"),
            }
        )
    return out
