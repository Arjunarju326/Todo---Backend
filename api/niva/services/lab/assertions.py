"""Assertion helpers for Intelligence Lab scenario expects."""

from __future__ import annotations

import re
from typing import Any


def sentence_count(text: str) -> int:
    parts = [p.strip() for p in re.split(r"[.!?]+", text or "") if p.strip()]
    return len(parts)


def check_intent(actual: str, expect: dict[str, Any]) -> tuple[float, str | None]:
    wanted = expect.get("intent")
    allowed = expect.get("intent_any") or ([] if wanted is None else [wanted])
    if not allowed:
        return 1.0, None
    if actual in allowed:
        return 1.0, None
    return 0.0, f"intent expected {allowed}, got {actual!r}"


def check_tools(actual_tools: list[str], expect: dict[str, Any]) -> tuple[float, str | None]:
    exact = expect.get("tools")
    any_of = expect.get("tools_any_of")
    includes = expect.get("tools_include") or []
    excludes = expect.get("tools_exclude") or []
    actual = list(actual_tools or [])
    if exact is not None:
        if sorted(actual) == sorted(exact):
            return 1.0, None
        return 0.0, f"tools expected {exact}, got {actual}"
    if any_of:
        if any(t in actual for t in any_of):
            return 1.0, None
        return 0.0, f"tools expected any of {any_of}, got {actual}"
    score = 1.0
    note = None
    for t in includes:
        if t not in actual:
            score = 0.0
            note = f"missing tool {t}"
            break
    for t in excludes:
        if t in actual:
            score = 0.0
            note = f"unexpected tool {t}"
            break
    return score, note


def check_reply(reply: str, expect: dict[str, Any]) -> tuple[float, list[str], bool]:
    """Returns (score, diffs, critical_fail)."""
    diffs: list[str] = []
    critical = False
    checks = 0
    passed = 0
    text = reply or ""

    if "max_sentences" in expect:
        checks += 1
        n = sentence_count(text)
        if n <= int(expect["max_sentences"]):
            passed += 1
        else:
            diffs.append(f"max_sentences {expect['max_sentences']}, got {n}")

    if "max_chars" in expect:
        checks += 1
        if len(text) <= int(expect["max_chars"]):
            passed += 1
        else:
            diffs.append(f"max_chars {expect['max_chars']}, got {len(text)}")

    forbid = expect.get("forbid_substrings") or []
    if forbid:
        checks += 1
        hit = [s for s in forbid if s.lower() in text.lower()]
        if not hit:
            passed += 1
        else:
            diffs.append(f"forbid_substrings hit {hit}")
            if expect.get("forbid_critical"):
                critical = True

    must_any = expect.get("must_include_any") or []
    if must_any:
        checks += 1
        if any(s.lower() in text.lower() for s in must_any):
            passed += 1
        else:
            diffs.append(f"must_include_any missing {must_any}")

    must_all = expect.get("must_include_all") or []
    if must_all:
        checks += 1
        missing = [s for s in must_all if s.lower() not in text.lower()]
        if not missing:
            passed += 1
        else:
            diffs.append(f"must_include_all missing {missing}")

    false_success = expect.get("forbid_false_success")
    if false_success:
        checks += 1
        patterns = [
            r"\bdone[!.,]?\b.*\b(added|created|saved|completed)\b",
            r"\bi('ve| have) (added|created|saved|completed)\b",
        ]
        # Only critical when expect says mutation should have failed / not run
        if expect.get("expect_no_mutation"):
            hit = any(re.search(p, text, re.I) for p in patterns)
            if not hit:
                passed += 1
            else:
                passed += 0
                diffs.append("possible false success confirmation")
                critical = True
        else:
            passed += 1

    if checks == 0:
        return 1.0, diffs, critical
    return passed / checks, diffs, critical


def check_response_type(actual: str, expect: dict[str, Any]) -> tuple[float, str | None]:
    wanted = expect.get("response_type")
    allowed = expect.get("response_type_any") or ([] if wanted is None else [wanted])
    if not allowed:
        return 1.0, None
    if actual in allowed:
        return 1.0, None
    return 0.0, f"response_type expected {allowed}, got {actual!r}"
