"""Compose final user-facing Niva responses with length/style control."""

from __future__ import annotations

from typing import Any

from api.niva.prompts import RESPONSE_LENGTH
from api.niva.services.language import localize_reply
from api.niva.services.companion import apply_companion_tone, detect_mood


def compose(
    *,
    intent: dict[str, Any],
    context: dict[str, Any],
    tool_results: list[dict[str, Any]] | None = None,
    draft_reply: str = "",
    profile: dict[str, str] | None = None,
) -> dict[str, Any]:
    primary = intent.get("primary_intent") or "chat.general"
    mode = intent.get("response_mode") or "CHAT"
    name = (profile or {}).get("user_name") or "there"
    tool_results = tool_results or []
    reply_lang = intent.get("reply_language") or "en"
    user_msg = intent.get("_original_message") or ""
    mood = intent.get("mood") or detect_mood(user_msg)
    celebrate = primary in ("task.complete", "habit.query") or any(
        (tr.get("response_type") or "").endswith("confirmation") and tr.get("ok")
        for tr in tool_results
    )

    def _finish(reply: str, **pack_kwargs):
        reply = apply_companion_tone(
            reply, mood=mood, profile=profile, celebrate=celebrate
        )
        reply = localize_reply(reply, reply_language=reply_lang, user_message=user_msg)
        meta = dict(pack_kwargs.get("metadata") or {})
        meta["mood"] = mood
        meta["lang"] = intent.get("lang")
        meta["reply_language"] = reply_lang
        pack_kwargs["metadata"] = meta
        return _pack(reply=reply, **pack_kwargs)

    # Prefer verified tool-driven replies (facts stay from tools; language may be localized)
    for tr in tool_results:
        if tr.get("ok") and tr.get("user_message"):
            return _finish(
                tr["user_message"],
                intent=primary,
                mode=mode,
                response_type=tr.get("response_type") or _default_type(primary),
                data=tr.get("data") or {},
                actions=tr.get("actions") or [],
                sources=tr.get("sources") or [],
                metadata={
                    "used_tools": True,
                    "used_memory": bool(context.get("memories_text")),
                },
            )
        if not tr.get("ok") and tr.get("user_message"):
            return _finish(
                tr["user_message"],
                intent=primary,
                mode="ACTION",
                response_type="error",
                data=tr.get("data") or {},
                actions=[],
                sources=[],
                metadata={"used_tools": True, "error": True},
            )

    reply = (draft_reply or "").strip()
    if primary == "profile.identity" and not reply:
        # fallback — orchestrator usually sets this
        reply = f"You’re {name}."

    reply = _enforce_length(reply, primary)
    return _finish(
        reply or "Okay.",
        intent=primary,
        mode=mode,
        response_type=_default_type(primary),
        data={},
        actions=[],
        sources=_sources_from_tools(tool_results),
        metadata={
            "used_tools": bool(tool_results),
            "used_memory": bool(context.get("memories_text")),
            "length_hint": RESPONSE_LENGTH.get(primary, "short"),
        },
    )


def _pack(**kwargs) -> dict[str, Any]:
    return {
        "success": True,
        "reply": kwargs["reply"],
        "response": kwargs["reply"],
        "intent": kwargs["intent"],
        "response_type": kwargs["response_type"],
        "response_mode": kwargs["mode"],
        "data": kwargs.get("data") or {},
        "actions": kwargs.get("actions") or [],
        "sources": kwargs.get("sources") or [],
        "metadata": kwargs.get("metadata") or {},
        "assistant": "Niva",
    }


def _default_type(intent: str) -> str:
    return {
        "task.create": "task_confirmation",
        "task.list": "task_list",
        "day.plan": "daily_plan",
        "day.review": "daily_review",
        "memory.save": "memory_confirmation",
        "memory.recall": "text",
        "learning.plan": "learning_plan",
        "learning.progress": "learning_progress",
        "research.web": "research",
        "research.news": "news",
        "doubt.ask": "doubt_answer",
        "doubt.save": "memory_confirmation",
        "recommendation": "recommendations",
        "profile.identity": "text",
        "health.guidance": "health",
        "admin.users": "admin_users",
        "system.internals": "system_internals",
    }.get(intent, "text")


def _enforce_length(reply: str, intent: str) -> str:
    if not reply:
        return reply
    if intent in ("profile.identity", "memory.save", "chat.general"):
        # Keep to ~3 sentences
        parts = [p.strip() for p in reply.replace("\n", " ").split(".") if p.strip()]
        if len(parts) > 3:
            return ". ".join(parts[:3]).rstrip(".") + "."
    if intent.startswith("research") and len(reply) > 1600:
        return reply[:1600].rstrip() + "…"
    return reply


def _sources_from_tools(tool_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for tr in tool_results:
        for s in tr.get("sources") or []:
            if isinstance(s, dict) and s.get("url"):
                out.append({"title": s.get("title") or "", "url": s["url"]})
    return out
