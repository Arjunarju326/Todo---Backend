"""Smrti — Gemini + RAG helper focused on remembering tasks and responsibilities."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, time as dtime
from typing import Any

from django.db import connection
from django.utils import timezone

from .assistant_knowledge import KNOWLEDGE_DOCS, PROFILE_DOC
from .models import (
    AssistantBrief,
    AssistantChunk,
    AssistantSourceType,
    Habit,
    LearningGoal,
    Note,
    Task,
    TaskStatus,
    UserSettings,
)

ASSISTANT_NAME = "Smrti"
EMBED_MODEL = "models/gemini-embedding-001"
CHAT_MODEL = "gemini-2.5-flash"


def _env(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    if val is None:
        return default
    val = str(val).strip()
    if (val.startswith("'") and val.endswith("'")) or (
        val.startswith('"') and val.endswith('"')
    ):
        val = val[1:-1]
    return val


def get_profile() -> dict[str, str]:
    settings = UserSettings.objects.first()
    name = (settings.user_name if settings else None) or "friend"
    return {
        "assistant_name": ASSISTANT_NAME,
        "user_name": name,
        "role": _env(
            "ASSISTANT_PROFILE_ROLE",
            "Python developer learning AI/ML",
        ),
        "location": _env(
            "ASSISTANT_PROFILE_LOCATION",
            "Kannur, Kerala, India",
        ),
    }


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return -1.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def ensure_pgvector() -> bool:
    try:
        with connection.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        return True
    except Exception:
        return False


def _configure_gemini():
    api_key = _env("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        return genai
    except Exception:
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    genai = _configure_gemini()
    if not genai or not texts:
        return [[] for _ in texts]
    out: list[list[float]] = []
    for text in texts:
        try:
            result = genai.embed_content(
                model=EMBED_MODEL,
                content=text[:6000],
                task_type="retrieval_document",
            )
            emb = result.get("embedding") if isinstance(result, dict) else None
            if emb is None and hasattr(result, "embedding"):
                emb = result.embedding
            out.append(list(emb or []))
        except Exception:
            out.append([])
    return out


def embed_query(text: str) -> list[float]:
    genai = _configure_gemini()
    if not genai or not text.strip():
        return []
    try:
        result = genai.embed_content(
            model=EMBED_MODEL,
            content=text[:6000],
            task_type="retrieval_query",
        )
        emb = result.get("embedding") if isinstance(result, dict) else None
        if emb is None and hasattr(result, "embedding"):
            emb = result.embedding
        return list(emb or [])
    except Exception:
        return []


def _upsert_chunk(
    source_type: str,
    source_id: str,
    title: str,
    content: str,
    embedding: list[float] | None = None,
    metadata: dict | None = None,
):
    obj, _ = AssistantChunk.objects.update_or_create(
        source_type=source_type,
        source_id=source_id,
        defaults={
            "title": title[:255],
            "content": content,
            "embedding": embedding or [],
            "metadata": metadata or {},
        },
    )
    return obj


def seed_knowledge(force_embed: bool = True) -> int:
    docs = [PROFILE_DOC, *KNOWLEDGE_DOCS]
    count = 0
    for doc in docs:
        source = (
            AssistantSourceType.PROFILE
            if doc["id"] == "user-profile"
            else AssistantSourceType.KNOWLEDGE
        )
        existing = AssistantChunk.objects.filter(
            source_type=source, source_id=doc["id"]
        ).first()
        need_embed = force_embed and (
            not existing or not (existing.embedding or [])
        )
        emb: list[float] = []
        if need_embed:
            emb = embed_texts([f"{doc['title']}\n{doc['content']}"])[0]
        elif existing:
            emb = existing.embedding if isinstance(existing.embedding, list) else []
        _upsert_chunk(
            source_type=source,
            source_id=doc["id"],
            title=doc["title"],
            content=doc["content"],
            embedding=emb,
            metadata={"kind": "knowledge"},
        )
        count += 1
    return count


def index_workspace(force_embed: bool = True) -> dict[str, int]:
    ensure_pgvector()
    seeded = seed_knowledge(force_embed=force_embed)

    task_rows = []
    for t in Task.objects.exclude(status=TaskStatus.DONE):
        due = t.due_date.isoformat() if t.due_date else "no due date"
        text = (
            f"Pending task: {t.title}. Category {t.category}. Priority {t.priority}. "
            f"Status {t.status}. Due {due}. {t.description or ''}"
        )
        task_rows.append((str(t.id), t.title, text, {"priority": t.priority}))

    habit_rows = []
    for h in Habit.objects.all()[:20]:
        text = f"Habit: {h.title}. Streak {h.streak} days. {getattr(h, 'description', '') or ''}"
        habit_rows.append((str(h.id), h.title, text, {"streak": h.streak}))

    learn_rows = []
    for g in LearningGoal.objects.all()[:20]:
        pct = getattr(g, "progress_percentage", None) or 0
        text = (
            f"Learning goal: {g.title}. Progress {pct}%. Status {g.status}. "
            f"{getattr(g, 'notes', '') or ''}"
        )
        learn_rows.append((str(g.id), g.title, text, {"progress": float(pct)}))

    note_rows = []
    for n in Note.objects.all()[:15]:
        text = f"Note: {n.title}. {n.content or ''}"
        note_rows.append((str(n.id), n.title, text, {"category": n.category}))

    batches = [
        (AssistantSourceType.TASK, task_rows),
        (AssistantSourceType.HABIT, habit_rows),
        (AssistantSourceType.LEARNING, learn_rows),
        (AssistantSourceType.NOTE, note_rows),
    ]

    counts = {"knowledge": seeded, "tasks": 0, "habits": 0, "learning": 0, "notes": 0}
    key_map = {
        AssistantSourceType.TASK: "tasks",
        AssistantSourceType.HABIT: "habits",
        AssistantSourceType.LEARNING: "learning",
        AssistantSourceType.NOTE: "notes",
    }

    live_task_ids = {r[0] for r in task_rows}
    AssistantChunk.objects.filter(source_type=AssistantSourceType.TASK).exclude(
        source_id__in=live_task_ids
    ).delete()

    for source_type, rows in batches:
        for sid, title, content, meta in rows:
            existing = AssistantChunk.objects.filter(
                source_type=source_type, source_id=sid
            ).first()
            content_changed = not existing or existing.content != content
            need_embed = force_embed and (
                content_changed or not (existing and existing.embedding)
            )
            emb: list[float] = []
            if need_embed:
                emb = embed_texts([content])[0]
            elif existing and isinstance(existing.embedding, list):
                emb = existing.embedding
            _upsert_chunk(source_type, sid, title, content, emb, meta)
            counts[key_map[source_type]] += 1

    return counts


def retrieve(query: str, k: int = 8) -> list[AssistantChunk]:
    q = embed_query(query)
    chunks = list(AssistantChunk.objects.all()[:400])
    if q:
        scored = []
        for c in chunks:
            emb = c.embedding if isinstance(c.embedding, list) else []
            scored.append((_cosine(q, emb), c))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for score, c in scored[:k] if score > 0.05]
        if top:
            return top

    # Keyword fallback
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    ranked = []
    for c in chunks:
        blob = f"{c.title} {c.content}".lower()
        score = sum(1 for t in tokens if t in blob)
        ranked.append((score, c))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in ranked[:k] if s > 0] or chunks[:k]


def _live_task_snapshot() -> dict[str, Any]:
    now = timezone.now()
    start = timezone.make_aware(datetime.combine(now.date(), dtime.min))
    end = timezone.make_aware(datetime.combine(now.date(), dtime.max))
    open_qs = Task.objects.exclude(status=TaskStatus.DONE)
    overdue = open_qs.filter(due_date__lt=start)
    due_today = open_qs.filter(due_date__gte=start, due_date__lte=end)
    no_date = open_qs.filter(due_date__isnull=True)
    return {
        "overdue": list(overdue.values("id", "title", "priority", "category")[:8]),
        "due_today": list(due_today.values("id", "title", "priority", "category")[:8]),
        "undated": list(no_date.values("id", "title", "priority", "category")[:5]),
        "open_count": open_qs.count(),
        "overdue_count": overdue.count(),
        "due_today_count": due_today.count(),
    }


def _fallback_briefing(profile: dict, snap: dict) -> dict[str, Any]:
    overdue = snap["overdue"]
    due_today = snap["due_today"]
    if overdue:
        top = overdue[0]["title"]
        greeting = f"Hey {profile['user_name']} — Smrti here. You have {snap['overdue_count']} overdue."
        task_nudge = f"Start with: “{top}”. Clear overdue before new work."
    elif due_today:
        top = due_today[0]["title"]
        greeting = f"Good to see you, {profile['user_name']}. Smrti has your day mapped."
        task_nudge = f"Focus next: “{top}” ({snap['due_today_count']} due today)."
    elif snap["open_count"]:
        greeting = f"Hi {profile['user_name']} — Smrti’s watching your open list."
        task_nudge = f"You have {snap['open_count']} open tasks. Pick one and finish it."
    else:
        greeting = f"{profile['user_name']}, your board looks clear — nice work."
        task_nudge = "Capture any new responsibility now so you don’t forget later."

    return {
        "assistantName": ASSISTANT_NAME,
        "greeting": greeting,
        "taskNudge": task_nudge,
        "methodTip": (
            "Use a 5-minute capture + triage: write new duties into Dayflow, then do the "
            "single next action on the top overdue or due-today item."
        ),
        "newsBite": (
            f"For a {profile['role']} in {profile['location']}: keep one short AI/ML practice "
            "block today — even 25 minutes beats skipping."
        ),
        "responsibilityFocus": (
            "Remember: work deliverables, bills, habits, and learning all count as responsibilities."
        ),
        "avatarMood": "encourage",
        "sources": ["fallback"],
        "generatedBy": "fallback",
    }


def _parse_json_loose(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def generate_briefing(force_refresh: bool = False) -> dict[str, Any]:
    profile = get_profile()
    today = timezone.localdate()
    if not force_refresh:
        cached = AssistantBrief.objects.filter(brief_date=today).first()
        if cached and cached.payload:
            return {**cached.payload, "cached": True}

    # Fast path for popup: text knowledge + tasks (embeddings via /reindex)
    try:
        if AssistantChunk.objects.filter(
            source_type=AssistantSourceType.KNOWLEDGE
        ).count() < 3:
            seed_knowledge(force_embed=False)
        # Refresh task chunk text without waiting on embeddings
        index_workspace(force_embed=False)
    except Exception:
        pass

    snap = _live_task_snapshot()
    query = (
        "Help me remember pending tasks, overdue work, and responsibilities. "
        "Suggest one method and one short tech/learning tip for a Python AI learner in Kannur."
    )
    chunks = retrieve(query, k=8)
    context = "\n\n".join(
        f"[{c.source_type}] {c.title}: {c.content}" for c in chunks
    )
    snap_text = json.dumps(snap, default=str)

    genai = _configure_gemini()
    payload = None
    if genai:
        prompt = f"""You are {ASSISTANT_NAME}, a warm memory assistant inside Dayflow.
