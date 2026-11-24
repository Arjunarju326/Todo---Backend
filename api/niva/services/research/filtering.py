from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def filter_results(web: dict[str, Any] | None) -> dict[str, Any] | None:
    if not web:
        return None
    seen = set()
    cleaned = []
    for item in web.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        if not url and not content:
            continue
        host = urlparse(url).netloc.lower() if url else ""
        key = host + "|" + title.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            {
                "title": title[:200],
                "url": url[:400],
                "content": content[:700],
            }
        )
    return {
        "answer": (web.get("answer") or "").strip()[:1200],
        "results": cleaned[:6],
        "query": web.get("query") or "",
        "cached": web.get("cached", False),
    }
