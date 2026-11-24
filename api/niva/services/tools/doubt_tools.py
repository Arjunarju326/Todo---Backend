"""Doubt mode tools — explain + conditional search; save only on explicit confirm."""

from __future__ import annotations

from typing import Any

from api.niva.services.doubt import (
    extract_learning_payload_from_history,
    run_doubt,
    save_learning_note,
)


def doubt_explain(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    q = (
        entities.get("query")
        or intent.get("normalized_english_query")
        or message
    )
    force = bool(entities.get("force_search") or entities.get("needs_fresh"))
    if not force:
        # Explicit search cues in original message
        lower = (message or "").lower()
        force = any(
            k in lower
            for k in ("search", "google", "look up", "online", "from the web")
        )
    return run_doubt(str(q), user=user, force_search=force)


def save_doubt_learning(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    payload = entities.get("learning_payload")
    if not isinstance(payload, dict) or not payload.get("content"):
        history = intent.get("_history") or []
        payload = extract_learning_payload_from_history(history)
    return save_learning_note(
        user=user,
        payload=payload if isinstance(payload, dict) else None,
        source_message=message,
    )
