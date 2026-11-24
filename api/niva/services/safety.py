"""Safety helpers — log redaction, rate-limit constants, scoping notes."""

from __future__ import annotations

import re
from typing import Any

# Never log raw secrets
_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}\b"),  # some Google-style keys
    re.compile(r"(?i)GEMINI_API_KEY\s*=\s*\S+"),
    re.compile(r"(?i)TAVILY_API_KEY\s*=\s*\S+"),
    re.compile(r"(?i)POSTGRES_PASSWORD\s*=\s*\S+"),
]


def redact_text(text: str, *, max_len: int = 500) -> str:
    raw = (text or "").replace("\n", " ").strip()
    out = raw
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out


def redact_mapping(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    safe: dict[str, Any] = {}
    for k, v in data.items():
        key = str(k)
        if re.search(r"(?i)(password|secret|token|api_key|authorization)", key):
            safe[key] = "[REDACTED]"
        elif isinstance(v, str):
            safe[key] = redact_text(v, max_len=240)
        elif isinstance(v, dict):
            safe[key] = redact_mapping(v)
        elif isinstance(v, list):
            safe[key] = [
                redact_mapping(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            safe[key] = v
    return safe


def assert_user_scoped(qs_model_name: str, user_id: int | None) -> None:
    """Dev-time documentation helper — real scoping is in every ORM filter."""
    if user_id is None:
        raise ValueError(f"{qs_model_name} queries must include user_id")
