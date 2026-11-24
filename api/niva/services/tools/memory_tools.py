from __future__ import annotations

from typing import Any

from api.niva.services.memory.retriever import rank_and_retrieve
from api.niva.services.memory.updater import upsert_canonical_memory


def memory_save(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    from api.assistant_service import (
        _extract_memories_with_gemini,
        _parse_name_memory_specs,
        get_profile,
        _canonical_value_from_memory,
    )
    from api.niva.services.language import normalize_memory_text, normalize_to_english

    profile = get_profile(user)
    # Prefer English-normalized text so Manglish / Malayalam hit the same memory bank
    source_for_extract = intent.get("normalized_english_query") or normalize_to_english(message) or message
    specs = _parse_name_memory_specs(source_for_extract) or _extract_memories_with_gemini(
        source_for_extract, "", profile
    )
    saved = []
    actions = []
    for spec in specs:
        content = normalize_memory_text(spec.get("content") or "")
        title = normalize_memory_text(spec.get("title") or "Memory") or "Memory"
        mem, action = upsert_canonical_memory(
            user=user,
            title=title,
            content=content,
            key=spec.get("key") or "",
            category="profile" if "preferred_name" in (spec.get("tags") or []) else "general",
            tags=spec.get("tags") or [],
            source_message=message,
            explicit=True,
            importance=8 if spec.get("key") == "preferred_name" else 5,
        )
        if mem and action != "IGNORE":
            saved.append(mem)
            actions.append(action)
        elif mem and action == "IGNORE":
            saved.append(mem)

    if not saved:
        return {
            "ok": False,
            "user_message": "Tell me clearly what I should remember.",
            "response_type": "clarification",
            "memoriesSaved": [],
        }

    pref = next(
        (m for m in saved if "preferred_name" in [str(t).lower() for t in (m.tags or [])]),
        None,
    )
    if pref:
        nick = _canonical_value_from_memory(pref) or "that"
        reply = f"Got it — I’ll call you {nick}."
    elif len(saved) == 1:
        reply = f"Got it — remembered ({saved[0].title})."
    else:
        reply = f"Got it — remembered {len(saved)} things."

    return {
        "ok": True,
        "user_message": reply,
        "response_type": "memory_confirmation",
        "data": {"count": len(saved)},
        "memoriesSaved": [
            {"id": m.id, "title": m.title, "content": m.content, "tags": m.tags}
            for m in saved
        ],
    }


def memory_search(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    from api.assistant_service import _natural_memory_answer, _maybe_cleanup_memory
    from api.niva.services.rag.retrieve import hybrid_retrieve_as_dicts

    query = (
        (intent.get("entities") or {}).get("query")
        or intent.get("normalized_english_query")
        or message
    )
    hits = rank_and_retrieve(query, user=user, limit=5, min_score=0.30)
    rag = []
    try:
        rag = hybrid_retrieve_as_dicts(query, user=user, limit=5)
    except Exception:
        rag = []

    if hits:
        best = hits[0]
        _maybe_cleanup_memory(best)
        best.refresh_from_db()
        reply = _natural_memory_answer(message, best)
        return {
            "ok": True,
            "user_message": reply,
            "response_type": "text",
            "data": {
                "memory_id": best.id,
                "title": best.title,
                "rag": rag[:3],
            },
        }

    if rag:
        top = rag[0]
        snippet = (top.get("content") or "")[:280]
        title = top.get("title") or "note"
        reply = f"From your notes — “{title}”: {snippet}"
        return {
            "ok": True,
            "user_message": reply,
            "response_type": "text",
            "data": {"rag": rag[:3]},
        }

    return {
        "ok": True,
        "user_message": "I don’t have that saved yet. Say “remember this: …” and I’ll store it.",
        "response_type": "text",
        "data": {"memories": [], "rag": []},
    }


def memory_archive(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    from api.assistant_service import forget_memories

    forgotten = forget_memories(message, user=user)
    if not forgotten:
        return {
            "ok": False,
            "user_message": "I couldn’t find a matching memory to forget.",
            "response_type": "text",
        }
    titles = ", ".join(f"“{m.title}”" for m in forgotten)
    return {
        "ok": True,
        "user_message": f"Okay — I forgot {titles}.",
        "response_type": "memory_confirmation",
        "memoriesForgotten": [{"id": m.id, "title": m.title} for m in forgotten],
    }
