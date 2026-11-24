"""Conditional Tavily routing — search only when freshness/external facts needed."""

from __future__ import annotations

import re


def should_search(message: str, intent: str = "") -> bool:
    if intent in ("research.web", "research.news"):
        return True
    if intent == "doubt.ask":
        from api.niva.services.doubt import needs_fresh_info

        return needs_fresh_info(message)
    lower = (message or "").lower()
    if re.search(
        r"\b(google|search online|look up|latest news|headlines|current (price|version)|"
        r"breaking|from the web|check online)\b",
        lower,
    ):
        return True
    # Conceptual questions — no search
    if re.search(r"\b(what is|explain|how does|teach me)\b", lower) and not re.search(
        r"\b(latest|current|today|202[4-9]|version)\b", lower
    ):
        return False
    # Personal Dayflow data — no search
    if re.search(r"\b(my task|my habit|who am i|remember|dayflow)\b", lower):
        return False
    return False


def topic_for(message: str, intent: str = "") -> str:
    if intent == "research.news" or re.search(r"\bnews|headline", (message or "").lower()):
        return "news"
    return "general"
