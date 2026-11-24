"""Gemini function-calling router — schema-based tool selection with keyword fast-path."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from api.niva.services.intent_router import route_intent
from api.niva.services.language import annotate_language, glossary_prompt_block
from api.niva.services.tool_registry import (
    FAST_PATH_INTENTS,
    MAX_TOOL_STEPS,
    gemini_tools_for_user,
    intent_for_tool,
)

logger = logging.getLogger("niva.router")

ROUTER_SYSTEM = """You are Niva's tool planner for Dayflow Personal Organizer.
Pick zero or more tools to answer the user. Prefer tools for personal data (tasks, money, habits, activity, memory).
Rules:
- Never invent numbers or claim an action succeeded — tools write/read the database.
- For current/external facts use web_search or news_search.
- For chit-chat or pure explanation with no personal data, call no tools.
- Use at most 4 tools. Prefer 1 when enough.
- Put period/category/amount in tool arguments when known (use English normalized values).
- User may write English, Manglish, or Malayalam. Tool args must be English.

""" + glossary_prompt_block()


def function_calling_enabled() -> bool:
    raw = os.environ.get("NIVA_FUNCTION_CALLING", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _attach_language(intent: dict[str, Any], lang_info: dict[str, Any]) -> dict[str, Any]:
    intent["lang"] = lang_info.get("lang") or "en"
    intent["normalized_english_query"] = lang_info.get("normalized_english_query") or ""
    intent["reply_language"] = lang_info.get("reply_language") or "en"
    return intent


def resolve_route(
    message: str,
    *,
    user=None,
    history: list[dict[str, str]] | None = None,
    force_create_task: bool = False,
) -> dict[str, Any]:
    """
    Returns intent dict plus:
      lang, normalized_english_query, reply_language
      routing: keyword|gemini_fc|force
      tool_plan: [{name, args}, ...]
      router_latency_ms
    """
    t0 = time.perf_counter()
    lang_info = annotate_language(message, user=user)
    # Route keywords on English-normalized text so Manglish hits the same patterns
    route_text = lang_info.get("normalized_english_query") or message

    keyword = route_intent(
        route_text, history=history, force_create_task=force_create_task
    )
    keyword = dict(keyword)
    keyword["_history"] = history or []
    keyword["_original_message"] = message
    _attach_language(keyword, lang_info)

    if force_create_task:
        keyword["routing"] = "force"
        keyword["tool_plan"] = [
            {"name": n, "args": {}} for n in (keyword.get("tools_required") or [])
        ][:MAX_TOOL_STEPS]
        keyword["router_latency_ms"] = int((time.perf_counter() - t0) * 1000)
        return keyword

    primary = keyword.get("primary_intent") or "chat.general"
    conf = float(keyword.get("confidence") or 0)
    tools_kw = list(keyword.get("tools_required") or [])

    use_fast = (
        primary in FAST_PATH_INTENTS
        or (conf >= 0.92 and bool(tools_kw))
        or primary in ("day.plan", "day.review", "profile.identity")
    )

    if use_fast or not function_calling_enabled():
        keyword["routing"] = "keyword"
        keyword["tool_plan"] = [{"name": n, "args": {}} for n in tools_kw][:MAX_TOOL_STEPS]
        keyword["router_latency_ms"] = int((time.perf_counter() - t0) * 1000)
        return keyword

    # Ambiguous / mid-confidence → Gemini function calling (pass normalized + original)
    try:
        from api.niva.services.usage import record_usage

        record_usage(user, kind="router", amount=1)
    except Exception:
        pass
    fc = _gemini_tool_plan(
        message,
        user=user,
        history=history,
        normalized=route_text,
    )
    keyword["router_latency_ms"] = int((time.perf_counter() - t0) * 1000)

    if fc.get("error"):
        keyword["routing"] = "keyword_fallback"
        keyword["tool_plan"] = [{"name": n, "args": {}} for n in tools_kw][:MAX_TOOL_STEPS]
        keyword["fc_error"] = fc["error"]
        return keyword

    plan = (fc.get("tool_plan") or [])[:MAX_TOOL_STEPS]
    if not plan:
        # Model chose no tools — keep keyword tools if any, else chat
        if tools_kw and conf >= 0.85:
            keyword["routing"] = "keyword_fallback"
            keyword["tool_plan"] = [{"name": n, "args": {}} for n in tools_kw][
                :MAX_TOOL_STEPS
            ]
        else:
            keyword["routing"] = "gemini_fc"
            keyword["tool_plan"] = []
            keyword["tools_required"] = []
            if primary == "chat.general" or conf < 0.85:
                keyword["primary_intent"] = "chat.general"
                keyword["response_mode"] = "CHAT"
        return keyword

    # Adopt Gemini plan
    names = [p["name"] for p in plan]
    keyword["routing"] = "gemini_fc"
    keyword["tool_plan"] = plan
    keyword["tools_required"] = names
    keyword["primary_intent"] = intent_for_tool(names[0])
    keyword["confidence"] = max(conf, 0.86)
    # Merge first tool args into entities
    entities = dict(keyword.get("entities") or {})
    first_args = plan[0].get("args") or {}
    if isinstance(first_args, dict):
        entities.update(_normalize_tool_args(names[0], first_args))
    keyword["entities"] = entities
    keyword["response_mode"] = _mode_for_intent(keyword["primary_intent"])
    return keyword


def _normalize_tool_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        if v is None or v == "":
            continue
        out[k] = v
    # add_transaction → transaction_draft
    if tool_name == "add_transaction":
        draft: dict[str, Any] = {}
        if "amount" in out:
            draft["amount"] = out["amount"]
        if "title" in out:
            draft["title"] = out["title"]
        if "type" in out:
            draft["type"] = out["type"]
        if "category" in out:
            draft["category"] = str(out["category"]).upper()
        if draft:
            out["transaction_draft"] = draft
    if tool_name in ("web_search", "news_search") and out.get("query"):
        out["query"] = str(out["query"])
    if tool_name == "get_activity" and out.get("period"):
        out["period"] = str(out["period"]).replace(" ", "_").lower()
    if tool_name.startswith("spending") or tool_name in (
        "list_transactions",
        "top_expenses",
        "compare_periods",
        "budget_status",
    ):
        if out.get("category"):
            out["category"] = str(out["category"]).upper()
        if out.get("period"):
            out["period"] = str(out["period"]).replace(" ", "_").lower()
    return out


def _mode_for_intent(intent: str) -> str:
    from api.niva.services.intent_router import _mode_for

    return _mode_for(intent)


def _gemini_tool_plan(
    message: str,
    *,
    user=None,
    history: list[dict[str, str]] | None = None,
    normalized: str | None = None,
) -> dict[str, Any]:
    try:
        from api.assistant_service import CHAT_MODEL, _configure_gemini

        genai = _configure_gemini()
        if not genai:
            return {"error": "gemini_unavailable"}

        tools = gemini_tools_for_user(user)
        if not tools:
            return {"error": "no_tools"}

        # Prefer a slightly cheaper/faster model for routing if configured
        model_name = os.environ.get("NIVA_ROUTER_MODEL", "").strip() or CHAT_MODEL

        model = genai.GenerativeModel(
            model_name,
            tools=tools,
            system_instruction=ROUTER_SYSTEM,
            generation_config={"temperature": 0.1},
        )

        hist_bits = []
        for turn in (history or [])[-4:]:
            role = (turn.get("role") or "user").lower()
            content = (turn.get("content") or "").strip()[:300]
            if content:
                hist_bits.append(f"{role}: {content}")
        norm = (normalized or message).strip()
        prompt = f"User (original): {message}\nEnglish normalized: {norm}"
        if hist_bits:
            prompt = "Recent chat:\n" + "\n".join(hist_bits) + "\n\n" + prompt

        t1 = time.perf_counter()
        resp = model.generate_content(
            prompt,
            tool_config={"function_calling_config": {"mode": "AUTO"}},
            request_options={"timeout": 25},
        )
        latency = int((time.perf_counter() - t1) * 1000)
        plan = _extract_function_calls(resp)[:MAX_TOOL_STEPS]
        logger.info(
            "niva_fc plan=%s latency_ms=%s",
            [p["name"] for p in plan],
            latency,
        )
        return {"tool_plan": plan, "fc_latency_ms": latency, "model": model_name}
    except Exception as exc:
        logger.warning("niva_fc failed: %s", exc)
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _extract_function_calls(resp) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    try:
        cands = getattr(resp, "candidates", None) or []
        if not cands:
            return plan
        content = getattr(cands[0], "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            fc = getattr(part, "function_call", None)
            if not fc:
                continue
            name = getattr(fc, "name", None) or ""
            if not name:
                continue
            raw_args = getattr(fc, "args", None) or {}
            args: dict[str, Any] = {}
            if isinstance(raw_args, dict):
                args = dict(raw_args)
            else:
                # MapComposite / proto
                try:
                    args = dict(raw_args)
                except Exception:
                    try:
                        args = {k: raw_args[k] for k in raw_args}
                    except Exception:
                        args = {}
            plan.append({"name": name, "args": args})
    except Exception as exc:
        logger.debug("extract function_call failed: %s", exc)
    return plan
