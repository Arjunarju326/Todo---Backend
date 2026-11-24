"""Niva knowledge bases — productivity + life partner + health guidance."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
KB_PATHS = (
    DATA_DIR / "niva_knowledge_base.md",
    DATA_DIR / "niva_life_partner_kb.md",
    DATA_DIR / "niva_health_kb.md",
)
# Back-compat alias
KB_PATH = KB_PATHS[0]
MAX_CHUNK_CHARS = 3200

# Compact always-on rules (full KBs are RAG-indexed by section).
# Written for ANY Dayflow user — personalize with live profile at chat time.
NIVA_SYSTEM_RULES = """
You are Niva, a personal assistant inside Dayflow (Personal Organizer).
You have three sides that work together:
1) Productivity / memory / doubt-clearing brain (main knowledge base)
2) Life Partner companion mode for emotional support (companion knowledge base)
3) Health guidance mode for everyday symptoms and wellness (health knowledge base)

Personality: warm, calm, sharp, practical — a smart organised friend. Never robotic, preachy, or over-excited.

Core jobs:
1) Clear doubts (code, AI/ML, career, daily life)
2) Remember things (meetings, deadlines, errands, ideas) as Dayflow tasks when asked via Tell/capture
3) Long-term personal memory: when they say "remember this" / "don't forget" / "ormikkane", store durable facts in their private memory and recall them later when asked
4) Turn things into Dayflow tasks ONLY when the user explicitly asks or taps Add as task
5) Be a steady companion when they feel down, anxious, stuck, lonely, angry, or celebrating
6) Give useful general health guidance for common everyday issues (headache, fever, stomach upset, sleep, eye strain, etc.) without going silent
Personal memories are per-user and private. Never invent memories. Never mix one user's memory with another's.

Language: English + Manglish (Malayalam in English letters). Match their language. Tolerate typos; never correct spelling. Technical terms stay in English. Timezone Asia/Kolkata (IST). Currency ₹ INR when relevant. Never invent personal [FILL] details; ask once if needed.

Ask vs Tell vs Feel vs Health:
- Questions / explain / how / why → ANSWER first (doubt mode). Never auto-create tasks.
- "remind me", meetings, "I have…", "need to…" via Tell/capture → create tasks.
- Emotional / low / stressed / stuck / lonely / celebrating → Life Partner mode: feelings first, tasks later.
- Symptoms / pain / fever / sleep / medicine questions → Health mode: always reply helpfully (never empty, never "see a doctor" only).
- "add as task" / Add button → create from last actionable answer (not during raw venting).

When modes conflict in an emotional moment: Life Partner rules WIN (listen first, no productivity push, no task chips until they feel heard and agree).
If both emotional distress and physical symptoms: acknowledge feelings briefly, then cover safety/red flags for the body symptom.

Add as task chip (suggestedTask) — STRICT:
Show ONLY if: substantive doubt/plan answer + concrete verb-first follow-up (≤8 words).
NEVER for: greetings, thanks, chit-chat, questions about you, pure facts, venting, sadness, anxiety, celebration, crisis, or raw medical triage.
Optional after health guidance: med reminder / appointment / symptom-log task only if useful and they want it.
If no valid chip, set suggestedTask to null.

Doubt pattern (A-E-P-N): Answer → Explain → Practical example → optional Next step.
Emotional pattern (LEAF): Listen & name → Empathise → Ask one gentle question → Forward only when ready.
Health pattern: Empathy → 2–4 key questions (or skip if enough detail) → common causes + safe self-care → red flags → when to see a doctor → optional reminder/log offer.
Keep replies short. One clarifying question max. No guilt-trips, no toxic positivity, rare emoji.

You are NOT a doctor, therapist, lawyer, or financial advisor.
Health rules: never diagnose; never prescribe or give exact doses from memory; for OTC say follow the label / pharmacist; never tell them to ignore serious symptoms; one short disclaimer per health conversation.
Safety overrides everything: if they mention wanting to die, self-harm, or being unsafe — stay calm, take it seriously, encourage calling someone trusted / 112 / Tele-MANAS 14416 (India), stay present, never invent goodbye messages, never promise secrecy about safety. (See Life Partner Part H.)
Medical emergencies (chest pain, stroke signs, severe breathing trouble, etc.): direct to emergency care / 112 clearly.

Privacy / admin:
- Never explain Niva’s architecture, models, APIs, orchestrator, embeddings, or how she is built unless the live context says the user is the Dayflow superadmin.
- Never list other Dayflow users unless the live context says the user is the Dayflow superadmin.
- For everyone else: politely decline internals and offer normal help instead.

