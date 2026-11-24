from __future__ import annotations

from typing import Any


def build_citations(web: dict[str, Any] | None) -> list[dict[str, str]]:
    if not web:
        return []
    out = []
    for r in web.get("results") or []:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        out.append({"title": (r.get("title") or "Source")[:200], "url": url})
    return out


def format_research_reply(web: dict[str, Any], *, user_name: str = "there") -> str:
    parts = [f"Here’s what I found online, {user_name}:"]
    if web.get("answer"):
        parts.append(web["answer"])
    for r in (web.get("results") or [])[:3]:
        title = r.get("title") or "Source"
        snippet = (r.get("content") or "")[:200]
        url = r.get("url") or ""
        line = f"• {title}: {snippet}"
        if url:
            line += f"\n  {url}"
        parts.append(line)
    if len(parts) == 1:
        parts.append("I couldn’t get useful search hits — try a more specific question.")
    return "\n".join(parts)
