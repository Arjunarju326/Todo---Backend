"""Index free-text sources into AssistantChunk (embeddings as JSON; no task/tx tables)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.utils import timezone

from api.models import (
    AssistantChunk,
    AssistantMemory,
    AssistantSourceType,
    Note,
    NivaConversationSummary,
)
from api.niva.services.rag.chunking import chunk_text

logger = logging.getLogger("niva.rag")

# Free-text RAG sources only — never raw transactions / task tables
FREE_TEXT_TYPES = frozenset(
    {
        AssistantSourceType.MEMORY,
        AssistantSourceType.NOTE,
        AssistantSourceType.SUMMARY,
        AssistantSourceType.JOURNAL,
        AssistantSourceType.LEARNING_NOTE,
    }
)
# Optional KB overlap for conceptual explain (not personal recall)
FREE_TEXT_PLUS_KB = FREE_TEXT_TYPES | {AssistantSourceType.KNOWLEDGE}


def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _upsert_chunks_for_doc(
    *,
    user,
    source_type: str,
    source_id: str,
    title: str,
    full_text: str,
    metadata: dict[str, Any],
    force_embed: bool = True,
) -> int:
    from api.assistant_service import _upsert_chunk, embed_texts

    pieces = chunk_text(full_text)
    if not pieces:
        # Clear stale chunks for empty docs
        AssistantChunk.objects.filter(
            user=user, source_type=source_type, source_id__startswith=f"{source_id}#"
        ).delete()
        AssistantChunk.objects.filter(
            user=user, source_type=source_type, source_id=source_id
        ).delete()
        return 0

    live_ids: list[str] = []
    count = 0
    for i, piece in enumerate(pieces):
        sid = source_id if len(pieces) == 1 else f"{source_id}#{i}"
        live_ids.append(sid)
        existing = AssistantChunk.objects.filter(
            user=user, source_type=source_type, source_id=sid
        ).first()
        chash = _content_hash(piece)
        content_changed = (
            not existing
            or existing.content != piece
            or (existing.metadata or {}).get("content_hash") != chash
        )
        need_embed = force_embed and (
            content_changed or not (existing and existing.embedding)
        )
        emb: list[float] = []
        if need_embed:
            try:
                emb = embed_texts([f"{title}\n{piece}" if title else piece])[0]
                try:
                    from api.niva.services.usage import record_usage

                    record_usage(user, kind="embed", amount=1)
                except Exception:
                    pass
            except Exception as exc:
                logger.warning("embed failed %s/%s: %s", source_type, sid, exc)
                emb = []
        elif existing and isinstance(existing.embedding, list):
            emb = existing.embedding

        meta = {
            **(metadata or {}),
            "content_hash": chash,
            "chunk_index": i,
            "chunk_count": len(pieces),
            "indexed_at": timezone.now().isoformat(),
        }
        _upsert_chunk(
            source_type=source_type,
            source_id=sid,
            title=(title or "")[:255],
            content=piece,
            embedding=emb,
            metadata=meta,
            user=user,
        )
        count += 1

    # Drop orphan chunk pieces
    AssistantChunk.objects.filter(user=user, source_type=source_type).filter(
        source_id__startswith=f"{source_id}#"
    ).exclude(source_id__in=live_ids).delete()
    if f"{source_id}#0" in live_ids:
        AssistantChunk.objects.filter(
            user=user, source_type=source_type, source_id=source_id
        ).delete()
    return count


def index_memory_document(memory: AssistantMemory, *, force_embed: bool = True) -> int:
    if not memory or not memory.user_id:
        return 0
    if not memory.is_active or memory.status != "active":
        AssistantChunk.objects.filter(
            user=memory.user,
            source_type=AssistantSourceType.MEMORY,
            source_id__startswith=str(memory.id),
        ).delete()
        AssistantChunk.objects.filter(
            user=memory.user,
            source_type=AssistantSourceType.LEARNING_NOTE,
            source_id__startswith=str(memory.id),
        ).delete()
        return 0

    tags = [str(t).lower() for t in (memory.tags or [])]
    is_learning = memory.category == "learning" or "learning" in tags or "doubt" in tags
    source_type = (
        AssistantSourceType.LEARNING_NOTE if is_learning else AssistantSourceType.MEMORY
    )
    # Remove from the other type if switched
    other = (
        AssistantSourceType.MEMORY
        if is_learning
        else AssistantSourceType.LEARNING_NOTE
    )
    AssistantChunk.objects.filter(
        user=memory.user,
        source_type=other,
        source_id__startswith=str(memory.id),
    ).delete()

    text = f"{memory.title}\n{memory.content}"
    meta = {
        "type": "memory",
        "memory_id": memory.id,
        "category": memory.category,
        "importance": memory.importance or 5,
        "explicit": bool(memory.explicit),
        "date": (memory.updated_at or memory.created_at or timezone.now()).isoformat(),
        "tags": tags[:8],
    }
    return _upsert_chunks_for_doc(
        user=memory.user,
        source_type=source_type,
        source_id=str(memory.id),
        title=memory.title,
        full_text=text,
        metadata=meta,
        force_embed=force_embed,
    )


def index_note_document(note: Note, *, force_embed: bool = True) -> int:
    if not note or not note.user_id:
        return 0
    cat = (note.category or "").upper()
    source_type = (
        AssistantSourceType.JOURNAL
        if cat in ("JOURNAL", "DIARY", "REFLECTION")
        else AssistantSourceType.NOTE
    )
    text = f"{note.title}\n{note.content or ''}"
    meta = {
        "type": "note",
        "note_id": note.id,
        "category": note.category,
        "importance": 6 if note.is_pinned else 4,
        "date": (note.updated_at or note.created_at or timezone.now()).isoformat(),
        "pinned": bool(note.is_pinned),
    }
    return _upsert_chunks_for_doc(
        user=note.user,
        source_type=source_type,
        source_id=str(note.id),
        title=note.title,
        full_text=text,
        metadata=meta,
        force_embed=force_embed,
    )


def index_summary_document(summary: NivaConversationSummary, *, force_embed: bool = True) -> int:
    conv = getattr(summary, "conversation", None)
    user = getattr(conv, "user", None) if conv else None
    if not user or not (summary.summary or "").strip():
        return 0
    text = summary.summary
    if summary.current_topic:
        text = f"Topic: {summary.current_topic}\n{text}"
    if summary.unresolved_items:
        text += "\nUnresolved: " + "; ".join(str(x) for x in summary.unresolved_items[:8])
    meta = {
        "type": "summary",
        "conversation_id": conv.id,
        "importance": 5,
        "date": (summary.updated_at or timezone.now()).isoformat(),
    }
    return _upsert_chunks_for_doc(
        user=user,
        source_type=AssistantSourceType.SUMMARY,
        source_id=str(conv.id),
        title=f"Chat summary {conv.id}",
        full_text=text,
        metadata=meta,
        force_embed=force_embed,
    )


def index_free_text(user, *, force_embed: bool = True) -> dict[str, int]:
    """
    Reindex memories, notes/journal, conversation summaries, learning notes.
    Does NOT embed raw transactions or task tables.
    """
    from api.assistant_service import ensure_pgvector

    ensure_pgvector()
    counts = {
        "memories": 0,
        "learning_notes": 0,
        "notes": 0,
        "journals": 0,
        "summaries": 0,
        "chunks": 0,
    }
    if not user:
        return counts

    for mem in AssistantMemory.objects.filter(user=user, is_active=True, status="active")[
        :200
    ]:
        n = index_memory_document(mem, force_embed=force_embed)
        counts["chunks"] += n
        tags = [str(t).lower() for t in (mem.tags or [])]
        if mem.category == "learning" or "learning" in tags or "doubt" in tags:
            counts["learning_notes"] += 1
        else:
            counts["memories"] += 1

    for note in Note.objects.filter(user=user)[:100]:
        n = index_note_document(note, force_embed=force_embed)
        counts["chunks"] += n
        cat = (note.category or "").upper()
        if cat in ("JOURNAL", "DIARY", "REFLECTION"):
            counts["journals"] += 1
        else:
            counts["notes"] += 1

    from api.models import NivaConversation

    conv_ids = NivaConversation.objects.filter(user=user).values_list("id", flat=True)[:30]
    for s in NivaConversationSummary.objects.filter(conversation_id__in=list(conv_ids)):
        n = index_summary_document(s, force_embed=force_embed)
        counts["chunks"] += n
        if n:
            counts["summaries"] += 1

    return counts