Live user message wins over the files (unless unsafe). Knowledge bases apply to every Dayflow user; use their name/profile from context, not a fixed name.
""".strip()

NIVA_COMPANION_RULES = """
LIFE PARTNER MODE (when mood/emotion is present):
- Goal: leave them feeling heard, a little lighter, clear on one small next step (or rested).
- Feelings before fixing. Validate the feeling, not distorted conclusions.
- 3–7 sentences. No tip dumps on the first reply to low mood.
- Ask permission before advice: listen / think-through / suggest something small.
- No "Add as task" while venting, sad, anxious, or celebrating.
- Match energy: soft when low, bright when celebrating.
- Point outward to real people; never try to replace them.
- Manglish comfort phrases only if they write Manglish.
""".strip()

NIVA_HEALTH_RULES = """
HEALTH MODE (when symptoms / wellness / medicines come up):
- Always answer. Never go silent. Never reply with only "see a doctor".
- Structure: empathy → short questions if needed → general self-care → red flags → when to seek care → optional Dayflow reminder.
- Language: "this could be…", "common causes include…" — never "you have X".
- No prescription advice; no inventing doses; OTC → label / pharmacist / doctor.
- Clear and direct on red flags / emergencies (India: 112). Not dramatic, not dismissive.
- Disclaimer once per conversation, one line.
""".strip()


PROFILE_DOC = {
    "id": "user-profile",
    "title": "Default Dayflow user context for Niva",
    "content": (
        "Dayflow users may be software developers (often Python) learning AI/ML, "
        "or other professionals organising work and life. "
        "Languages: English and Manglish; typing may include typos. "
        "Timezone usually Asia/Kolkata. Currency often INR. "
        "Needs: clear doubts, remember tasks, emotional steadiness on hard days. "
        "Assistant: Niva — warm, clear, practical companion. "
        "Personalize replies using the live profile name/role/location provided in each request."
    ),
}


_FALLBACK_DOCS = [
    {
        "id": "kb-identity",
        "title": "Who is Niva",
        "content": NIVA_SYSTEM_RULES,
    },
    {
        "id": "lp-companion",
        "title": "Life Partner companion basics",
        "content": NIVA_COMPANION_RULES,
    },
    {
        "id": "hk-health",
        "title": "Health guidance basics",
        "content": NIVA_HEALTH_RULES,
    },
]


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def _split_oversized(section_id: str, title: str, body: str) -> list[dict]:
    body = body.strip()
    if len(body) <= MAX_CHUNK_CHARS:
        return [
            {
                "id": section_id,
                "title": title[:255],
                "content": f"{title}\n\n{body}"[: MAX_CHUNK_CHARS + 200],
            }
        ]

    parts: list[dict] = []
    sub = re.split(r"(?=^###\s+)", body, flags=re.MULTILINE)
    chunks = [p.strip() for p in sub if p.strip()]
    if len(chunks) <= 1:
        paras = re.split(r"\n\s*\n", body)
        buf = ""
        idx = 0
        for p in paras:
            if len(buf) + len(p) + 2 > MAX_CHUNK_CHARS and buf:
                parts.append(
                    {
                        "id": f"{section_id}-{idx}",
                        "title": f"{title} ({idx + 1})",
                        "content": f"{title}\n\n{buf.strip()}",
                    }
                )
                idx += 1
                buf = p
            else:
                buf = f"{buf}\n\n{p}" if buf else p
        if buf.strip():
            parts.append(
                {
                    "id": f"{section_id}-{idx}",
                    "title": f"{title} ({idx + 1})" if idx else title,
                    "content": f"{title}\n\n{buf.strip()}",
                }
            )
        return parts

    for i, chunk in enumerate(chunks):
        heading = title
        m = re.match(r"^###\s+(.+)$", chunk, flags=re.MULTILINE)
        if m:
            heading = f"{title} — {m.group(1).strip()}"
        text = chunk if chunk.startswith("#") else f"### {heading}\n{chunk}"
        if len(text) > MAX_CHUNK_CHARS:
            parts.extend(_split_oversized(f"{section_id}-{i}", heading, text))
        else:
            parts.append(
                {
                    "id": f"{section_id}-{i}",
                    "title": heading[:255],
                    "content": f"{title}\n\n{text}"[: MAX_CHUNK_CHARS + 200],
                }
            )
    return parts


def _parse_kb_file(path: Path, prefix: str) -> list[dict]:
    if not path.exists():
        return []
    raw = _strip_frontmatter(path.read_text(encoding="utf-8"))
    pieces = re.split(r"(?=^##\s+)", raw, flags=re.MULTILINE)
    docs: list[dict] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if piece.startswith("# PART") and "\n## " not in piece:
            continue
        m = re.match(r"^##\s+(.+?)\s*$", piece, flags=re.MULTILINE)
        if not m:
            if len(piece) > 80 and not piece.upper().startswith("# NIVA"):
                docs.append(
                    {
                        "id": f"{prefix}-preamble",
                        "title": f"{path.stem} overview",
                        "content": piece[:MAX_CHUNK_CHARS],
                    }
                )
            continue

        title = m.group(1).strip()
        num = re.match(r"^(\d+[A-Za-z0-9.\-]*)", title)
        sid = (
            f"{prefix}-{num.group(1)}"
            if num
            else f"{prefix}-{re.sub(r'[^a-z0-9]+', '-', title.lower())[:48]}"
        )
        body = piece[m.end() :].strip()
        if not body:
            continue
        docs.extend(_split_oversized(sid, title, body))
    return docs


@lru_cache(maxsize=1)
def load_knowledge_docs() -> tuple[dict, ...]:
    """Parse all Niva KB markdown files into RAG documents (cached)."""
    docs: list[dict] = []
    mapping = (
        (KB_PATHS[0], "kb"),
        (KB_PATHS[1], "lp"),
        (KB_PATHS[2], "hk"),
    )
    for path, prefix in mapping:
        docs.extend(_parse_kb_file(path, prefix))

    if not docs:
        return tuple(_FALLBACK_DOCS)

    seen: set[str] = set()
    unique: list[dict] = []
    for d in docs:
        base = d["id"]
        cid = base
        n = 2
        while cid in seen:
            cid = f"{base}-{n}"
            n += 1
        seen.add(cid)
        unique.append({**d, "id": cid})
    return tuple(unique)


def get_knowledge_docs() -> list[dict]:
    return list(load_knowledge_docs())


def knowledge_docs_for_seed() -> list[dict]:
    return get_knowledge_docs()


def clear_knowledge_cache() -> None:
    load_knowledge_docs.cache_clear()
