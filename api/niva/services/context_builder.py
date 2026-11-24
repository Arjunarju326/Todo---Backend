"""Build minimal relevant context per intent."""

from __future__ import annotations

from typing import Any

from api.niva.services.memory.retriever import memories_as_context, rank_and_retrieve
from api.niva.services.conversation_manager import get_or_create_conversation, get_summary_text


def build_context(
    *,
    user,
    message: str,
    history: list[dict[str, str]] | None,
    intent: dict[str, Any],
    tool_results: list[dict[str, Any]] | None = None,
    profile: dict[str, str] | None = None,
    task_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary = intent.get("primary_intent") or "chat.general"
    cats = intent.get("memory_categories") or []

    need_memory = primary.startswith("memory") or primary in (
        "profile.identity",
        "learning.plan",
        "learning.progress",
        "recommendation",
        "day.plan",
        "project.context",
        "activity.recall",
        "doubt.ask",
    )
    # Prefer English-normalized query for embedding recall (Manglish → same vectors)
    recall_q = intent.get("normalized_english_query") or message
    memories = []
    if need_memory or cats:
        memories = rank_and_retrieve(
            recall_q,
            user=user,
            limit=4 if primary == "profile.identity" else 5,
            categories=cats or None,
            min_score=0.35 if primary != "chat.general" else 0.5,
        )

    conversation = get_or_create_conversation(user)
    summary = get_summary_text(conversation)

    # Free-text RAG snippets (notes / summaries / learning) — top 3–5 only
    rag_text = ""
    need_rag = primary.startswith("memory") or primary in (
        "doubt.ask",
        "learning.explain",
        "learning.plan",
        "project.context",
        "recommendation",
    )
    if need_rag:
        try:
            from api.niva.services.rag.retrieve import chunks_as_context, hybrid_retrieve

            hits = hybrid_retrieve(recall_q, user=user, limit=5)
            rag_text = chunks_as_context(hits)
        except Exception:
            rag_text = ""

    recent = []
    for turn in (history or [])[-6:]:
        role = (turn.get("role") or "user").lower()
        content = (turn.get("content") or "").strip()
        if content:
            recent.append({"role": role, "content": content[:800]})

    mem_block = memories_as_context(memories)
    if rag_text:
        mem_block = (mem_block + "\n" + rag_text).strip() if mem_block else rag_text

    ctx = {
        "user_profile": profile or {},
        "relevant_memories": memories,
        "memories_text": mem_block,
        "rag_text": rag_text,
        "conversation_id": conversation.id,
        "conversation_summary": summary,
        "recent_messages": recent,
        "current_tasks": (task_snapshot or {}).get("due_today")
        or (task_snapshot or {}).get("undated")
        or [],
        "task_snapshot": task_snapshot or {},
        "tool_results": tool_results or [],
        "intent": primary,
    }

    # Strip heavy fields for light intents
    if primary in ("chat.general", "system.help"):
        ctx["relevant_memories"] = []
        ctx["memories_text"] = ""
        ctx["current_tasks"] = []
    if primary == "profile.identity":
        ctx["current_tasks"] = []
        ctx["task_snapshot"] = {}
    return ctx
