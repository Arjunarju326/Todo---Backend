"""Doubt mode — explain, search when needed, cite, offer to save (never auto-save)."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from django.utils import timezone

from api.niva.services.research.citations import build_citations
from api.niva.services.research.filtering import filter_results
from api.niva.services.research.tavily import search as tavily_search

logger = logging.getLogger("niva.doubt")

DOUBT_PATTERNS = (
    r"\bwhat is\b",
    r"\bwhat's\b",
    r"\bwhats\b",
    r"\bwhy (does|do|is|are|did)\b",
    r"\bhow (do|does|to|can|should)\b",
    r"\bexplain\b",
    r"\bdifference between\b",
    r"\bmean(ing)? of\b",
    r"\benthaanu\b",
    r"\benthaa\b",
    r"\benthu aa\b",
    r"\benthanu\b",
    r"\bsahayikkamo\b.{0,40}\b(explain|enthaanu|what)",
)

FRESH_CUES = (
    r"\b(latest|current|today|tonight|this week|202[4-9]|news|price|prices|"
    r"version|release|released|update|updated|breaking|score|scores|"
    r"law|laws|regulation|weather|stock|ipo)\b",
    r"\bwhat'?s new\b",
    r"\bnew in\b",
    r"\b(search|google|look up|online|from the web)\b",
)

PERSONAL_CUES = (
    r"\b(my task|my tasks|my habit|my spend|my expense|chilavu|who am i|"
    r"remember|dayflow|innu enthokke|innale)\b",
)

STABLE_CONCEPT = (
    r"\b(what is|what's|explain|how does|how do|meaning of|difference between|"
    r"enthaanu)\b",
)


def is_doubt_message(message: str) -> bool:
    lower = (message or "").lower().strip()
    if not lower:
        return False
    if re.search(PERSONAL_CUES[0], lower):
        # Personal data doubts → not doubt-mode (use Dayflow tools)
        if not re.search(r"\b(what is|explain|how does|enthaanu)\b", lower):
            return False
    return any(re.search(p, lower) for p in DOUBT_PATTERNS)


def needs_fresh_info(message: str, *, confidence_low: bool = False) -> bool:
    lower = (message or "").lower()
    if re.search(PERSONAL_CUES[0], lower) and not any(
        re.search(p, lower) for p in FRESH_CUES
    ):
        return False
    if any(re.search(p, lower) for p in FRESH_CUES):
        return True
    if confidence_low:
        return True
    # Stable definitions — prefer knowledge, no search
    if any(re.search(p, lower) for p in STABLE_CONCEPT) and not any(
        re.search(p, lower) for p in FRESH_CUES
    ):
        return False
    return False


def daily_search_count(user) -> int:
    if not user:
        return 0
    try:
        from api.models import NivaResearchCache

        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return NivaResearchCache.objects.filter(user=user, created_at__gte=start).count()
    except Exception:
        return 0


def daily_search_cap() -> int:
    try:
        return max(1, int(os.environ.get("NIVA_DAILY_SEARCH_CAP", "40")))
    except ValueError:
        return 40


def search_allowed(user) -> bool:
    return daily_search_count(user) < daily_search_cap()


def _gemini_explain(
    question: str,
    *,
    web: dict[str, Any] | None = None,
    used_search: bool = False,
) -> dict[str, Any]:
    """Short explanation + optional practice question. Facts from web when present."""
    from api.assistant_service import CHAT_MODEL, _configure_gemini, _gemini_response_text, _parse_json_loose

    genai = _configure_gemini()
    sources_block = ""
    if web:
        bits = []
        if web.get("answer"):
            bits.append(f"Search answer: {web['answer'][:800]}")
        for r in (web.get("results") or [])[:3]:
            bits.append(
                f"- {(r.get('title') or '')[:120]}: {(r.get('content') or '')[:240]} "
                f"({r.get('url') or ''})"
            )
        sources_block = "\n".join(bits)

    prompt = f"""You are Niva, a warm concise learning companion for Dayflow.
Answer the user's doubt in plain language (English). Keep under 900 characters.
If web/search context is provided, ground claims in it and do not invent URLs.
If no search context, answer from stable knowledge and say when you're unsure.
Never claim you saved anything to memory.

Return ONLY JSON:
{{
  "explanation": "short clear answer",
  "practice_question": "one tiny practice question or next step (or empty string)",
  "uncertain": false
}}

User doubt: {question!r}

