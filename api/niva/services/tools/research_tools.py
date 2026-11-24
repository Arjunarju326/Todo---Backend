from __future__ import annotations

from typing import Any

from api.niva.services.research.citations import build_citations, format_research_reply
from api.niva.services.research.filtering import filter_results
from api.niva.services.research.router import topic_for
from api.niva.services.research.tavily import search


def web_search(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    from api.assistant_service import get_profile

    profile = get_profile(user)
    q = (
        (intent.get("entities") or {}).get("query")
        or intent.get("normalized_english_query")
        or message
    )
    topic = topic_for(q, intent.get("primary_intent") or "")
    raw = search(q, user=user, topic=topic, max_results=5)
    web = filter_results(raw)
    if not web or (not web.get("answer") and not web.get("results")):
        return {
            "ok": False,
            "user_message": "I couldn’t reach live search right now. Try again in a moment.",
            "response_type": "error",
        }
    return {
        "ok": True,
        "user_message": format_research_reply(web, user_name=profile.get("user_name") or "there"),
        "response_type": "research",
        "sources": build_citations(web),
        "data": {"query": web.get("query"), "cached": web.get("cached", False)},
        "webSearch": True,
    }


def news_search(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    from api.assistant_service import get_profile

    profile = get_profile(user)
    q = (
        (intent.get("entities") or {}).get("query")
        or intent.get("normalized_english_query")
        or message
    )
    q = q.strip() if isinstance(q, str) else ""
    if not q:
        q = "latest technology AI news today"
    raw = search(q, user=user, topic="news", max_results=5)
    web = filter_results(raw)
    if not web or (not web.get("answer") and not web.get("results")):
        return {
            "ok": False,
            "user_message": "I couldn’t fetch news right now.",
            "response_type": "error",
        }
    return {
        "ok": True,
        "user_message": format_research_reply(web, user_name=profile.get("user_name") or "there"),
        "response_type": "news",
        "sources": build_citations(web),
        "data": {"query": web.get("query"), "cached": web.get("cached", False)},
        "webSearch": True,
    }
