"""Validate + execute Niva tools; never claim success without DB/API verification."""

from __future__ import annotations

import logging
import time
from typing import Any

from api.niva.services.tools import TOOL_HANDLERS
from api.niva.services.tool_registry import MAX_TOOL_STEPS
from api.niva.services.function_router import _normalize_tool_args

logger = logging.getLogger("niva.tools")


def execute_tools(
    tool_names: list[str] | None = None,
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task: dict[str, Any] | None = None,
    tool_plan: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Execute tools in order (max MAX_TOOL_STEPS).
    Prefer tool_plan=[{name, args}] from the function-calling router;
    otherwise tool_names with empty args.
    """
    plan: list[dict[str, Any]] = []
    if tool_plan:
        for step in tool_plan:
            if not isinstance(step, dict):
                continue
            name = step.get("name")
            if not name:
                continue
            plan.append({"name": name, "args": step.get("args") or {}})
    else:
        for name in tool_names or []:
            plan.append({"name": name, "args": {}})

    plan = plan[:MAX_TOOL_STEPS]
    results: list[dict[str, Any]] = []
    call_log: list[dict[str, Any]] = []

    base_entities = dict(intent.get("entities") or {})

    for step in plan:
        name = step["name"]
        args = step.get("args") or {}
        handler = TOOL_HANDLERS.get(name)
        t0 = time.perf_counter()
        status = "ok"

        if not handler:
            latency = int((time.perf_counter() - t0) * 1000)
            entry = {
                "tool": name,
                "ok": False,
                "user_message": f"I don’t have the “{name}” tool available yet.",
                "latency_ms": latency,
                "args": args,
            }
            results.append(entry)
            call_log.append(
                {"name": name, "args": _safe_args(args), "status": "missing", "latency_ms": latency}
            )
            continue

        # Merge per-tool args into a copy of intent entities
        step_intent = dict(intent)
        merged = dict(base_entities)
        if isinstance(args, dict) and args:
            merged.update(_normalize_tool_args(name, args))
        step_intent["entities"] = merged

        try:
            result = handler(
                user=user,
                message=message,
                intent=step_intent,
                draft_task=draft_task,
            )
            if not isinstance(result, dict):
                result = {"ok": False, "user_message": "Tool returned an invalid result."}
                status = "invalid"
            elif not result.get("ok", True):
                status = "failed"
            result.setdefault("tool", name)
            latency = int((time.perf_counter() - t0) * 1000)
            result["latency_ms"] = latency
            results.append(result)
            call_log.append(
                {
                    "name": name,
                    "args": _safe_args(args),
                    "status": status,
                    "latency_ms": latency,
                    "ok": bool(result.get("ok")),
                }
            )
        except Exception as exc:
            latency = int((time.perf_counter() - t0) * 1000)
            status = "error"
            results.append(
                {
                    "tool": name,
                    "ok": False,
                    "user_message": (
                        f"I couldn’t complete that action because the service failed. "
                        f"Nothing was changed. ({type(exc).__name__})"
                    ),
                    "error": str(exc)[:200],
                    "latency_ms": latency,
                }
            )
            call_log.append(
                {
                    "name": name,
                    "args": _safe_args(args),
                    "status": status,
                    "latency_ms": latency,
                    "error": type(exc).__name__,
                }
            )
            logger.warning("tool %s failed: %s", name, exc)

    intent["_tool_call_log"] = call_log
    if call_log:
        logger.info(
            "niva_tools calls=%s",
            [
                f"{c['name']}:{c['status']}:{c['latency_ms']}ms"
                for c in call_log
            ],
        )
    return results


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    """Redact oversized values for logs."""
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and len(v) > 120:
            out[k] = v[:120] + "…"
        elif isinstance(v, (dict, list)):
            out[k] = str(v)[:120]
        else:
            out[k] = v
    return out


def known_tool_names() -> list[str]:
    return sorted(TOOL_HANDLERS.keys())