Search context (may be empty):
{sources_block or "(none — answer from knowledge)"}
Used live search: {used_search}
"""
    if not genai:
        return {
            "explanation": _fallback_explain(question, web),
            "practice_question": _fallback_practice(question),
            "uncertain": True,
        }
    try:
        model = genai.GenerativeModel(
            CHAT_MODEL,
            generation_config={"temperature": 0.35, "response_mime_type": "application/json"},
        )
        resp = model.generate_content(prompt, request_options={"timeout": 40})
        parsed = _parse_json_loose(_gemini_response_text(resp) or "")
        if not isinstance(parsed, dict) or not parsed.get("explanation"):
            return {
                "explanation": _fallback_explain(question, web),
                "practice_question": _fallback_practice(question),
                "uncertain": True,
            }
        return {
            "explanation": str(parsed.get("explanation") or "")[:1200],
            "practice_question": str(parsed.get("practice_question") or "")[:400],
            "uncertain": bool(parsed.get("uncertain")),
        }
    except Exception as exc:
        logger.warning("doubt explain failed: %s", exc)
        return {
            "explanation": _fallback_explain(question, web),
            "practice_question": _fallback_practice(question),
            "uncertain": True,
        }


def _fallback_explain(question: str, web: dict[str, Any] | None) -> str:
    if web and web.get("answer"):
        return str(web["answer"])[:900]
    results = (web or {}).get("results") or []
    if results:
        snips = []
        for r in results[:2]:
            snips.append((r.get("content") or r.get("title") or "")[:200])
        return "Here’s a short take from live sources: " + " ".join(snips)
    return (
        f"I’m not fully sure about “{question[:120]}” without more context. "
        "Try rephrasing, or say “search online” if you want me to look it up."
    )


def _fallback_practice(question: str) -> str:
    topic = (question or "this").strip()[:80]
    return f"Quick check: explain “{topic}” in one sentence in your own words."


def run_doubt(
    question: str,
    *,
    user=None,
    force_search: bool = False,
    allow_search: bool | None = None,
) -> dict[str, Any]:
    q = (question or "").strip()
    if not q:
        return {
            "ok": False,
            "user_message": "What are you unsure about? Ask “what is…”, “why…”, or “how to…”.",
            "response_type": "clarification",
        }

    fresh = force_search or needs_fresh_info(q)
    if allow_search is None:
        allow_search = True
        try:
            from api.models import NivaCompanionSettings

            if user:
                s = NivaCompanionSettings.objects.filter(user=user).first()
                if s is not None and s.web_research_enabled is False:
                    allow_search = False
        except Exception:
            pass

    web = None
    used_search = False
    search_blocked = False
    if fresh and allow_search:
        if not search_allowed(user):
            search_blocked = True
        else:
            raw = tavily_search(q, user=user, topic="general", max_results=5)
            web = filter_results(raw) if raw else None
            used_search = bool(web)

    # If uncertain / no web and looks like it might need freshness, try search once
    explained = _gemini_explain(q, web=web, used_search=used_search)
    if (
        not used_search
        and allow_search
        and not search_blocked
        and explained.get("uncertain")
        and search_allowed(user)
    ):
        raw = tavily_search(q, user=user, topic="general", max_results=5)
        web = filter_results(raw) if raw else None
        if web:
            used_search = True
            explained = _gemini_explain(q, web=web, used_search=True)

    citations = build_citations(web)[:3] if web else []
    explanation = explained.get("explanation") or ""
    practice = (explained.get("practice_question") or "").strip()

    parts = [explanation]
    if citations:
        parts.append("\nSources:")
        for c in citations:
            title = c.get("title") or "Source"
            url = c.get("url") or ""
            parts.append(f"• {title}" + (f"\n  {url}" if url else ""))
    parts.append("\nSave this to your learning notes?")
    if practice:
        parts.append(f"Practice: {practice}")
    if search_blocked:
        parts.append("(Live search daily cap reached — answered from knowledge only.)")

    learning_payload = {
        "title": f"Doubt: {q[:80]}",
        "content": explanation[:1500],
        "question": q[:500],
        "sources": citations,
        "practice": practice,
    }

    return {
        "ok": True,
        "user_message": "\n".join(parts).strip(),
        "response_type": "doubt_answer",
        "sources": citations,
        "actions": [
            {
                "type": "save_learning",
                "label": "Save to learning notes",
            }
        ],
        "data": {
            "question": q,
            "explanation": explanation,
            "practice_question": practice,
            "used_search": used_search,
            "offer_save": True,
            "learning_payload": learning_payload,
            "search_blocked": search_blocked,
            "needs_fresh": fresh,
        },
        "webSearch": used_search,
    }


def save_learning_note(
    *,
    user,
    payload: dict[str, Any] | None = None,
    source_message: str = "",
) -> dict[str, Any]:
    """Explicit save only — never called automatically from web search."""
    from api.niva.services.memory.updater import upsert_canonical_memory

    payload = payload or {}
    title = (payload.get("title") or "Learning note")[:255]
    content = (payload.get("content") or "").strip()
    question = (payload.get("question") or "").strip()
    if not content and question:
        content = question
    if not content:
        return {
            "ok": False,
            "user_message": "Nothing to save yet. Ask a doubt first, then say “save this to learning”.",
            "response_type": "clarification",
        }
    sources = payload.get("sources") or []
    if sources:
        links = "; ".join(
            f"{s.get('title') or 'Source'}: {s.get('url')}"
            for s in sources[:3]
            if isinstance(s, dict) and s.get("url")
        )
        if links:
            content = f"{content}\n\nSources: {links}"[:2000]

    mem, action = upsert_canonical_memory(
        user=user,
        title=title,
        content=content,
        key="",
        category="learning",
        tags=["learning", "doubt", "explicit_save"],
        source_message=source_message or question,
        explicit=True,
        importance=6,
    )
    if not mem:
        return {
            "ok": False,
            "user_message": "I couldn’t save that learning note. Nothing was stored.",
            "response_type": "error",
        }
    return {
        "ok": True,
        "user_message": f"Saved to your learning notes ({mem.title}).",
        "response_type": "memory_confirmation",
        "data": {"memory_id": mem.id, "action": action},
        "actions": [],
        "memoriesSaved": [
            {"id": mem.id, "title": mem.title, "content": mem.content, "tags": mem.tags}
        ],
    }


def extract_learning_payload_from_history(history: list[dict[str, str]] | None) -> dict[str, Any] | None:
    """Best-effort: recover last doubt explanation from chat history for save confirm."""
    for turn in reversed(history or []):
        if (turn.get("role") or "").lower() != "assistant":
            continue
        content = (turn.get("content") or "").strip()
        if "Save this to your learning notes?" not in content:
            continue
        # Strip offer / practice / sources for the note body
        body = content.split("Save this to your learning notes?")[0].strip()
        if "Sources:" in body:
            body = body.split("Sources:")[0].strip()
        if not body:
            continue
        return {
            "title": f"Doubt note: {body[:60]}",
            "content": body[:1500],
            "question": "",
            "sources": [],
        }
    return None
