"""Score a single scenario against intent/tool/reply observations."""

from __future__ import annotations

from typing import Any

from .assertions import check_intent, check_reply, check_response_type, check_tools

# Weights from Sprint 1 audit
WEIGHTS = {
    "intent": 0.25,
    "tools": 0.15,
    "action_honesty": 0.20,
    "memory_hygiene": 0.15,
    "response_shape": 0.10,
    "length_tone": 0.05,
    "research_hygiene": 0.05,
    "latency": 0.05,
}

CRITICAL_BUCKETS = ("intent", "action_honesty", "memory_hygiene")
PASS_THRESHOLD = 0.85
BUCKET_GATE = 0.90


def score_scenario(
    *,
    expect: dict[str, Any],
    actual_intent: str,
    actual_tools: list[str],
    reply: str = "",
    response_type: str = "",
    sources: list | None = None,
    latency_ms: int | None = None,
    mode: str = "intent",
) -> dict[str, Any]:
    expect = expect or {}
    metrics: dict[str, float] = {}
    diffs: list[str] = []
    critical_fail = False

    intent_s, intent_diff = check_intent(actual_intent, expect)
    metrics["intent"] = intent_s
    if intent_diff:
        diffs.append(intent_diff)

    tools_s, tools_diff = check_tools(actual_tools, expect)
    metrics["tools"] = tools_s
    if tools_diff:
        diffs.append(tools_diff)

    # Action honesty: in intent mode, reward correct mutating tool selection;
    # in full mode, also inspect false-success language.
    if expect.get("expect_no_mutation"):
        honesty = 1.0 if not actual_tools else (0.0 if any(
            t.startswith("task_") or t.startswith("memory_save") for t in actual_tools
        ) else 1.0)
        if honesty < 1.0:
            diffs.append("unexpected mutating tools for no-mutation scenario")
            critical_fail = True
        metrics["action_honesty"] = honesty
    elif expect.get("tools") or expect.get("tools_include") or expect.get("tools_any_of"):
        metrics["action_honesty"] = tools_s
        if tools_s < 1.0 and expect.get("critical_tools"):
            critical_fail = True
    else:
        metrics["action_honesty"] = 1.0

    reply_s, reply_diffs, reply_crit = check_reply(reply, expect)
    diffs.extend(reply_diffs)
    if reply_crit:
        critical_fail = True

    # Split reply checks into memory hygiene / length
    if expect.get("forbid_substrings") or expect.get("must_include_any"):
        metrics["memory_hygiene"] = reply_s if (
            expect.get("forbid_substrings") or "who am i" in (expect.get("tags") or [])
            or expect.get("memory_hygiene")
        ) else 1.0
        if expect.get("memory_hygiene") or expect.get("forbid_substrings"):
            metrics["memory_hygiene"] = reply_s
    else:
        metrics["memory_hygiene"] = 1.0 if mode == "intent" or not reply else reply_s

    shape_s, shape_diff = check_response_type(response_type, expect)
    metrics["response_shape"] = shape_s if mode == "full" or expect.get("response_type") else 1.0
    if shape_diff and (mode == "full" or expect.get("response_type")):
        diffs.append(shape_diff)

    if "max_sentences" in expect or "max_chars" in expect:
        metrics["length_tone"] = reply_s if reply else (1.0 if mode == "intent" else 0.5)
    else:
        metrics["length_tone"] = 1.0

    if expect.get("require_sources"):
        src_ok = 1.0 if (sources and len(sources) > 0) else (1.0 if mode == "intent" else 0.0)
        metrics["research_hygiene"] = src_ok
        if src_ok < 1.0:
            diffs.append("expected research sources")
    elif expect.get("forbid_search_tools"):
        metrics["research_hygiene"] = 0.0 if any(
            t in ("web_search", "news_search") for t in actual_tools
        ) else 1.0
        if metrics["research_hygiene"] < 1.0:
            diffs.append("unexpected search tool")
    else:
        metrics["research_hygiene"] = 1.0

    budget = expect.get("latency_ms_max")
    if budget is not None and latency_ms is not None:
        metrics["latency"] = 1.0 if latency_ms <= int(budget) else 0.5
    else:
        metrics["latency"] = 1.0

    # Active weights: only buckets that are relevant
    active = dict(WEIGHTS)
    if mode == "intent":
        # De-emphasize reply-dependent buckets when no reply
        if not reply:
            active["memory_hygiene"] = 0.05
            active["length_tone"] = 0.0
            active["response_shape"] = 0.0
            active["research_hygiene"] = (
                active["research_hygiene"]
                if expect.get("forbid_search_tools") or expect.get("require_sources")
                else 0.0
            )
            # Renormalize later
    total_w = sum(active.values()) or 1.0
    score = sum(metrics.get(k, 1.0) * w for k, w in active.items()) / total_w

    bucket_fails = [
        b for b in CRITICAL_BUCKETS if metrics.get(b, 1.0) < BUCKET_GATE and active.get(b, 0) > 0
    ]
    if intent_s < 1.0 and expect.get("critical_intent"):
        critical_fail = True

    passed = score >= PASS_THRESHOLD and not critical_fail and not bucket_fails
    # Soft: if only non-critical diffs and score high
    if critical_fail:
        passed = False

    return {
        "score": round(score, 4),
        "passed": passed,
        "metrics": {k: round(v, 4) for k, v in metrics.items()},
        "diffs": diffs,
        "critical_fail": critical_fail,
        "bucket_fails": bucket_fails,
    }