User: {profile['user_name']}, {profile['role']}, lives in {profile['location']}.
Core job: help them REMEMBER tasks, work, and responsibilities — never shame them.

Live task snapshot JSON:
{snap_text}

Retrieved knowledge/context:
{context[:7000]}

Return ONLY valid JSON with keys:
greeting (short spoken line, energetic but kind),
taskNudge (specific next task/responsibility to do now),
methodTip (one practical method to stop forgetting work),
newsBite (one short Python/AI or India-tech tip relevant today),
responsibilityFocus (one line about duties they may overlook),
avatarMood (one of: welcome, encourage, focus, celebrate)

No markdown. Keep each string under 220 characters."""
        try:
            model = genai.GenerativeModel(CHAT_MODEL)
            resp = model.generate_content(
                prompt, request_options={"timeout": 45}
            )
            text = getattr(resp, "text", None) or ""
            parsed = _parse_json_loose(text)
            if parsed:
                payload = {
                    "assistantName": ASSISTANT_NAME,
                    "greeting": parsed.get("greeting") or f"Hey {profile['user_name']}!",
                    "taskNudge": parsed.get("taskNudge") or "",
                    "methodTip": parsed.get("methodTip") or "",
                    "newsBite": parsed.get("newsBite") or "",
                    "responsibilityFocus": parsed.get("responsibilityFocus") or "",
                    "avatarMood": parsed.get("avatarMood") or "encourage",
                    "sources": [c.source_id or c.title for c in chunks[:5]],
                    "generatedBy": "gemini",
                }
        except Exception:
            payload = None

    if not payload:
        payload = _fallback_briefing(profile, snap)

    payload["profile"] = profile
    payload["stats"] = {
        "openCount": snap["open_count"],
        "overdueCount": snap["overdue_count"],
        "dueTodayCount": snap["due_today_count"],
    }
    payload["cached"] = False

    AssistantBrief.objects.update_or_create(
        brief_date=today, defaults={"payload": payload}
    )
    return payload
