"""Niva v2 orchestrator — intent → context → tools → compose."""

from __future__ import annotations

import time
from typing import Any

from api.niva.prompts import CONVERSATION_RULES, IDENTITY
from api.niva.services.context_builder import build_context
from api.niva.services.conversation_manager import (
    get_or_create_conversation,
    maybe_update_summary,
)
from api.niva.services.function_router import resolve_route
from api.niva.services.planning.planner import build_daily_plan, plan_as_reply, review_day
from api.niva.services.response_composer import compose
from api.niva.services.tool_executor import execute_tools


def process_message(
    message: str,
    *,
    user=None,
    history: list[dict[str, str]] | None = None,
    force_create_task: bool = False,
    draft_task: dict[str, Any] | None = None,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    intent_for_trace: dict[str, Any] = {}
    try:
        result = _process_message_inner(
            message,
            user=user,
            history=history,
            force_create_task=force_create_task,
            draft_task=draft_task,
            conversation_id=conversation_id,
            intent_for_trace=intent_for_trace,
        )
    except Exception as exc:
        try:
            from api.niva.services.lab.tracer import emit_trace

            emit_trace(
                user=user,
                source="prod",
                message=message or "",
                intent=intent_for_trace,
                result={"success": False},
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=f"{type(exc).__name__}",
            )
        except Exception:
            pass
        raise

    try:
        from api.niva.services.usage import record_usage

        record_usage(user, kind="chat", amount=1)
        approx = max(1, len(message or "") // 4)
        reply = ""
        if isinstance(result, dict):
            reply = str(result.get("reply") or result.get("response") or "")
        approx += max(0, len(reply) // 4)
        record_usage(user, kind="tokens", amount=0, approx_tokens=approx)
    except Exception:
        pass

    try:
        from api.niva.services.lab.tracer import emit_trace, tracing_enabled

        if tracing_enabled():
            mem_n = 0
            meta = result.get("metadata") if isinstance(result, dict) else None
            if isinstance(meta, dict) and meta.get("used_memory"):
                mem_n = 1
            search_n = 1 if (isinstance(result, dict) and result.get("webSearch")) else 0
            emit_trace(
                user=user,
                source="prod",
                message=message or "",
                intent=intent_for_trace,
                result=result if isinstance(result, dict) else {},
                latency_ms=int((time.perf_counter() - t0) * 1000),
                memory_count=mem_n,
                search_count=search_n,
            )
    except Exception:
        pass
    return result


def _process_message_inner(
    message: str,
    *,
    user=None,
    history: list[dict[str, str]] | None = None,
    force_create_task: bool = False,
    draft_task: dict[str, Any] | None = None,
    conversation_id: int | None = None,
    intent_for_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from api.assistant_service import (
        ASSISTANT_NAME,
        _crisis_reply,
        _is_crisis_message,
        _is_small_talk,
        _who_am_i_reply,
        _live_task_snapshot,
        chat_message as legacy_chat,
        get_profile,
    )

    message = (message or "").strip()
    history = history or []
    if not message and not (force_create_task and draft_task):
        return {"success": False, "error": "Message is required"}

    profile = get_profile(user)

    if _is_crisis_message(message) and not force_create_task:
        return {
            "success": True,
            "reply": _crisis_reply(profile["user_name"]),
            "response": _crisis_reply(profile["user_name"]),
            "intent": "crisis",
            "response_type": "text",
            "tasksCreated": False,
            "tasks": [],
            "assistant": ASSISTANT_NAME,
        }

    intent = resolve_route(
        message,
        user=user,
        history=history,
        force_create_task=force_create_task,
    )
    intent["_history"] = history
    try:
        from api.niva.services.companion import detect_mood

        intent["mood"] = detect_mood(message)
    except Exception:
        intent["mood"] = "neutral"
    if intent_for_trace is not None:
        intent_for_trace.clear()
        intent_for_trace.update(
            {
                "primary_intent": intent.get("primary_intent"),
                "confidence": intent.get("confidence"),
                "tools_required": list(intent.get("tools_required") or []),
                "routing": intent.get("routing"),
                "tool_plan": intent.get("tool_plan") or [],
                "router_latency_ms": intent.get("router_latency_ms"),
                "lang": intent.get("lang"),
                "reply_language": intent.get("reply_language"),
                "normalized_english_query": intent.get("normalized_english_query"),
            }
        )
    primary = intent["primary_intent"]

    snap = {}
    try:
        snap = _live_task_snapshot(user=user)
    except Exception:
        snap = {}

    # Fast identity path — no dumps
    if primary == "profile.identity":
        reply = _who_am_i_reply(profile, user=user)
        ctx = build_context(
            user=user,
            message=message,
            history=history,
            intent=intent,
            profile=profile,
            task_snapshot={},
        )
        out = compose(
            intent=intent,
            context=ctx,
            draft_reply=reply,
            profile=profile,
        )
        return _finalize(out, user, message, history, conversation_id)

    # Daily plan / review — real data tools
    if primary == "day.plan":
        from api.niva.services.companion import apply_companion_tone, shrink_plan_for_mood

        minutes = (intent.get("entities") or {}).get("available_minutes")
        plan = build_daily_plan(user, available_minutes=minutes, message=message)
        plan = shrink_plan_for_mood(plan, intent.get("mood") or "neutral")
        reply = plan_as_reply(plan, user_name=profile.get("user_name") or "there")
        reply = apply_companion_tone(
            reply,
            mood=intent.get("mood") or "neutral",
            profile=profile,
        )
        out = {
            "success": True,
            "reply": reply,
            "response": reply,
            "intent": "day.plan",
            "response_type": "daily_plan",
            "data": plan,
            "actions": [],
            "sources": [],
            "tasksCreated": False,
            "tasks": [],
            "assistant": ASSISTANT_NAME,
            "metadata": {"used_tools": True, "mood": intent.get("mood")},
        }
        return _finalize(out, user, message, history, conversation_id)

    if primary == "day.review":
        from api.niva.services.companion import apply_companion_tone, build_evening_checkin

        evening = build_evening_checkin(user, profile=profile)
        reply = apply_companion_tone(
            evening.get("reply") or review_day(user).get("reply") or "",
            mood=intent.get("mood") or "neutral",
            profile=profile,
        )
        out = {
            "success": True,
            "reply": reply,
            "response": reply,
            "intent": "day.review",
            "response_type": evening.get("response_type") or "daily_review",
            "data": evening.get("data") or {},
            "actions": [],
            "sources": [],
            "tasksCreated": False,
            "tasks": [],
            "assistant": ASSISTANT_NAME,
            "metadata": {"mood": intent.get("mood")},
        }
        return _finalize(out, user, message, history, conversation_id)

    if primary == "companion.weekly":
        from api.niva.services.companion import apply_companion_tone, build_weekly_review

        weekly = build_weekly_review(user, profile=profile)
        reply = apply_companion_tone(
            weekly.get("reply") or "",
            mood=intent.get("mood") or "neutral",
            profile=profile,
        )
        out = {
            "success": True,
            "reply": reply,
            "response": reply,
            "intent": "companion.weekly",
            "response_type": "weekly_review",
            "data": weekly.get("data") or {},
            "actions": [],
            "sources": [],
            "tasksCreated": False,
            "tasks": [],
            "assistant": ASSISTANT_NAME,
        }
        return _finalize(out, user, message, history, conversation_id)

    if primary == "companion.morning":
        from api.niva.services.companion import apply_companion_tone, build_morning_checkin

        morning = build_morning_checkin(user, profile=profile)
        reply = apply_companion_tone(
            morning.get("reply") or "",
            mood=intent.get("mood") or "neutral",
            profile=profile,
        )
        out = {
            "success": True,
            "reply": reply,
            "response": reply,
            "intent": "companion.morning",
            "response_type": "companion_morning",
            "data": morning.get("data") or {},
            "actions": [],
            "sources": [],
            "tasksCreated": False,
            "tasks": [],
            "assistant": ASSISTANT_NAME,
        }
        return _finalize(out, user, message, history, conversation_id)

    tool_plan = list(intent.get("tool_plan") or [])
    tool_names = list(intent.get("tools_required") or [])
    tool_results = execute_tools(
        tool_names,
        user=user,
        message=message,
        intent=intent,
        draft_task=draft_task,
        tool_plan=tool_plan or None,
    )
    if intent_for_trace is not None:
        intent_for_trace["tool_call_log"] = list(intent.get("_tool_call_log") or [])

    # Hard rule: if a tool failed and that was the only answer path, say so — never "Done"
    failed_only = (
        tool_results
        and all(not r.get("ok") for r in tool_results)
        and any(r.get("user_message") for r in tool_results)
    )
    if failed_only:
        msg = next(
            (r.get("user_message") for r in tool_results if r.get("user_message")),
            "That action didn’t complete. Nothing was changed.",
        )
        out = {
            "success": True,
            "reply": msg,
            "response": msg,
            "intent": primary,
            "response_type": "error",
            "actions": [],
            "sources": [],
            "tasksCreated": False,
            "tasks": [],
            "assistant": ASSISTANT_NAME,
            "metadata": {
                "used_tools": True,
                "routing": intent.get("routing"),
                "tool_call_log": intent.get("_tool_call_log") or [],
            },
        }
        return _finalize(out, user, message, history, conversation_id)

    # If tools fully answered, compose from them only (no invented numbers)
    if tool_results and any(r.get("ok") and r.get("user_message") for r in tool_results):
        ctx = build_context(
            user=user,
            message=message,
            history=history,
            intent=intent,
            tool_results=tool_results,
            profile=profile,
            task_snapshot=snap,
        )
        out = compose(
            intent=intent,
            context=ctx,
            tool_results=tool_results,
            profile=profile,
        )
        # Preserve legacy fields for existing UI
        for tr in tool_results:
            if tr.get("tasksCreated"):
                out["tasksCreated"] = True
                out["tasks"] = tr.get("tasks") or []
                out["task"] = tr.get("task")
                out["count"] = tr.get("count") or 0
            if tr.get("memoriesSaved") is not None:
                out["memoriesSaved"] = tr["memoriesSaved"]
            if tr.get("offerQuickActions"):
                out["offerQuickActions"] = True
            if tr.get("webSearch"):
                out["webSearch"] = True
        out.setdefault("tasksCreated", False)
        out.setdefault("tasks", [])
        meta = out.setdefault("metadata", {})
        if isinstance(meta, dict):
            meta["routing"] = intent.get("routing")
            meta["tool_call_log"] = intent.get("_tool_call_log") or []
            meta["used_tools"] = True
        return _finalize(out, user, message, history, conversation_id)

    # Fall through to legacy Gemini chat for general/health with orchestrated context
    # (doubt.ask / learning.explain are handled by doubt_explain tool above)
    if primary in (
        "health.guidance",
        "chat.general",
        "recommendation",
        "system.help",
    ) or (
        primary.startswith("learning")
        and primary not in ("learning.explain",)
        and not tool_results
    ):
        # Inject length policy into legacy by post-processing
        legacy = legacy_chat(
            message,
            user=user,
            history=history,
            force_create_task=False,
            draft_task=None,
        )
        if not legacy.get("success"):
            return legacy
        ctx = build_context(
            user=user,
            message=message,
            history=history,
            intent=intent,
            profile=profile,
            task_snapshot=snap,
        )
        out = compose(
            intent=intent,
            context=ctx,
            draft_reply=legacy.get("reply") or "",
            profile=profile,
        )
        # Keep suggested task / quick actions from legacy when relevant
        if legacy.get("suggestedTask"):
            out["suggestedTask"] = legacy["suggestedTask"]
        if legacy.get("offerQuickActions"):
            out["offerQuickActions"] = legacy["offerQuickActions"]
        out["tasksCreated"] = False
        out["tasks"] = []
        return _finalize(out, user, message, history, conversation_id)

    # Default: legacy path for anything not yet specialized
    legacy = legacy_chat(
        message,
        user=user,
        history=history,
        force_create_task=force_create_task,
        draft_task=draft_task,
    )
    if legacy.get("success"):
        legacy.setdefault("response", legacy.get("reply"))
        legacy.setdefault("response_type", "text")
        legacy.setdefault("intent", primary)
        legacy.setdefault("assistant", ASSISTANT_NAME)
    return _finalize(legacy, user, message, history, conversation_id)


def _finalize(
    result: dict[str, Any],
    user,
    message: str,
    history: list | None,
    conversation_id: int | None,
) -> dict[str, Any]:
    if not result.get("success"):
        return result
    try:
        conv = get_or_create_conversation(user, conversation_id)
        maybe_update_summary(
            conv,
            message=message,
            reply=result.get("reply") or "",
            intent=str(result.get("intent") or ""),
            history=history,
        )
        result["conversation_id"] = conv.id
    except Exception:
        pass
    result.setdefault("tasksCreated", False)
    result.setdefault("tasks", result.get("tasks") or [])
    result.setdefault("assistant", "Niva")
    return result
