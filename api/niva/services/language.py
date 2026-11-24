"""Manglish / Malayalam language layer — detect, normalize, reply style."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("niva.language")

# Glossary: Manglish (romanized Malayalam) → English for routing / tools / retrieval
MANGLISH_GLOSSARY: dict[str, str] = {
    "innu": "today",
    "nale": "tomorrow",
    "innale": "yesterday",
    "kazhinja aazhcha": "last week",
    "kazhinja azhcha": "last week",
    "kazhinja maasam": "last month",
    "ee aazhcha": "this week",
    "ee azhcha": "this week",
    "ee maasam": "this month",
    "ee masam": "this month",
    "chilavu": "expense",
    "chilavayi": "spent",
    "ethra": "how much",
    "enthokke": "what all",
    "enthu": "what",
    "enthaanu": "what is",
    "und": "have",
    "illa": "don't have",
    "cheyyanam": "need to do",
    "cheythu": "did",
    "cheythathu": "did",
    "sahayikkamo": "can you help",
    "sahayiikkamo": "can you help",
    "njan": "I",
    "ente": "my",
    "oru": "a",
    "task": "task",
    "tasks": "tasks",
    "ormikkane": "remember this",
    "aaranu": "who am I",
    "engane": "how",
    "enganeyundu": "how is it",
    "sheri": "okay",
}

MANGLISH_EXAMPLES: list[tuple[str, str]] = [
    ("innu enthokke task und?", "what all tasks do I have today?"),
    ("nale enthu cheyyanam?", "what do I need to do tomorrow?"),
    ("ente chilavu ee aazhcha engane und?", "how is my spending this week?"),
    ("ee maasam ethra chilavayi?", "how much did I spend this month?"),
    ("innale njan enthokke cheythu?", "what all did I do yesterday?"),
    ("food-inu ethra chilavu ee maasam?", "how much food expense this month?"),
    ("add expense 250 for lunch", "add expense 250 for lunch"),
    ("sahayikkamo plan my day", "can you help plan my day"),
]

_ML_SCRIPT = re.compile(r"[\u0D00-\u0D7F]")
_MANGLISH_CUES = re.compile(
    r"\b("
    + "|".join(
        re.escape(k)
        for k in sorted(MANGLISH_GLOSSARY.keys(), key=len, reverse=True)
        if " " not in k
    )
    + r")\b",
    re.I,
)


def detect_language(text: str) -> str:
    """Return en | manglish | ml."""
    raw = (text or "").strip()
    if not raw:
        return "en"
    if _ML_SCRIPT.search(raw):
        return "ml"
    lower = raw.lower()
    # Multi-word glossary first
    hits = 0
    for phrase in MANGLISH_GLOSSARY:
        if " " in phrase and phrase in lower:
            hits += 2
    hits += len(_MANGLISH_CUES.findall(lower))
    # Common Manglish particles
    if re.search(r"\b(anu|alle|aano|ndo|undo|pattiche|sheri)\b", lower):
        hits += 1
    if hits >= 1:
        return "manglish"
    return "en"


def normalize_to_english(text: str) -> str:
    """Cheap glossary-based normalization for tools/routing (not a full translator)."""
    raw = (text or "").strip()
    if not raw:
        return raw
    if detect_language(raw) == "en":
        return raw

    out = raw
    # Longer phrases first
    for manglish, english in sorted(MANGLISH_GLOSSARY.items(), key=lambda x: -len(x[0])):
        out = re.sub(
            rf"(?<!\w){re.escape(manglish)}(?!\w)",
            english,
            out,
            flags=re.I,
        )
    # food-inu → food
    out = re.sub(r"\b([a-z]+)-inu\b", r"\1", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def glossary_prompt_block() -> str:
    lines = ["Manglish glossary (romanized Malayalam → English):"]
    for k, v in MANGLISH_GLOSSARY.items():
        lines.append(f"- {k} = {v}")
    lines.append("Examples:")
    for src, eng in MANGLISH_EXAMPLES:
        lines.append(f'- "{src}" → "{eng}"')
    return "\n".join(lines)


def get_reply_language_setting(user) -> str:
    """auto | en | manglish"""
    if not user:
        return "auto"
    try:
        from api.models import NivaCompanionSettings

        obj = NivaCompanionSettings.objects.filter(user=user).first()
        if obj and getattr(obj, "reply_language", None):
            val = (obj.reply_language or "auto").strip().lower()
            if val in ("auto", "en", "english"):
                return "auto" if val == "auto" else "en"
            if val in ("manglish", "ml", "malayalam"):
                return "manglish" if val == "manglish" else "manglish"
            return val if val in ("auto", "en", "manglish") else "auto"
    except Exception:
        pass
    return "auto"


def resolve_reply_language(user, detected: str) -> str:
    setting = get_reply_language_setting(user)
    if setting == "en":
        return "en"
    if setting == "manglish":
        return "manglish"
    # auto
    if detected == "ml":
        return "ml"
    if detected == "manglish":
        return "manglish"
    return "en"


def annotate_language(
    message: str,
    *,
    user=None,
) -> dict[str, Any]:
    detected = detect_language(message)
    normalized = normalize_to_english(message)
    reply_lang = resolve_reply_language(user, detected)
    return {
        "lang": detected,
        "normalized_english_query": normalized,
        "reply_language": reply_lang,
    }


def localize_reply(
    english_reply: str,
    *,
    reply_language: str,
    user_message: str = "",
) -> str:
    """
    Keep English tool facts; rewrite tone/language when reply_language is manglish/ml.
    Numbers, ₹, and titles stay intact.
    """
    reply = (english_reply or "").strip()
    if not reply:
        return reply
    if reply_language in ("en", "", None):
        return reply
    if reply_language == "manglish":
        # Cheap deterministic touch-ups for common openings; else Gemini
        touched = _manglish_phrase_touch(reply)
        if touched != reply:
            return touched
        return _gemini_localize(reply, target="manglish", user_message=user_message) or reply
    if reply_language == "ml":
        return _gemini_localize(reply, target="malayalam", user_message=user_message) or reply
    return reply


def _manglish_phrase_touch(reply: str) -> str:
    """Light Manglish flavor without losing facts — only safe prefix swaps."""
    replacements = [
        (r"^Done — ", "Sheri — "),
        (r"^Got it — ", "Okke, got it — "),
        (r"^For today, you ", "Innu nee "),
        (r"^For yesterday, you ", "Innale nee "),
        (r"^For this week, you ", "Ee aazhcha nee "),
        (r"^For this month, you ", "Ee maasam nee "),
        (r"^Spending for this month:", "Ee maasam chilavu:"),
        (r"^Spending for this week:", "Ee aazhcha chilavu:"),
        (r"^I don’t see any logged Dayflow activity for today\.", "Innu oru activity um kanunnilla."),
        (r"^I don’t see any logged Dayflow activity for yesterday\.", "Innale oru activity um kanunnilla."),
        (r"^No transactions found for this month\.", "Ee maasam oru transaction um illa."),
        (r"^No expenses logged for this month\.", "Ee maasam expense illa."),
    ]
    out = reply
    for pat, repl in replacements:
        new = re.sub(pat, repl, out)
        if new != out:
            return new
    return out


def _gemini_localize(reply: str, *, target: str, user_message: str = "") -> str | None:
    try:
        from api.assistant_service import CHAT_MODEL, _configure_gemini, _gemini_response_text

        genai = _configure_gemini()
        if not genai:
            return None
        style = (
            "romanized Malayalam mixed with English (Manglish). Natural, warm, short. "
            "Keep all numbers, ₹ amounts, task titles, and category names exactly as given."
            if target == "manglish"
            else "Malayalam script. Warm and short. Keep numbers, ₹ amounts, and English proper nouns unchanged."
        )
        prompt = (
            f"Rewrite this Dayflow assistant reply in {style}\n"
            f"User said: {user_message[:200]!r}\n"
            f"English reply:\n{reply[:1200]}\n\n"
            "Return ONLY the rewritten reply text, no quotes or preamble."
        )
        model = genai.GenerativeModel(
            CHAT_MODEL,
            generation_config={"temperature": 0.3},
        )
        resp = model.generate_content(prompt, request_options={"timeout": 20})
        text = (_gemini_response_text(resp) or "").strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text[:2000] if text else None
    except Exception as exc:
        logger.debug("localize failed: %s", exc)
        return None


def normalize_memory_text(text: str) -> str:
    """Store memories as English-normalized text so both languages hit the same data."""
    raw = (text or "").strip()
    if not raw:
        return raw
    if detect_language(raw) == "en":
        return raw
    glossed = normalize_to_english(raw)
    # If still heavily non-English, try Gemini one-shot
    if detect_language(glossed) != "en" or glossed == raw:
        translated = _gemini_to_english(raw)
        if translated:
            return translated
    return glossed


def _gemini_to_english(text: str) -> str | None:
    try:
        from api.assistant_service import CHAT_MODEL, _configure_gemini, _gemini_response_text

        genai = _configure_gemini()
        if not genai:
            return None
        prompt = (
            "Translate this user memory/note into clear short English. "
            "Keep names and places. Return ONLY the English text.\n\n"
            f"{text[:800]}"
        )
        model = genai.GenerativeModel(CHAT_MODEL, generation_config={"temperature": 0.1})
        resp = model.generate_content(prompt, request_options={"timeout": 20})
        out = (_gemini_response_text(resp) or "").strip()
        return out[:1000] if out else None
    except Exception:
        return None
