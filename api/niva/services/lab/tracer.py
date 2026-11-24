"""Optional Niva turn tracing — off by default (NIVA_TRACE_ENABLED=1 to enable)."""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger("niva.lab")


def tracing_enabled() -> bool:
    return os.environ.get("NIVA_TRACE_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def _preview(text: str, limit: int = 200) -> str:
    try:
        from api.niva.services.safety import redact_text

        return redact_text(text or "", max_len=limit)
    except Exception:
        t = (text or "").replace("\n", " ").strip()
        return t[:limit]


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def emit_trace(
    *,
    request_id: str | None = None,
    user=None,
    source: str = "prod",
    message: str = "",
    intent: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    latency_ms: int | None = None,
    memory_count: int = 0,
    search_count: int = 0,
    model_name: str = "",
    error: str = "",
) -> str | None:
    """Persist a redacted turn trace. Never raises into the chat path."""
    if source == "prod" and not tracing_enabled():
        return None
    rid = request_id or new_request_id()
    intent = intent or {}
    result = result or {}
    try:
        from api.models import NivaTrace
        from api.niva.services.safety import redact_mapping

        tools = list(intent.get("tools_required") or [])
        tool_log = intent.get("tool_call_log") or []
        if not tool_log and isinstance(result.get("metadata"), dict):
            tool_log = result["metadata"].get("tool_call_log") or []
        if tool_log:
            tools = tool_log
        meta = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        tool_latency = None
        if tool_log:
            try:
                tool_latency = sum(int(c.get("latency_ms") or 0) for c in tool_log)
            except Exception:
                tool_latency = None
        safe_meta = redact_mapping(
            {
                "response_mode": result.get("response_mode"),
                "used_tools": meta.get("used_tools"),
                "used_memory": meta.get("used_memory"),
                "routing": intent.get("routing") or meta.get("routing"),
                "router_latency_ms": intent.get("router_latency_ms"),
                "tool_call_log": tool_log,
            }
        )
        NivaTrace.objects.create(
            request_id=rid,
            user=user if getattr(user, "is_authenticated", False) else None,
            source=source if source in ("prod", "eval") else "prod",
            message_preview=_preview(message),
            message_hash=_hash(message),
            primary_intent=str(
                result.get("intent") or intent.get("primary_intent") or ""
            )[:64],
            intent_confidence=intent.get("confidence"),
            tools=tools,
            response_type=str(result.get("response_type") or "")[:64],
            conversation_id=result.get("conversation_id"),
            model_name=(model_name or "")[:120],
            latency_ms=latency_ms,
            tool_latency_ms=tool_latency,
            memory_count=int(memory_count or 0),
            search_count=int(search_count or 0),
            token_usage={},
            success=bool(result.get("success", True)) and not error,
            error_status=(error or "")[:120],
            metadata=safe_meta,
        )
    except Exception as exc:
        logger.debug("niva trace emit failed: %s", exc)
    return rid
