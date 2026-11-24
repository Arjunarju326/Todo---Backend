"""Smrti — Gemini + RAG helper focused on remembering tasks and responsibilities."""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, time as dtime
from typing import Any

from django.db import connection
from django.utils import timezone

from .assistant_knowledge import (
    NIVA_COMPANION_RULES,
    NIVA_HEALTH_RULES,
    NIVA_SYSTEM_RULES,
    PROFILE_DOC,
    knowledge_docs_for_seed,
)
from .models import (
    AssistantBrief,
    AssistantChunk,
    AssistantMemory,
    AssistantSourceType,
    Habit,
    LearningGoal,
    Note,
    Task,
    TaskStatus,
    UserSettings,
)

ASSISTANT_NAME = "Niva"
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


def get_profile(user=None) -> dict[str, str]:
    settings = None
    if user is not None and getattr(user, "is_authenticated", False):
        settings = UserSettings.objects.filter(user=user).first()
    name = (settings.user_name if settings else None) or getattr(user, "first_name", None) or getattr(user, "username", None) or "friend"
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


def _wants_web_search(message: str) -> bool:
    """User wants live web/news answers (Tavily), not only KB/memory."""
    lower = (message or "").lower()
    cues = (
        "google",
        "search online",
        "search the web",
        "look up",
        "look it up",
        "check online",
        "from the web",
        "from google",
        "latest news",
        "news about",
        "headlines",
        "current events",
        "what's happening",
        "whats happening",
        "what is happening",
        "breaking news",
        "live update",
        "live news",
        "check the news",
        "any news",
        "tech news",
        "browse",
        "web search",
        "search for",
        "find online",
        "check the issue",
        "check issue",
        "latest update",
        "latest updates",
        "recent update",
        "what does google",
    )
    if any(c in lower for c in cues):
        return True
    if re.search(r"\b(news|headline|headlines)\b", lower):
        return True
    if re.search(r"\b(today|latest|current)\b.{0,40}\b(news|update|updates|issue|issues)\b", lower):
        return True
    return False


def _web_topic_for_query(message: str) -> str:
    lower = (message or "").lower()
    if re.search(r"\b(news|headline|headlines|breaking)\b", lower):
        return "news"
    return "general"


def tavily_search(
    query: str,
    *,
    topic: str = "general",
    max_results: int = 5,
    search_depth: str = "basic",
) -> dict[str, Any] | None:
    """
    Live web search via Tavily.
    Free plan: 1000 credits/month; basic search = 1 credit, advanced = 2.
    """
    api_key = _env("TAVILY_API_KEY")
    q = (query or "").strip()
    if not api_key or not q:
        return None
    payload = {
        "api_key": api_key,
        "query": q[:400],
        "topic": topic if topic in ("general", "news") else "general",
        "search_depth": search_depth if search_depth in ("basic", "advanced") else "basic",
        "include_answer": True,
        "max_results": max(1, min(int(max_results or 5), 8)),
    }
    try:
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        results = []
        for item in data.get("results") or []:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            content = (item.get("content") or "").strip()
            if title or content:
                results.append(
                    {
                        "title": title[:200],
                        "url": url[:400],
                        "content": content[:700],
                    }
                )
        return {
            "answer": (data.get("answer") or "").strip()[:1200],
            "results": results,
            "query": q,
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    except Exception:
        return None


def _format_web_context(web: dict[str, Any] | None) -> str:
    if not web:
        return ""
    lines = [f"WEB SEARCH (live via Tavily) for: {web.get('query') or ''}"]
    if web.get("answer"):
        lines.append(f"Tavily summary: {web['answer']}")
    for i, r in enumerate(web.get("results") or [], 1):
        lines.append(
            f"{i}. {r.get('title') or 'Result'}\n"
            f"   {r.get('content') or ''}\n"
            f"   Source: {r.get('url') or ''}"
        )
    return "\n".join(lines).strip()


def _web_search_reply(web: dict[str, Any], profile: dict[str, str] | None = None) -> str:
    """Offline-friendly reply when Gemini is down but Tavily returned results."""
    name = (profile or {}).get("user_name") or "there"
    parts = [f"Here’s what I found online for you, {name}:"]
    if web.get("answer"):
        parts.append(web["answer"])
    for r in (web.get("results") or [])[:3]:
        title = r.get("title") or "Source"
        snippet = (r.get("content") or "")[:220]
        url = r.get("url") or ""
        line = f"• {title}: {snippet}"
        if url:
            line += f" ({url})"
        parts.append(line)
    if len(parts) == 1:
        parts.append("I couldn’t get useful search hits — try a more specific question.")
    else:
        parts.append("Say if you want me to go deeper on any of these.")
    return "\n".join(parts)


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
    user=None,
):
    obj, _ = AssistantChunk.objects.update_or_create(
        user=user,
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


def seed_knowledge(force_embed: bool = True, user=None) -> int:
    docs = [PROFILE_DOC, *knowledge_docs_for_seed()]
    count = 0
    for doc in docs:
        source = (
            AssistantSourceType.PROFILE
            if doc["id"] == "user-profile"
            else AssistantSourceType.KNOWLEDGE
        )
        existing = AssistantChunk.objects.filter(
            user=user, source_type=source, source_id=doc["id"]
        ).first()
        content_changed = bool(
            existing and (existing.content or "") != (doc.get("content") or "")
        )
        missing_emb = not existing or not (existing.embedding or [])
        # Re-embed on content change; otherwise only when forced + missing
        need_embed = content_changed or (force_embed and missing_emb)
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
            metadata={"kind": "niva_kb", "version": "1.0.0"},
            user=user,
        )
        count += 1
    return count


def index_workspace(force_embed: bool = True, user=None) -> dict[str, int]:
    ensure_pgvector()
    seeded = seed_knowledge(force_embed=force_embed, user=user)

    task_qs = Task.objects.filter(user=user).exclude(status=TaskStatus.DONE)
    task_rows = []
    for t in task_qs:
        due = t.due_date.isoformat() if t.due_date else "no due date"
        text = (
            f"Pending task: {t.title}. Category {t.category}. Priority {t.priority}. "
            f"Status {t.status}. Due {due}. {t.description or ''}"
        )
        task_rows.append((str(t.id), t.title, text, {"priority": t.priority}))

    habit_rows = []
    for h in Habit.objects.filter(user=user)[:20]:
        text = f"Habit: {h.name}. Streak {h.streak} days. Category {h.category}."
        habit_rows.append((str(h.id), h.name, text, {"streak": h.streak}))

    learn_rows = []
    for g in LearningGoal.objects.filter(user=user)[:20]:
        pct = getattr(g, "progress_percentage", None) or 0
        text = (
            f"Learning goal: {g.title}. Progress {pct}%. Status {g.status}. "
            f"{getattr(g, 'notes', '') or ''}"
        )
        learn_rows.append((str(g.id), g.title, text, {"progress": float(pct)}))

    note_rows = []
    for n in Note.objects.filter(user=user)[:15]:
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
    AssistantChunk.objects.filter(user=user, source_type=AssistantSourceType.TASK).exclude(
        source_id__in=live_task_ids
    ).delete()

    for source_type, rows in batches:
        for sid, title, content, meta in rows:
            existing = AssistantChunk.objects.filter(
                user=user, source_type=source_type, source_id=sid
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
            _upsert_chunk(source_type, sid, title, content, emb, meta, user=user)
            counts[key_map[source_type]] += 1

    return counts


def retrieve(query: str, k: int = 8, user=None) -> list[AssistantChunk]:
    q = embed_query(query)
    chunk_qs = AssistantChunk.objects.filter(user=user)
    chunks = list(chunk_qs[:400])
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


def _task_row(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "description": (t.description or "")[:400],
        "priority": t.priority,
        "category": t.category,
        "status": t.status,
        "dueDate": t.due_date.isoformat() if t.due_date else None,
        "createdAt": t.created_at.isoformat() if t.created_at else None,
    }


def _live_task_snapshot(user=None) -> dict[str, Any]:
    now = timezone.localtime()
    start = timezone.make_aware(datetime.combine(now.date(), dtime.min))
    end = timezone.make_aware(datetime.combine(now.date(), dtime.max))
    week_end = start + timedelta(days=7)
    open_qs = (
        Task.objects.filter(user=user)
        .exclude(status=TaskStatus.DONE)
        .order_by("due_date", "-priority", "-created_at")
    )
    overdue = list(open_qs.filter(due_date__lt=start)[:10])
    dated_today = list(open_qs.filter(due_date__gte=start, due_date__lte=end)[:10])
    no_date = list(open_qs.filter(due_date__isnull=True)[:8])
    # Match Tasks UI: undated open tasks belong in "today"
    due_today = dated_today + [t for t in no_date if t.id not in {x.id for x in dated_today}]
    due_today = due_today[:12]
    upcoming = list(
        open_qs.filter(due_date__gt=end, due_date__lte=week_end)[:8]
    )
    recent = list(
        Task.objects.filter(user=user)
        .order_by("-created_at")[:8]
    )
    in_progress = list(
        open_qs.filter(status=TaskStatus.IN_PROGRESS)[:8]
    )
    dated_today_count = open_qs.filter(due_date__gte=start, due_date__lte=end).count()
    undated_count = open_qs.filter(due_date__isnull=True).count()
    return {
        "overdue": [_task_row(t) for t in overdue],
        "due_today": [_task_row(t) for t in due_today],
        "upcoming": [_task_row(t) for t in upcoming],
        "undated": [_task_row(t) for t in no_date],
        "in_progress": [_task_row(t) for t in in_progress],
        "recent": [_task_row(t) for t in recent],
        "open_count": open_qs.count(),
        "overdue_count": open_qs.filter(due_date__lt=start).count(),
        "due_today_count": dated_today_count + undated_count,
        "now": now.isoformat(),
    }


def _format_task_lines(tasks: list[dict[str, Any]], limit: int = 8) -> list[str]:
    lines = []
    for t in tasks[:limit]:
        due = t.get("dueDate")
        due_bit = ""
        if due:
            try:
                dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                if timezone.is_aware(dt):
                    dt = timezone.localtime(dt)
                due_bit = f" · due {dt.strftime('%a %d %b, %I:%M %p')}"
            except Exception:
                due_bit = f" · due {due}"
        pri = t.get("priority") or "MEDIUM"
        cat = t.get("category") or ""
        lines.append(f"• {t.get('title')} ({pri}{', ' + cat if cat else ''}{due_bit})")
    return lines


def _tasks_status_reply(profile: dict[str, str], snap: dict[str, Any]) -> str:
    name = profile.get("user_name") or "there"
    parts = [
        f"Here’s your Dayflow task picture, {name}:",
        f"Open {snap.get('open_count', 0)} · Due today {snap.get('due_today_count', 0)} · Overdue {snap.get('overdue_count', 0)}.",
    ]
    if snap.get("overdue"):
        parts.append("Overdue:")
        parts.extend(_format_task_lines(snap["overdue"]))
    if snap.get("due_today"):
        parts.append("Due today:")
        parts.extend(_format_task_lines(snap["due_today"]))
    if snap.get("in_progress"):
        parts.append("In progress:")
        parts.extend(_format_task_lines(snap["in_progress"]))
    if not snap.get("overdue") and not snap.get("due_today"):
        if snap.get("undated"):
            parts.append("Open with no due date:")
            parts.extend(_format_task_lines(snap["undated"]))
        if snap.get("upcoming"):
            parts.append("Coming up this week:")
            parts.extend(_format_task_lines(snap["upcoming"]))
    if snap.get("open_count", 0) == 0:
        parts.append("Your board is clear — want me to help capture something new?")
    else:
        focus = (
            (snap.get("overdue") or snap.get("due_today") or snap.get("in_progress") or snap.get("undated") or [None])[0]
        )
        if focus:
            parts.append(
                f"I’d start with “{focus.get('title')}”. Want help on how to do that one?"
            )
    return "\n".join(parts)


def _find_task_for_help(message: str, user=None) -> Task | None:
    open_qs = list(
        Task.objects.filter(user=user)
        .exclude(status=TaskStatus.DONE)
        .order_by("due_date", "-priority", "-created_at")[:40]
    )
    if not open_qs:
        return None
    lower = (message or "").lower()
    # Prefer explicit title mention
    for t in open_qs:
        title = (t.title or "").lower()
        if len(title) >= 4 and title in lower:
            return t
    # Keyword overlap
    tokens = [tok for tok in re.split(r"\W+", lower) if len(tok) > 3]
    best = None
    best_score = 0
    for t in open_qs:
        blob = f"{t.title} {t.description or ''}".lower()
        score = sum(1 for tok in tokens if tok in blob)
        if score > best_score:
            best_score = score
            best = t
    if best_score >= 1:
        return best
    # Default to most urgent
    now = timezone.localtime()
    start = timezone.make_aware(datetime.combine(now.date(), dtime.min))
    overdue = [t for t in open_qs if t.due_date and t.due_date < start]
    if overdue:
        return overdue[0]
    due_today = [
        t
        for t in open_qs
        if t.due_date and start <= t.due_date <= timezone.make_aware(datetime.combine(now.date(), dtime.max))
    ]
    if due_today:
        return due_today[0]
    return open_qs[0]


def _offline_howto_for_task(task: Task) -> list[str]:
    """Concrete steps from task title when Gemini is unavailable (no live web)."""
    blob = f"{task.title} {task.description or ''}".lower()
    blob = blob.replace("junkins", "jenkins").replace("jenkin ", "jenkins ")
    if re.search(r"\bjenkins\b|\bci/?cd\b|\bpipeline\b", blob):
        return [
            "Suggested Jenkins setup path:",
            "1) Confirm the app build: local `npm`/`mvn`/`gradle` (or Docker) build succeeds.",
            "2) Install/open Jenkins → New Item → Pipeline (or Freestyle if you only need a shell job).",
            "3) Connect source: Git repo URL + credentials; set the branch used for Nexera ERP.",
            "4) Add a Jenkinsfile (or build steps): checkout → install deps → build → test → archive/artifact.",
            "5) Add deploy stage only after build is green (SSH/k8s/docker — match your server).",
            "6) Run once manually, fix the first red step, then enable a webhook or SCM poll.",
            "Tell me your stack (Node/Java/Docker) and where it deploys — I’ll tighten these steps.",
        ]
    if re.search(r"\bdocker\b|\bcontainer\b", blob):
        return [
            "Suggested Docker path:",
            "1) Write/verify a Dockerfile that builds the app cleanly.",
            "2) `docker build` locally and fix the first failing layer.",
            "3) Add `docker-compose` for app + DB if needed.",
            "4) Push image to your registry, then pull/run on the target host.",
            "Share the runtime (Node/Java/Python) if you want a sample Dockerfile.",
        ]
    if re.search(r"\berp\b|\bapi\b|\bdjango\b|\breact\b", blob):
        return [
            "Suggested build/ship path:",
            "1) Reproduce the feature/bug locally and note the exact command that fails.",
            "2) Fix config/env (DB URL, secrets, CORS) before bigger code changes.",
            "3) Add/run the smallest test or manual checklist that proves it works.",
            "4) Commit, then deploy/restart the matching service.",
            "Tell me the exact error or screen you’re on — I’ll give precise steps.",
        ]
    return [
        "Suggested way to finish it:",
        "1) Clarify the outcome — what “done” looks like in one sentence.",
        "2) Do the smallest next action for 10–15 minutes (open the file/doc/tool).",
        "3) Unblock: if stuck, write the blocker and ask me a precise doubt.",
        "4) Mark progress in Dayflow when you finish a chunk.",
    ]


def _task_help_reply(message: str, user=None, profile: dict[str, str] | None = None) -> str:
    profile = profile or {}
    task = _find_task_for_help(message, user=user)
    if not task:
        return (
            f"I don’t see open tasks for you right now, {profile.get('user_name') or 'there'}. "
            "Tell me what you’re working on and I’ll suggest how to do it — or say “remember this / add as task”."
        )
    due = ""
    if task.due_date:
        due = timezone.localtime(task.due_date).strftime("%a %d %b, %I:%M %p")
    desc = (task.description or "").strip()
    steps = [
        f"Let’s tackle “{task.title}” ({task.priority}{', due ' + due if due else ''}).",
    ]
    if desc:
        steps.append(f"Notes you saved: {desc[:280]}")
    steps.extend(_offline_howto_for_task(task))
    cat = (task.category or "").upper()
    if cat == "LEARNING":
        steps.append("Tip: pair a short explanation with one tiny practice example.")
    elif cat == "FINANCE":
        steps.append("Tip: gather the amount/date/account first, then complete the payment/entry.")
    elif cat == "WORK":
        steps.append("Tip: define the deliverable and any deadline dependency before deep work.")
    steps.append("Want me to go deeper on any step? Say which number.")
    return "\n".join(steps)


def _wants_task_status(message: str) -> bool:
    lower = (message or "").lower()
    cues = (
        "my task",
        "my tasks",
        "tasks for today",
        "task for today",
        "today's task",
        "todays task",
        "due today",
        "what do i have",
        "what should i do",
        "pending task",
        "open task",
        "overdue",
        "did you add",
        "did you added",
        "any task",
        "task list",
        "show task",
        "list task",
        "ente task",
        "task undoo",
        "task undo",
        "innathe task",
        "what tasks",
        "which task",
    )
    return any(c in lower for c in cues)


def _wants_task_help(message: str) -> bool:
    lower = (message or "").lower()
    lower = re.sub(r"\s+", " ", lower)
    cues = (
        "help me with",
        "help with the task",
        "help with my task",
        "how to do",
        "how do i",
        "how can i",
        "how to finish",
        "suggest how",
        "suggestion for",
        "guide me",
        "steps for",
        "help me finish",
        "help me complete",
        "engane cheyyam",
        "engane cheyyanam",
        "help me on",
        "stuck on this task",
        "don't know how",
        "dont know how",
        "need your help",
        "need you help",
        "need help",
        "i need help",
        "can you help",
        "please help",
        "show me how",
        "help me",
        "help pls",
        "help please",
    )
    if any(c in lower for c in cues):
        return True
    if re.search(r"\b(help|helpp|helping)\b", lower) and re.search(
        r"\b(task|this|that|it|jenkins|junkins|setup|setting)\b", lower
    ):
        return True
    return "help" in lower and "task" in lower


def _last_assistant_offered_help(history: list | None) -> bool:
    for turn in reversed(history or []):
        if (turn.get("role") or "").lower() != "assistant":
            continue
        content = (turn.get("content") or "").lower()
        if not content:
            continue
        return bool(
            re.search(
                r"want help|help on how to do|how to do that|want me to help|"
                r"shall i help|can help you (with|on)|walk you through",
                content,
            )
        )
    return False


def _accepts_task_help_offer(message: str, history: list | None) -> bool:
    """Short yes / need-help after Niva offered help on a task."""
    if not _last_assistant_offered_help(history):
        return False
    text = (message or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s']+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return False
    if _wants_task_help(text):
        return True
    affirm = {
        "yes",
        "ys",
        "y",
        "yeah",
        "yep",
        "yup",
        "sure",
        "ok",
        "okay",
        "k",
        "kk",
        "pls",
        "please",
        "help",
        "do it",
        "go ahead",
        "sheri",
        "venam",
        "ashi",
        "aa",
        "haan",
        "ha",
        "of course",
        "please help",
        "yes please",
        "yes help",
        "yes i need help",
        "ys i need you help",
        "yes i need your help",
        "i need help",
        "need help",
    }
    if text in affirm:
        return True
    return bool(
        re.search(
            r"^(yes|ys|yeah|yep|yup|sure|ok|okay)\b.{0,40}\b(help|please|pls|venam)\b",
            text,
        )
    )


def _find_memory_by_tag(user, tag: str) -> AssistantMemory | None:
    tag_l = (tag or "").strip().lower()
    if not tag_l:
        return None
    keyed = (
        _memory_queryset(user)
        .filter(key__iexact=tag_l, status="active")
        .first()
    )
    if keyed:
        return keyed
    for m in _memory_queryset(user)[:80]:
        tags = [str(t).lower() for t in (m.tags or [])]
        if tag_l in tags or (m.key or "").lower() == tag_l:
            return m
    return None


def _canonical_value_from_memory(memory: AssistantMemory | None) -> str:
    if not memory:
        return ""
    # Prefer content only — title phrases like "Preferred name" must not be parsed as the value
    text = (memory.content or "").strip()
    patterns = (
        r"preferred name is\s+([A-Za-z][A-Za-z0-9_\-]{1,40})",
        r"(?:full\s+)?name is\s+([A-Za-z][A-Za-z0-9_\-]{1,40})",
        r"call(?:ed)?\s+me\s+([A-Za-z][A-Za-z0-9_\-]{1,40})",
        r"i am\s+([A-Za-z][A-Za-z0-9_\-]{1,40})",
    )
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            name = m.group(1).strip()
            if name.lower() in {"preferred", "name", "full", "call", "called"}:
                continue
            return name[0].upper() + name[1:] if name else ""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,40}", text)
    skip = {"preferred", "name", "full", "is", "call", "called", "me", "i", "am"}
    tokens = [t for t in tokens if t.lower() not in skip]
    if tokens:
        name = tokens[-1]
        return name[0].upper() + name[1:]
    return ""


def _preferred_display_name(profile: dict[str, str], user=None) -> str:
    pref = _find_memory_by_tag(user, "preferred_name")
    value = _canonical_value_from_memory(pref)
    if value:
        return value
    full = _find_memory_by_tag(user, "full_name")
    value = _canonical_value_from_memory(full)
    if value:
        return value
    return (profile.get("user_name") or "friend").strip() or "friend"


def _who_am_i_reply(profile: dict[str, str], user=None) -> str:
    """Short identity answer — never dump the memory list."""
    account = (profile.get("user_name") or "friend").strip() or "friend"
    pref_mem = _find_memory_by_tag(user, "preferred_name")
    full_mem = _find_memory_by_tag(user, "full_name")
    pref = _canonical_value_from_memory(pref_mem)
    legal = _canonical_value_from_memory(full_mem)

    if pref and legal and pref.lower() != legal.lower():
        return f"You’re {legal} — I call you {pref}."
    if pref:
        return f"You’re {pref}."
    if legal:
        return f"You’re {legal}."
    return f"You’re {account}."


def _fallback_briefing(profile: dict, snap: dict) -> dict[str, Any]:
    overdue = snap["overdue"]
    due_today = snap["due_today"]
    if overdue:
        top = overdue[0]["title"]
        greeting = f"Hey {profile['user_name']} — Niva here. You have {snap['overdue_count']} overdue."
        task_nudge = f"Start with: “{top}”. Clear overdue before new work."
    elif due_today:
        top = due_today[0]["title"]
        greeting = f"Good to see you, {profile['user_name']}. Niva has your day mapped."
        task_nudge = f"Focus next: “{top}” ({snap['due_today_count']} due today)."
    elif snap["open_count"]:
        greeting = f"Hi {profile['user_name']} — Niva’s watching your open list."
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
    text = (text or "").strip()
    if not text:
        return None
    # Strip common markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        raw = match.group(0)
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except Exception:
            # Trailing commas
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
            try:
                obj = json.loads(cleaned)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
    return None


def _gemini_response_text(resp) -> str:
    try:
        text = getattr(resp, "text", None)
        if text:
            return str(text)
    except Exception:
        pass
    try:
        parts = []
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                t = getattr(part, "text", None)
                if t:
                    parts.append(str(t))
        return "\n".join(parts).strip()
    except Exception:
        return ""


def generate_briefing(force_refresh: bool = False, user=None) -> dict[str, Any]:
    profile = get_profile(user)
    today = timezone.localdate()
    if not force_refresh:
        cached = AssistantBrief.objects.filter(user=user, brief_date=today).first()
        if cached and cached.payload:
            return {**cached.payload, "cached": True}

    # Fast path for popup: text knowledge + tasks (embeddings via /reindex)
    try:
        if AssistantChunk.objects.filter(
            user=user, source_type=AssistantSourceType.KNOWLEDGE
        ).count() < 3:
            seed_knowledge(force_embed=False, user=user)
        # Refresh task chunk text without waiting on embeddings
        index_workspace(force_embed=False, user=user)
    except Exception:
        pass

    snap = _live_task_snapshot(user)
    query = (
        "Help me remember pending tasks, overdue work, and responsibilities. "
        "Suggest one method and one short tech/learning tip for a Python AI learner in Kannur."
    )
    chunks = retrieve(query, k=8, user=user)
    context = "\n\n".join(
        f"[{c.source_type}] {c.title}: {c.content}" for c in chunks
    )
    snap_text = json.dumps(snap, default=str)

    news_web = tavily_search(
        "latest technology AI Python India tech news today",
        topic="news",
        max_results=3,
        search_depth="basic",
    )
    news_ctx = _format_web_context(news_web)
    if news_ctx:
        context = f"{news_ctx}\n\n{context}".strip()

    genai = _configure_gemini()
    payload = None
    if genai:
        prompt = f"""{NIVA_SYSTEM_RULES}

Daily briefing mode for {profile['user_name']} ({profile['role']}, {profile['location']}).
Help them REMEMBER tasks and responsibilities — never shame them.

Live task snapshot JSON:
{snap_text}

Retrieved knowledge/context (may include LIVE WEB SEARCH news):
{context[:7000]}

Return ONLY valid JSON with keys:
greeting (short spoken line, warm and calm — not over-excited),
taskNudge (specific next task/responsibility to do now — if due_today or overdue exist, name the real task),
methodTip (one practical method to stop forgetting work),
newsBite (one short real news or tech update from WEB SEARCH if present; else a Python/AI tip),
responsibilityFocus (one line about duties they may overlook),
avatarMood (one of: welcome, encourage, focus, celebrate)

If snapshot has due_today or overdue items, taskNudge MUST mention the most urgent real title.
No markdown. Keep each string under 220 characters."""
        try:
            model = genai.GenerativeModel(CHAT_MODEL)
            resp = model.generate_content(
                prompt, request_options={"timeout": 45}
            )
            text = getattr(resp, "text", None) or ""
            parsed = _parse_json_loose(text)
            if parsed:
                news_bite = parsed.get("newsBite") or ""
                if not news_bite and news_web and news_web.get("answer"):
                    news_bite = news_web["answer"][:220]
                elif not news_bite and news_web and news_web.get("results"):
                    news_bite = (news_web["results"][0].get("title") or "")[:220]
                payload = {
                    "assistantName": ASSISTANT_NAME,
                    "greeting": parsed.get("greeting") or f"Hey {profile['user_name']}!",
                    "taskNudge": parsed.get("taskNudge") or "",
                    "methodTip": parsed.get("methodTip") or "",
                    "newsBite": news_bite,
                    "responsibilityFocus": parsed.get("responsibilityFocus") or "",
                    "avatarMood": parsed.get("avatarMood") or "encourage",
                    "sources": [c.source_id or c.title for c in chunks[:5]],
                    "generatedBy": "gemini+tavily" if news_web else "gemini",
                }
        except Exception:
            payload = None

    if not payload:
        payload = _fallback_briefing(profile, snap)
        if news_web and (news_web.get("answer") or news_web.get("results")):
            payload["newsBite"] = (
                (news_web.get("answer") or "")[:220]
                or (news_web["results"][0].get("title") or "")[:220]
            )
            payload["generatedBy"] = "fallback+tavily"

    payload["profile"] = profile
    payload["stats"] = {
        "openCount": snap["open_count"],
        "overdueCount": snap["overdue_count"],
        "dueTodayCount": snap["due_today_count"],
    }
    payload["cached"] = False

    AssistantBrief.objects.update_or_create(
        user=user, brief_date=today, defaults={"payload": payload}
    )
    return payload


def _parse_due_datetime(iso_or_local: str | None):
    if not iso_or_local:
        return None
    raw = str(iso_or_local).strip()
    try:
        # Accept "2026-11-20T16:30:00" or date-only
        if len(raw) == 10 and raw[4] == "-":
            dt = datetime.strptime(raw, "%Y-%m-%d")
            dt = timezone.make_aware(datetime.combine(dt.date(), dtime(9, 0)))
            return dt
        cleaned = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except Exception:
        return None


def _parse_chunk_due(text: str, now: datetime):
    """Best-effort due date from a single task phrase."""
    lower = text.lower()
    due_day = now.date()
    if any(w in lower for w in ("day after tomorrow", "naale annal", "naaley annal")):
        due_day = now.date() + timedelta(days=2)
    elif any(
        w in lower
        for w in (
            "tomorrow",
            "tomarow",
            "tommorow",
            "naale",
            "naaley",
            "nale",
        )
    ):
        due_day = now.date() + timedelta(days=1)
    elif "today" in lower or "innu" in lower:
        due_day = now.date()

    m = re.search(r"(\d{1,2})[:.](\d{2})\s*(am|pm)?", lower)
    hour, minute = 9, 0
    has_time = bool(m)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        elif not ampm and hour <= 7:
            hour += 12

    # Only set due if tomorrow/today/time was mentioned, or keep None for plain chores
    if not has_time and due_day == now.date() and not any(
        w in lower for w in ("today", "innu", "tomorrow", "tomarow", "tommorow", "naale", "naaley", "nale")
    ):

        return None
    return timezone.make_aware(datetime.combine(due_day, dtime(hour, minute)))


def _clean_task_title(chunk: str) -> str:
    title = _strip_task_create_phrasing(chunk) if chunk else ""
    if not title:
        title = chunk or ""
    title = re.sub(
        r"\b("
        r"i have a|i have|i need to|need to|have to|remind me|remember|"
        r"please|also|then|and then|ok|okay|"
        r"tomorrow|tomarow|tommorow|today|day after tomorrow|"
        r"naale|naaley|nale|innu|innale|"
        r"at\s+\d{1,2}[:.]\d{2}\s*(am|pm)?|"
        r"\d{1,2}[:.]\d{2}\s*(am|pm)?"
        r")\b",
        "",
        title,
        flags=re.I,
    )
    title = re.sub(r"\s+", " ", title).strip(" .,!;-:")
    return title[:255] if title else (chunk or "").strip()[:255]


def _heuristic_capture(message: str) -> dict[str, Any]:
    """Offline fallback: split multi-task messages when Gemini is unavailable."""
    now = timezone.localtime()
    # Split on newlines, semicolons, " and ", " also ", numbered lists, manglish connectors
    raw_parts = re.split(
        r"(?:\n+|;|\u2022|\d+[.)]\s+|\band then\b|\balso\b|\bpinne\b|\bathava\b|\bappo\b)",
        message,
        flags=re.I,
    )
    # Further split on commas only when they look like list separators (short items)
    parts: list[str] = []
    for part in raw_parts:
        part = part.strip(" .,!")
        if not part:
            continue
        if "," in part and len(part) < 120:
            sub = [p.strip(" .,!") for p in part.split(",") if p.strip(" .,!")]
            # Only treat as list if 2+ meaningful chunks
            if len(sub) >= 2 and all(len(s) >= 3 for s in sub):
                parts.extend(sub)
                continue
        parts.append(part)

    # Collapse "X and Y" style when both sides look like tasks
    expanded: list[str] = []
    for part in parts:
        and_bits = re.split(r"\s+\band\b\s+", part, flags=re.I)
        if (
            len(and_bits) >= 2
            and all(len(b.strip()) >= 4 for b in and_bits)
            and not re.search(r"\b(milk and sugar|bread and butter)\b", part, re.I)
        ):
            # Prefer splitting when each side has a verb-ish cue or shopping/chore word
            chore = any(
                w in part.lower()
                for w in (
                    "buy",
                    "call",
                    "pay",
                    "check",
                    "meet",
                    "send",
                    "finish",
                    "complete",
                    "vaangi",
                    "vilikk",
                    "cheyy",
                    "nokki",
                )
            )
            if chore or len(and_bits) == 2:
                expanded.extend(b.strip(" .,!") for b in and_bits if b.strip())
                continue
        expanded.append(part)

    if not expanded:
        expanded = [message.strip()]

    tasks = []
    for chunk in expanded:
        lower = chunk.lower()
        title = _clean_task_title(chunk) or "New reminder"
        if "meeting" in lower and "meeting" not in title.lower():
            title = f"Meeting — {title}" if title.lower() != "meeting" else "Meeting"
        due = _parse_chunk_due(chunk, now)
        category = (
            "WORK"
            if any(w in lower for w in ("meeting", "call", "client", "office", "interview"))
            else "FINANCE"
            if any(w in lower for w in ("emi", "bill", "pay", "recharge", "bank"))
            else "LEARNING"
            if any(w in lower for w in ("study", "learn", "course", "django", "python"))
            else "PERSONAL"
        )
        priority = (
            "HIGH"
            if any(w in lower for w in ("meeting", "urgent", "important", "asap"))
            else "MEDIUM"
        )
        tasks.append(
            {
                "title": title[:255],
                "description": f"Captured by Niva from: {chunk.strip()}",
                "category": category,
                "priority": priority,
                "dueDate": due.isoformat() if due else None,
            }
        )

    n = len(tasks)
    reply = (
        f"Got it — I saved {n} tasks so you won’t forget."
        if n > 1
        else "Got it — I saved this so you won’t forget."
    )
    return {"action": "create_tasks", "tasks": tasks, "reply": reply}


def _normalize_capture_payload(parsed: dict[str, Any], message: str) -> list[dict[str, Any]]:
    """Accept single-task or multi-task Gemini JSON and return a task dict list."""
    if not parsed:
        return []
    if isinstance(parsed.get("tasks"), list) and parsed["tasks"]:
        out = []
        for item in parsed["tasks"]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            out.append(item)
        return out
    # Legacy single-task shape
    if parsed.get("title"):
        return [parsed]
    return []


def capture_message(message: str, user=None) -> dict[str, Any]:
    """Parse natural language (English/Manglish) into one or more Dayflow tasks."""
    message = (message or "").strip()
    if not message:
        return {"success": False, "error": "Message is required"}

    profile = get_profile(user)
    now = timezone.localtime()
    parsed = None
    genai = _configure_gemini()
    if genai:
        prompt = f"""You are {ASSISTANT_NAME}, a memory assistant for Dayflow.
User lives in {profile['location']} (timezone Asia/Kolkata).
Current local datetime: {now.isoformat()}

User said: {message!r}

The user may write in English OR Manglish (Malayalam typed in English letters), e.g.
"naale 4.30 meeting und", "innu milk vaanganam", "EMI check cheyyanam".
Understand Manglish meaning and write task titles in clear short English (or keep simple Manglish nouns if clearer).

If the message contains MULTIPLE tasks (lists, commas, "and", "also", "pinne", numbered items),
split them into SEPARATE tasks. Do not merge unrelated items into one task.

Return ONLY valid JSON:
{{
  "action": "create_tasks",
  "tasks": [
    {{
      "title": "short clear task title",
      "description": "optional detail",
      "category": "WORK|PERSONAL|FINANCE|LEARNING",
      "priority": "HIGH|MEDIUM|LOW",
      "dueDate": "ISO datetime Asia/Kolkata naive like 2026-11-20T16:30:00 or null"
    }}
  ],
  "reply": "short confirmation spoken as Niva mentioning how many tasks were saved"
}}

Rules:
- One JSON object only, no markdown.
- Each distinct chore/meeting/reminder = its own entry in tasks[].
- If only one task, tasks array still has length 1.
- tomorrow / naale + time like 4.30 / 4:30 → dueDate tomorrow at that time (4:30 alone means 16:30).
- today / innu → today's date.
- If no date/time, dueDate can be null.
"""
        try:
            model = genai.GenerativeModel(CHAT_MODEL)
            resp = model.generate_content(prompt, request_options={"timeout": 45})
            text = getattr(resp, "text", None) or ""
            parsed = _parse_json_loose(text)
        except Exception:
            parsed = None

    task_specs = _normalize_capture_payload(parsed or {}, message)
    reply = (parsed or {}).get("reply") if isinstance(parsed, dict) else None
    if not task_specs:
        fallback = _heuristic_capture(message)
        task_specs = fallback.get("tasks") or []
        reply = reply or fallback.get("reply")

    if not task_specs:
        return {"success": False, "error": "Could not understand any tasks"}

    created = _create_tasks_from_specs(task_specs, user=user, source_message=message)
    if not created:
        return {"success": False, "error": "Could not create tasks"}

    from .serializers import TaskSerializer

    titles = [t.title for t in created]
    if not reply:
        if len(created) == 1:
            reply = f"Saved “{titles[0]}” — I’ll help you remember it."
        else:
            reply = f"Saved {len(created)} tasks: " + "; ".join(titles)

    return {
        "success": True,
        "reply": reply,
        "task": TaskSerializer(created[0]).data,  # backward compatible
        "tasks": TaskSerializer(created, many=True).data,
        "count": len(created),
        "assistant": ASSISTANT_NAME,
    }


def _create_tasks_from_specs(
    task_specs: list[dict[str, Any]],
    user=None,
    source_message: str = "",
) -> list:
    created = []
    for item in task_specs[:12]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "New reminder").strip()[:255]
        if not title:
            continue
        description = (
            item.get("description")
            or (f"Captured by Niva: {source_message}" if source_message else "Captured by Niva")
        ).strip()
        category = item.get("category") or "PERSONAL"
        if category not in ("WORK", "PERSONAL", "FINANCE", "LEARNING"):
            category = "PERSONAL"
        priority = item.get("priority") or "MEDIUM"
        if priority not in ("HIGH", "MEDIUM", "LOW"):
            priority = "MEDIUM"
        due = _parse_due_datetime(item.get("dueDate") or item.get("due_date"))

        task = Task.objects.create(
            user=user,
            title=title,
            description=description,
            category=category,
            priority=priority,
            status=TaskStatus.TODO,
            due_date=due,
            is_important=priority == "HIGH",
            tags=["niva"],
        )
        created.append(task)

        try:
            text = (
                f"Pending task: {task.title}. Category {task.category}. Priority {task.priority}. "
                f"Due {task.due_date.isoformat() if task.due_date else 'no due date'}. {task.description}"
            )
            _upsert_chunk(
                AssistantSourceType.TASK,
                str(task.id),
                task.title,
                text,
                [],
                {"priority": task.priority, "from": "niva"},
                user=user,
            )
        except Exception:
            pass

    if created:
        try:
            AssistantBrief.objects.filter(
                user=user, brief_date=timezone.localdate()
            ).delete()
        except Exception:
            pass
    return created


def _memory_queryset(user=None):
    return AssistantMemory.objects.filter(user=user, is_active=True)


def list_memories(user=None, limit: int = 50) -> list[dict[str, Any]]:
    rows = list(_memory_queryset(user)[: max(1, min(limit, 100))])
    return [
        {
            "id": m.id,
            "title": m.title,
            "content": m.content,
            "tags": m.tags if isinstance(m.tags, list) else [],
            "updatedAt": m.updated_at.isoformat() if m.updated_at else None,
            "createdAt": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]


def _index_memory_chunk(memory: AssistantMemory, user=None) -> None:
    text = f"Personal memory: {memory.title}. {memory.content}"
    emb: list[float] = []
    try:
        emb = embed_texts([text])[0]
    except Exception:
        emb = []
    _upsert_chunk(
        source_type=AssistantSourceType.MEMORY,
        source_id=f"mem-{memory.id}",
        title=memory.title,
        content=text,
        embedding=emb,
        metadata={"kind": "memory", "memory_id": memory.id, "tags": memory.tags},
        user=user,
    )


def _memory_fingerprint(title: str, content: str) -> str:
    blob = f"{title} {content}".lower()
    blob = re.sub(r"[^a-z0-9]+", " ", blob)
    return re.sub(r"\s+", " ", blob).strip()


def save_memories_from_specs(
    specs: list[dict[str, Any]],
    user=None,
    source_message: str = "",
) -> list[AssistantMemory]:
    created: list[AssistantMemory] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        title = (spec.get("title") or "").strip()[:255]
        content = (spec.get("content") or spec.get("text") or "").strip()
        if not title and content:
            title = content.split(".")[0].strip()[:80] or "Memory"
        if not content and title:
            content = title
        if not title or not content:
            continue
        tags = spec.get("tags") if isinstance(spec.get("tags"), list) else []
        tags = [str(t).strip()[:40] for t in tags if str(t).strip()][:8]
        key = (spec.get("key") or "").strip().lower()
        if key and key not in [t.lower() for t in tags]:
            tags.append(key[:40])

        existing = None
        # Canonical key/tag upsert (preferred_name, full_name, works_at, …)
        for tag in ("preferred_name", "full_name", "works_at", "lives_in", key):
            if not tag:
                continue
            if tag in [t.lower() for t in tags] or tag == key:
                existing = _find_memory_by_tag(user, tag)
                if existing:
                    break
        if not existing:
            existing = (
                _memory_queryset(user)
                .filter(title__iexact=title)
                .first()
            )
        if not existing:
            # Near-duplicate content (same fingerprint)
            fp = _memory_fingerprint(title, content)
            for m in _memory_queryset(user)[:60]:
                if _memory_fingerprint(m.title, m.content) == fp:
                    existing = m
                    break
                # Soft overlap for long messy duplicates of the same nickname fact
                if fp and fp in _memory_fingerprint(m.title, m.content):
                    if "preferred_name" in [t.lower() for t in tags] or "name" in fp:
                        existing = m
                        break

        mem_key = (spec.get("key") or "").strip()[:150]
        if not mem_key:
            for cand in ("preferred_name", "full_name", "works_at", "lives_in"):
                if cand in [t.lower() for t in tags]:
                    mem_key = cand
                    break
        category = "profile" if mem_key in ("preferred_name", "full_name") else (
            "goal" if "goal" in [t.lower() for t in tags] else "general"
        )

        if existing:
            existing.title = title[:255]
            existing.content = content[:4000]
            existing.tags = tags
            existing.source_message = (source_message or "")[:2000]
            existing.key = mem_key or existing.key
            existing.category = category
            existing.status = "active"
            existing.is_active = True
            existing.save(
                update_fields=[
                    "title",
                    "content",
                    "tags",
                    "source_message",
                    "key",
                    "category",
                    "status",
                    "is_active",
                    "updated_at",
                ]
            )
            mem = existing
            # Deactivate other near-duplicates for the same canonical tag
            canon = next(
                (
                    t
                    for t in ("preferred_name", "full_name", "works_at", "lives_in")
                    if t in [x.lower() for x in tags]
                ),
                None,
            )
            if canon:
                for other in _memory_queryset(user)[:80]:
                    if other.id == mem.id:
                        continue
                    otags = [str(t).lower() for t in (other.tags or [])]
                    if canon in otags or other.key == canon or (
                        canon == "preferred_name"
                        and re.search(r"call me|preferred name|arjuoo|arjoo", f"{other.title} {other.content}", re.I)
                    ):
                        other.is_active = False
                        other.status = "superseded"
                        other.save(update_fields=["is_active", "status", "updated_at"])
        else:
            mem = AssistantMemory.objects.create(
                user=user,
                title=title,
                content=content[:4000],
                tags=tags,
                key=mem_key,
                category=category,
                source_message=(source_message or "")[:2000],
                status="active",
                is_active=True,
                explicit=True,
            )
        try:
            _index_memory_chunk(mem, user=user)
        except Exception:
            pass
        created.append(mem)
    return created


def forget_memories(query: str, user=None) -> list[AssistantMemory]:
    q = (query or "").strip()
    if not q:
        return []
    qs = list(_memory_queryset(user)[:80])
    lower = q.lower()
    hits = []
    for m in qs:
        blob = f"{m.title} {m.content}".lower()
        if lower in blob or any(
            tok and tok in blob for tok in re.split(r"\W+", lower) if len(tok) > 3
        ):
            hits.append(m)
    if not hits and qs:
        # fallback: ask embedding similarity via retrieve
        try:
            chunks = retrieve(q, k=3, user=user)
            ids = []
            for c in chunks:
                if c.source_type == AssistantSourceType.MEMORY:
                    mid = (c.metadata or {}).get("memory_id")
                    if mid:
                        ids.append(int(mid))
            hits = [m for m in qs if m.id in ids]
        except Exception:
            hits = []

    forgotten: list[AssistantMemory] = []
    for m in hits[:5]:
        m.is_active = False
        m.save(update_fields=["is_active", "updated_at"])
        AssistantChunk.objects.filter(
            user=user,
            source_type=AssistantSourceType.MEMORY,
            source_id=f"mem-{m.id}",
        ).delete()
        forgotten.append(m)
    return forgotten


_MEMORY_TOPIC_HINTS = {
    "work": (
        "work",
        "working",
        "job",
        "office",
        "company",
        "employer",
        "career",
        "pani",
        "office",
        "workplace",
        "colleague",
        "manager",
        "client",
    ),
    "home": ("home", "live", "living", "house", "city", "place", "address", "veedu"),
    "family": ("family", "wife", "husband", "mom", "dad", "parent", "brother", "sister"),
    "learning": ("learn", "course", "ml", "ai", "python", "study"),
    "health": ("health", "gym", "sleep", "medicine", "doctor"),
    "money": ("salary", "emi", "rent", "budget", "money", "kaasu"),
}


def _score_memory(query: str, memory: AssistantMemory) -> float:
    q = (query or "").lower()
    blob = f"{memory.title} {memory.content} {' '.join(memory.tags or [])}".lower()
    score = 0.0
    if not q:
        return 0.0
    if q in blob:
        score += 4.0
    tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    stop = {
        "the",
        "and",
        "for",
        "you",
        "niva",
        "what",
        "where",
        "when",
        "who",
        "how",
        "are",
        "is",
        "am",
        "my",
        "me",
        "i",
        "do",
        "did",
        "can",
        "about",
        "tell",
        "please",
    }
    for tok in tokens:
        if tok in stop:
            continue
        if tok in blob:
            score += 1.2
    # Topic boosts (e.g. "where am i working" → work memories)
    for topic, hints in _MEMORY_TOPIC_HINTS.items():
        if any(h in q for h in hints):
            if any(h in blob for h in hints) or topic in blob:
                score += 2.5
            tags = [str(t).lower() for t in (memory.tags or [])]
            if topic in tags or "work" in tags and topic == "work":
                score += 1.5
    return score


def find_relevant_memories(
    query: str, user=None, limit: int = 8, min_score: float = 1.0
) -> list[AssistantMemory]:
    rows = list(_memory_queryset(user)[:80])
    if not rows:
        return []
    scored = [(_score_memory(query, m), m) for m in rows]
    scored.sort(key=lambda x: (x[0], x[1].updated_at or timezone.now()), reverse=True)
    hits = [m for s, m in scored if s >= min_score]
    if hits:
        return hits[:limit]
    # Embedding / RAG fallback via MEMORY chunks
    try:
        chunks = retrieve(query, k=5, user=user)
        ids: list[int] = []
        for c in chunks:
            if c.source_type != AssistantSourceType.MEMORY:
                continue
            mid = (c.metadata or {}).get("memory_id")
            if mid:
                try:
                    ids.append(int(mid))
                except Exception:
                    pass
        by_id = {m.id: m for m in rows}
        return [by_id[i] for i in ids if i in by_id][:limit]
    except Exception:
        return []


def memories_context(user=None, query: str = "", limit: int = 12) -> str:
    """Only include memories relevant to the query — never pad with unrelated facts."""
    rows = list(_memory_queryset(user)[:40])
    if not rows:
        return ""
    scored = [(_score_memory(query, m), m) for m in rows]
    scored.sort(key=lambda x: (x[0], x[1].updated_at or timezone.now()), reverse=True)
    # Strict relevance: do not dump the whole memory bank into every prompt
    min_score = 1.0 if (query or "").strip() else 0.0
    picked = [m for s, m in scored if s >= min_score][: max(1, min(limit, 6))]
    if not picked and not (query or "").strip():
        picked = [m for _, m in scored[: min(3, limit)]]
    if not picked:
        return ""
    lines = [f"- {m.title}: {m.content[:220]}" for m in picked]
    return "Relevant personal memories:\n" + "\n".join(lines)


def _normalize_typos(text: str) -> str:
    t = (text or "").strip()
    replacements = (
        (r"\biam\b", "I am"),
        (r"\bi\s*am\b", "I am"),
        (r"\bworkingin\b", "working in"),
        (r"\bworking\s*in\b", "working in"),
        (r"\btyhe\b", "the"),
        (r"\bteh\b", "the"),
        (r"\bnexcrestit\b", "Nexcrest"),
        (r"\bnexcrest\b", "Nexcrest"),
        (r"\bcalicut\b", "Calicut"),
        (r"\bkannur\b", "Kannur"),
        (r"\bkochi\b", "Kochi"),
        (r"\bhy\b", ""),
        (r"\bhe\s+niva\b", ""),
        (r"\bhey\s+niva\b", ""),
        (r"\bhi\s+niva\b", ""),
    )
    for pat, rep in replacements:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,.-")
    return t


def _strip_trailing_junk(text: str) -> str:
    t = (text or "").strip(" ,.-")
    # Drop trailing single-letter leftovers like "... calicut o"
    t = re.sub(r"\s+[a-z]$", "", t, flags=re.I).strip(" ,.-")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_work_fact(text: str) -> tuple[str | None, str | None]:
    """Return (company/place, city) from messy work memory text."""
    t = _normalize_typos(text)
    t = re.sub(
        r"\b(remember\s+(this|that|it)?|keep\s+in\s+mind|don'?t\s+forget|ormikkane)\b",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s+", " ", t).strip(" ,.-")
    t = _strip_trailing_junk(t)
    # working in/at/for [the] COMPANY at CITY
    m = re.search(
        r"work(?:ing)?\s+(?:in|at|for)\s+(?:the\s+)?(.+?)\s+at\s+([A-Za-z][A-Za-z\s]{1,40})$",
        t,
        flags=re.I,
    )
    if m:
        company = _strip_trailing_junk(m.group(1))
        city = _strip_trailing_junk(m.group(2))
        # If company still contains "at City", split again
        m2 = re.search(r"^(.+?)\s+at\s+([A-Za-z].+)$", company, flags=re.I)
        if m2 and not city:
            return _strip_trailing_junk(m2.group(1)), _strip_trailing_junk(m2.group(2))
        return company, city
    m = re.search(
        r"work(?:ing)?\s+(?:in|at|for)\s+(?:the\s+)?(.+)$",
        t,
        flags=re.I,
    )
    if m:
        rest = _strip_trailing_junk(m.group(1))
        m2 = re.search(r"^(.+?)\s+at\s+([A-Za-z].+)$", rest, flags=re.I)
        if m2:
            return _strip_trailing_junk(m2.group(1)), _strip_trailing_junk(m2.group(2))
        return rest, None
    m = re.search(
        r"(?:company|office|workplace)\s+is\s+(.+)$",
        t,
        flags=re.I,
    )
    if m:
        return _strip_trailing_junk(m.group(1)), None
    return None, None


def _natural_memory_answer(question: str, memory: AssistantMemory) -> str:
    """Turn a stored memory into a short answer for the user's question."""
    q = (question or "").lower()
    raw = f"{memory.title} {memory.content}".strip()
    clean_title, clean_content = _clean_memory_fact(raw)
    # Prefer structured work answer
    if any(k in q for k in ("work", "working", "company", "office", "job", "pani")):
        company, city = _parse_work_fact(clean_content)
        if not company:
            company, city = _parse_work_fact(raw)
        if company and city:
            return f"You work at {company} in {city}."
        if company:
            return f"You work at {company}."
    if any(k in q for k in ("live", "living", "home", "city")):
        m = re.search(r"liv(?:e|ing)\s+in\s+(.+)$", _normalize_typos(clean_content), re.I)
        if m:
            return f"You live in {m.group(1).strip(' .,!')}."
    # Generic short fact answer — never dump raw chat fluff
    fact = clean_content or clean_title or memory.content
    fact = _normalize_typos(fact)
    fact = re.sub(
        r"\b(remember\s+(this|that|it)?|keep\s+in\s+mind|niva)\b",
        " ",
        fact,
        flags=re.I,
    )
    fact = re.sub(r"\s+", " ", fact).strip(" ,.-")
    if not fact:
        fact = memory.title
    # Make it a sentence
    if not fact.endswith((".", "!", "?")):
        fact = fact[0].upper() + fact[1:] if fact else fact
    return fact


def _maybe_cleanup_memory(memory: AssistantMemory) -> None:
    """Quietly rewrite messy stored memories into a clean fact."""
    raw = (memory.content or "").strip()
    if not raw:
        return
    looks_messy = bool(
        re.search(
            r"niva|remember that|workingin|tyhe|iam |nexcrestit|\bhy\b|\s+[a-z]\.?$",
            raw,
            flags=re.I,
        )
    ) or len(raw) > 120
    company, city = _parse_work_fact(raw)
    if not looks_messy and not company:
        return
    title, content = _clean_memory_fact(raw)
    if not company:
        company, city = _parse_work_fact(content)
    if company and city:
        title = f"Works at {company}, {city}"
        content = f"I work at {company} in {city}."
    elif company:
        title = f"Works at {company}"
        content = f"I work at {company}."
    else:
        content = _strip_trailing_junk(content)
        title = _strip_trailing_junk(title)[:255]
    if content == raw and title == (memory.title or ""):
        return
    memory.title = title[:255]
    memory.content = content[:4000]
    try:
        memory.save(update_fields=["title", "content", "updated_at"])
        _index_memory_chunk(memory, user=memory.user)
    except Exception:
        pass


def _answer_from_memories(message: str, user=None, profile: dict[str, str] | None = None) -> str | None:
    """Answer personal questions from stored memories — short natural answer only."""
    hits = find_relevant_memories(message, user=user, limit=3, min_score=1.5)
    if not hits:
        return None
    # Clean + answer from the best match
    best = hits[0]
    _maybe_cleanup_memory(best)
    best.refresh_from_db()
    return _natural_memory_answer(message, best)


def _fact_from_history(message: str, history: list[dict[str, str]] | None) -> str | None:
    """If user already stated a fact in recent chat, reuse it (and caller may persist)."""
    if not history:
        return None
    lower_q = (message or "").lower()
    patterns: list[tuple[tuple[str, ...], re.Pattern[str]]] = []
    if any(k in lower_q for k in ("work", "working", "company", "office", "job", "pani")):
        patterns.append(
            (
                ("work",),
                re.compile(
                    r"(?:i\s+(?:am\s+)?work(?:ing)?\s+(?:at|in|for)|my\s+(?:company|office|workplace|job)\s+is)\s+(.+)$",
                    re.I,
                ),
            )
        )
    if any(k in lower_q for k in ("live", "living", "home", "city", "where am i")):
        patterns.append(
            (
                ("home",),
                re.compile(
                    r"(?:i\s+(?:am\s+)?liv(?:e|ing)\s+in|my\s+(?:home|city)\s+is)\s+(.+)$",
                    re.I,
                ),
            )
        )
    if not patterns:
        return None
    for turn in reversed(history[-12:]):
        if (turn.get("role") or "").lower() != "user":
            continue
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        for _tags, pat in patterns:
            m = pat.search(content)
            if m:
                return m.group(0).strip()
    return None


def _wants_memory_store(message: str) -> bool:
    """Only explicit remember / keep-in-mind commands — never casual chat."""
    lower = (message or "").lower()
    cues = (
        "remember this",
        "remember that",
        "remember:",
        "please remember",
        "don't forget",
        "dont forget",
        "do not forget",
        "keep this in mind",
        "keep in mind",
        "keep that in mind",
        "save this in memory",
        "save in your memory",
        "add to memory",
        "put in memory",
        "add to your memory",
        "ormayil vechu",
        "ormayil vekku",
        "ormikkane",
        "ormippikkane",
        "ormikkuka",
        "always remember",
    )
    return any(c in lower for c in cues)


def _parse_name_memory_specs(text: str) -> list[dict[str, Any]]:
    """Extract canonical profile name facts (not raw chat transcripts)."""
    t = _normalize_typos(text or "")
    t = re.sub(
        r"\b(please\s+)?(remember\s+(this|that|it)?|keep\s+(this|that)?\s*in\s+mind|"
        r"don'?t\s+forget|ok|okay)\b[:\-.,!]?\s*",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s+", " ", t).strip(" ,.-")
    specs: list[dict[str, Any]] = []

    def _nice(name: str) -> str:
        name = (name or "").strip(" .,!_")
        if not name:
            return ""
        return name[0].upper() + name[1:]

    pref = ""
    m = re.search(
        r"(?:you\s+can\s+)?call\s+me\s+([A-Za-z][A-Za-z0-9_\-]{1,40})",
        t,
        flags=re.I,
    )
    if m:
        pref = _nice(m.group(1))
        if pref:
            specs.append(
                {
                    "title": "Preferred name",
                    "content": f"Preferred name is {pref}.",
                    "tags": ["profile", "preferred_name"],
                    "key": "preferred_name",
                }
            )

    skip = {
        "a",
        "the",
        "learning",
        "working",
        "from",
        "in",
        "at",
        "going",
        "trying",
        "feeling",
        "here",
        "just",
        "also",
        "still",
    }
    m = re.search(r"\b(?:i am|i'm|iam)\s+([A-Za-z][A-Za-z0-9_\-]{1,40})\b", t, flags=re.I)
    if m:
        raw = m.group(1)
        legal = _nice(raw) if raw.lower() not in skip else ""
        if legal and legal.lower() != (pref or "").lower():
            specs.append(
                {
                    "title": "Full name",
                    "content": f"Name is {legal}.",
                    "tags": ["profile", "full_name"],
                    "key": "full_name",
                }
            )
    return specs


def _clean_memory_fact(message: str) -> tuple[str, str]:
    """Strip chat fluff / remember commands → (title, content)."""
    text = _normalize_typos(message or "")
    text = re.sub(
        r"^(hey|hi|hello|hii|helo|he)?\s*niva[,!]?\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(
        r"\b(please\s+)?(remember\s+(this|that|it)?|keep\s+(this|that)\s+in\s+mind|"
        r"keep\s+in\s+mind|don'?t\s+forget|do\s+not\s+forget|ormikkane|ormippikkane|ormikkuka|"
        r"ormayil\s+vekk?[u]?|save\s+this\s+in\s+(your\s+)?memory|"
        r"add\s+to\s+(your\s+)?memory|ok|okay)\b[:\-.,!]?\s*",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    if not text:
        text = (message or "").strip()[:200] or "Memory"

    name_specs = _parse_name_memory_specs(message)
    if name_specs:
        # Prefer preferred_name for the primary cleaned fact
        primary = next(
            (s for s in name_specs if s.get("key") == "preferred_name"),
            name_specs[0],
        )
        return primary["title"][:80], primary["content"][:1000]

    company, city = _parse_work_fact(text)
    if company and city:
        return f"Works at {company}, {city}"[:80], f"I work at {company} in {city}."
    if company:
        return f"Works at {company}"[:80], f"I work at {company}."

    m = re.search(r"(?:I\s+am\s+)?liv(?:e|ing)\s+in\s+(.+)$", text, flags=re.I)
    if m:
        place = m.group(1).strip(" .,!")
        return f"Lives in {place}"[:80], f"I live in {place}."
    title = text[:80]
    return title, text[:1000]


def _wants_memory_forget(message: str) -> bool:
    lower = (message or "").lower()
    cues = (
        "forget that",
        "forget this",
        "forget about",
        "delete memory",
        "remove from memory",
        "don't remember that",
        "dont remember that",
        "ormayil ninnu kalayuka",
        "forget my",
    )
    return any(c in lower for c in cues)


def _wants_memory_recall(message: str) -> bool:
    lower = (message or "").lower()
    cues = (
        "do you remember",
        "did you remember",
        "what did i tell",
        "what do you remember",
        "what's in your memory",
        "whats in your memory",
        "what do you know about me",
        "my preference",
        "what is my",
        "what's my",
        "whats my",
        "ormayundo",
        "orma undo",
        "ninte ormayil",
        "tell me what you remember",
        "show my memories",
        "list my memories",
        "where am i working",
        "where do i work",
        "where i work",
        "where i am working",
        "where am i living",
        "where do i live",
        "what company",
        "which company",
        "my office",
        "my workplace",
        "my job",
        "who is my",
        "evanide",
        "evideyaanu",
        "enthaanu ente",
    )
    return any(c in lower for c in cues)


def _looks_like_personal_fact_question(message: str) -> bool:
    """Questions that should check private memory first."""
    lower = (message or "").lower().strip()
    if "?" in message or lower.startswith(
        ("where", "what", "who", "which", "when", "do you", "did you", "can you tell")
    ):
        personal = (
            " i ",
            " my ",
            " me",
            "am i",
            "do i",
            "i work",
            "i live",
            "working",
            "company",
            "office",
            "family",
            "preference",
            "ente ",
            "enikku ",
            "njan ",
        )
        # also messages like "niva where am i working"
        padded = f" {lower} "
        return any(p in padded for p in personal) or any(
            p in lower for p in ("where am i", "what is my", "what's my", "who am i")
        )
    return False


def _extract_memories_with_gemini(
    message: str,
    history_text: str,
    profile: dict[str, str],
) -> list[dict[str, Any]]:
    # Deterministic profile facts first (names) — never store raw "keep in mind" chat
    name_specs = _parse_name_memory_specs(message)
    if name_specs:
        return name_specs

    cleaned_title, cleaned_content = _clean_memory_fact(message)
    genai = _configure_gemini()
    if not genai:
        tags = ["work"] if re.search(r"work|office|company|job", cleaned_content, re.I) else ["general"]
        if re.search(r"work|office|company|job", cleaned_content, re.I):
            tags = ["work", "works_at"]
        return [{"title": cleaned_title, "content": cleaned_content, "tags": tags}]

    prompt = f"""You are {ASSISTANT_NAME}. The user EXPLICITLY asked you to remember something.
Extract ONLY clean durable FACTS as structured memories. Never store the raw chat transcript.
Remove greetings and remember/keep-in-mind words. Fix light typos.
If they give a nickname ("call me X"), use title "Preferred name", tags ["profile","preferred_name"], key "preferred_name".
If they give a legal name ("I am Arjun"), use title "Full name", tags ["profile","full_name"], key "full_name".
If workplace, tags ["work","works_at"]. Do NOT invent details. Do NOT create tasks.

User: {profile.get('user_name')}
Conversation:
{history_text}
Latest message: {message!r}
Pre-cleaned hint: {cleaned_content!r}

Return ONLY JSON:
{{
  "memories": [
    {{"title": "short label", "content": "one clean fact sentence", "tags": ["profile|work|home|learning|preference"], "key": "preferred_name|full_name|works_at|lives_in|other"}}
  ]
}}
If nothing durable, memories=[].
"""
    try:
        model = genai.GenerativeModel(
            CHAT_MODEL,
            generation_config={
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        )
        resp = model.generate_content(prompt, request_options={"timeout": 45})
        text = _gemini_response_text(resp)
        parsed = _parse_json_loose(text) or {}
        specs = parsed.get("memories") if isinstance(parsed, dict) else None
        if not isinstance(specs, list):
            specs = []
        out = []
        for s in specs:
            if isinstance(s, dict) and (s.get("content") or s.get("title")):
                # Reject transcript-like dumps
                content = (s.get("content") or "").strip()
                if re.search(r"keep in mind|remember this", content, re.I):
                    continue
                if len(content) > 220:
                    content = content[:220].rstrip() + "."
                    s = {**s, "content": content}
                out.append(s)
        if out:
            return out
    except Exception:
        pass
    tags = ["work", "works_at"] if re.search(r"work|office|company|job", cleaned_content, re.I) else ["general"]
    return [{"title": cleaned_title, "content": cleaned_content, "tags": tags}]


def _wants_task_creation(message: str) -> bool:
    """Detect create-task intent, including typo/filler variants like 'add it as task'."""
    lower = (message or "").lower()
    lower = re.sub(r"\bnewtask\b", "new task", lower)
    lower = re.sub(r"\s+", " ", lower)
    # Flexible patterns: allow words between verb and "task" (it/this/a/new/as/to…)
    patterns = (
        r"\b(?:please\s+)?(?:can you\s+|could you\s+)?(?:add|create|make|save|mark)\b.{0,48}\btasks?\b",
        r"\bnew\s+tasks?\b",
        r"\btasks?\s*(?:aayi|aaki|aakkan|aakk)\b",
        r"\btasks?\s+add\b",
        r"\btaskil\s*add\b",
        r"\btodo\s+add\b",
        r"\b(?:remeber|remember)\s+this\b",
        r"\bremind\s+me\b",
        r"\bmake\s+it\s+a\s+tasks?\b",
    )
    if any(re.search(p, lower) for p in patterns):
        return True
    # Exact legacy short cues (kept for safety)
    cues = (
        "mark as task",
        "add as task",
        "add to task",
        "create task",
        "make it a task",
        "make a task",
        "save as task",
        "task aayi",
        "task aaki",
        "task aakkan",
        "task aakk",
        "task add",
        "add task",
        "remeber this",
        "remember this",
        "remind me",
        "taskil add",
        "todo add",
    )
    return any(c in lower for c in cues)


def _strip_task_create_phrasing(message: str) -> str:
    """Remove 'add/create … task' scaffolding so the remaining text is the task."""
    text = re.sub(r"\bnewtask\b", "new task", message or "", flags=re.I)
    text = re.sub(
        r"\b(?:please\s+)?(?:can you\s+|could you\s+)?"
        r"(?:add|create|make|save|mark)\s+"
        r"(?:it|this|that|a|the|my|new)?\s*"
        r"(?:new\s+)?(?:as\s+(?:a\s+)?|to\s+(?:my\s+)?|to\s+)?"
        r"(?:a\s+)?tasks?\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bnew\s+tasks?\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:ok|okay|please)\b", " ", text, flags=re.I)
    text = re.sub(r"\bneed\s+to\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .,!;-:")
    text = re.sub(r"^(?:to|for|about|:)\s+", "", text, flags=re.I).strip(" .,!;-:")
    return text


def _is_task_create_confirmation(message: str) -> bool:
    """True when the user is confirming create with little/no task body."""
    if not _wants_task_creation(message):
        return False
    leftover = _strip_task_create_phrasing(message)
    return len(leftover) < 10


def _resolve_create_source(message: str, history: list | None) -> str:
    """
    Choose the best text to turn into a task.
    Short confirmations like 'add it as task' pull the prior user description.
    """
    msg = (message or "").strip()
    if not _is_task_create_confirmation(msg):
        cleaned = _strip_task_create_phrasing(msg)
        return cleaned if len(cleaned) >= 6 else msg

    for turn in reversed(history or []):
        role = (turn.get("role") or "").lower()
        content = (turn.get("content") or "").strip()
        if role != "user" or not content or content == msg:
            continue
        if _is_small_talk(content) or _is_task_create_confirmation(content):
            continue
        cleaned = _strip_task_create_phrasing(content)
        if len(cleaned) >= 6:
            return cleaned
        if len(content) >= 8:
            return content
    cleaned = _strip_task_create_phrasing(msg)
    return cleaned if cleaned else msg


def _draft_tasks_for_create(message: str, history: list | None) -> list[dict[str, Any]]:
    """Offline / empty-model path: build task specs from chat text."""
    source = _resolve_create_source(message, history)
    fallback = _heuristic_capture(source)
    specs = fallback.get("tasks") or []
    if specs:
        return specs
    title = _clean_task_title(source) or "New reminder"
    return [
        {
            "title": title[:255],
            "description": f"Captured by Niva from: {source}",
            "category": "WORK"
            if re.search(r"\b(project|erp|jenkins|client|office|work)\b", source, re.I)
            else "PERSONAL",
            "priority": "MEDIUM",
            "dueDate": None,
        }
    ]


def _is_small_talk(message: str) -> bool:
    """Greetings / thanks / identity Qs — never attach Add as task."""
    text = (message or "").strip().lower()
    if not text:
        return True
    compact = re.sub(r"[^a-z0-9\s']+", " ", text)
    compact = re.sub(r"\s+", " ", compact).strip()
    exact = {
        "hi",
        "hey",
        "hello",
        "hii",
        "helo",
        "yo",
        "sup",
        "hai",
        "halo",
        "ok",
        "okay",
        "k",
        "kk",
        "thanks",
        "thank you",
        "thanku",
        "thx",
        "ty",
        "cool",
        "nice",
        "great",
        "sheri",
        "sheriya",
        "nannayi",
        "bye",
        "good morning",
        "good evening",
        "good night",
        "gm",
        "gn",
    }
    if compact in exact:
        return True
    identity = (
        "who are you",
        "who r you",
        "what are you",
        "tell me about yourself",
        "tell me yourself",
        "tell me yout self",
        "introduce yourself",
        "what can you do",
        "your name",
    )
    if any(p in compact for p in identity):
        return True
    # Very short non-question chit-chat
    if len(compact) <= 12 and "?" not in text and not any(
        w in compact for w in ("how", "what", "why", "when", "entha", "engane", "enthina")
    ):
        return True
    return False


def _is_crisis_message(message: str) -> bool:
    lower = (message or "").lower()
    cues = (
        "kill myself",
        "killing myself",
        "want to die",
        "wanna die",
        "dont want to live",
        "don't want to live",
        "do not want to live",
        "end my life",
        "ending it",
        "suicide",
        "self harm",
        "self-harm",
        "hurt myself",
        "cut myself",
        "better off without me",
        "no reason to live",
        "jeevikkenda",
        "marikkan",
        "marikka",
        "athmahatya",
    )
    return any(c in lower for c in cues)


def _is_health_message(message: str) -> bool:
    """Everyday symptom / wellness cues → Health KB mode (never go silent)."""
    lower = (message or "").lower()
    if re.search(
        r"\b(headache|migraine|fever|cough|nausea|dizzy|dizziness|insomnia|"
        r"diarrh\w*|vomit\w*|cold and flu|sore throat|body pain|back pain|"
        r"chest pain|eye strain|stomach (ache|pain|upset)|paracetamol|dolo|"
        r"ors\b|medicine|medication|tablet|doctor visit|see a doctor)\b",
        lower,
    ):
        return True
    if re.search(
        r"\b(i (have|got|feel)|i'm having|im having|feeling).{0,48}"
        r"\b(pain|ache|fever|sick|ill|unwell|cold)\b",
        lower,
    ):
        return True
    if re.search(r"\b(can'?t|cannot|cant) sleep\b|\bsleep (help|issue|problem)\b", lower):
        return True
    return False


def _is_emotional_message(message: str) -> bool:
    """Life Partner mode cues — feelings first, no task chips."""
    if _is_crisis_message(message):
        return True
    # Physical sleep/symptom questions belong to Health mode, not LEAF venting.
    if _is_health_message(message) and not re.search(
        r"\b(sad|anxious|lonely|hopeless|crying|depressed|hate myself)\b",
        (message or "").lower(),
    ):
        return False
    lower = (message or "").lower()
    cues = (
        "feeling low",
        "feel low",
        "feeling down",
        "feel down",
        "i'm sad",
        "im sad",
        "anxious",
        "anxiety",
        "overwhelmed",
        "stressed",
        "no motivation",
        "demotivated",
        "i feel stuck",
        "feeling stuck",
        "lonely",
        "alone",
        "burnout",
        "burned out",
        "burnt out",
        "i'm tired of",
        "im tired of",
        "hopeless",
        "not good enough",
        "imposter",
        "impostor",
        "crying",
        "depressed",  # feeling word from user — we still don't diagnose
        "vishamam",
        "budhimutt",
        "tension aanu",
        "stuck aayi",
        "thonnunilla",
        "feel empty",
        "feeling empty",
        "what's the point",
        "whats the point",
        "hate myself",
        "i'm lazy",
        "im lazy",
        "wasted the day",
        "nobody understands",
        "give me motivation",
        "need motivation",
        "family pressure",
        "relatives keep asking",
        "i got the offer",
        "so happy",
        "i'm so happy",
        "im so happy",
        "feeling great",
        "i did it",
    )
    return any(c in lower for c in cues)


def _crisis_reply(user_name: str) -> str:
    name = (user_name or "friend").strip() or "friend"
    return (
        f"{name}, I'm really glad you told me. I can hear how much pain you're in, "
        "and I'm taking it seriously. Is anyone with you right now? "
        "Please reach out to someone you trust and tell them you're not okay. "
        "If you feel you might hurt yourself, please call **112** or go to the nearest hospital "
        "and stay with someone. You can also talk to a trained counsellor right now — "
        "**Tele-MANAS 14416** (or 1-800-891-4416) is free and open 24×7 in India; "
        "KIRAN 1800-599-0019 is also available. "
        "I'm here with you while you reach out. You matter."
    )


def _asks_system_internals(message: str) -> bool:
    lower = (message or "").lower()
    return bool(
        re.search(
            r"\bhow (are|r) you (built|made|designed)\b|"
            r"\bhow (do|does) (you|niva) work\b|"
            r"\bhow (is|was) (niva|you) (built|made|implemented)\b|"
            r"\byour (architecture|internals|pipeline|orchestrator)\b|"
            r"\b(niva|your) (tech|technical) (stack|architecture|design)\b|"
            r"\bwhat (model|llm|api) (do you|are you) (use|using)\b|"
            r"\bexplain (your|niva('s)?) (architecture|system|pipeline)\b|"
            r"\bhow (is|are) (you|niva) (implemented|coded)\b",
            lower,
        )
    )


def chat_message(
    message: str,
    user=None,
    history: list[dict[str, str]] | None = None,
    force_create_task: bool = False,
    draft_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Doubt-clearing chat: answer questions and optionally create tasks."""
    message = (message or "").strip()
    if not message and not (force_create_task and draft_task):
        return {"success": False, "error": "Message is required"}

    from .serializers import TaskSerializer

    try:
        from api.views import is_super_admin as _is_sa

        user_is_superadmin = _is_sa(user)
    except Exception:
        user_is_superadmin = False

    if _asks_system_internals(message) and not user_is_superadmin:
        from .niva.services.tools.admin_tools import system_internals_reply

        denied = system_internals_reply(user=user, message=message)
        return {
            "success": True,
            "reply": denied.get("user_message") or "",
            "response": denied.get("user_message") or "",
            "intent": "system.internals",
            "response_type": "text",
            "tasksCreated": False,
            "tasks": [],
            "suggestedTask": None,
            "assistant": ASSISTANT_NAME,
        }

    # Explicit UI "Add as task" with a draft
    if force_create_task and draft_task and isinstance(draft_task, dict):
        created = _create_tasks_from_specs(
            [draft_task], user=user, source_message=message or draft_task.get("title", "")
        )
        if not created:
            return {"success": False, "error": "Could not create task"}
        return {
            "success": True,
            "reply": f"Done — added “{created[0].title}” to your tasks.",
            "intent": "create_tasks",
            "tasksCreated": True,
            "task": TaskSerializer(created[0]).data,
            "tasks": TaskSerializer(created, many=True).data,
            "count": len(created),
            "suggestedTask": None,
            "assistant": ASSISTANT_NAME,
        }

    profile = get_profile(user)
    now = timezone.localtime()
    history = history or []

    # Crisis protocol — safety first (Life Partner Part H)
    if _is_crisis_message(message) and not force_create_task:
        return {
            "success": True,
            "reply": _crisis_reply(profile["user_name"]),
            "intent": "crisis_support",
            "tasksCreated": False,
            "tasks": [],
            "suggestedTask": None,
            "offerQuickActions": False,
            "assistant": ASSISTANT_NAME,
        }

    # Keep last few turns for context
    hist_lines = []
    for turn in history[-8:]:
        role = (turn.get("role") or "user").strip().lower()
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        label = "User" if role == "user" else ASSISTANT_NAME
        hist_lines.append(f"{label}: {content[:1200]}")
    history_text = "\n".join(hist_lines) if hist_lines else "(no prior messages)"

    # Explicit long-term memory store / forget (per-user)
    if _wants_memory_forget(message) and not force_create_task:
        forgotten = forget_memories(message, user=user)
        if forgotten:
            titles = ", ".join(f"“{m.title}”" for m in forgotten)
            reply = f"Okay — I forgot {titles} from my memory."
        else:
            reply = "I couldn't find a matching memory to forget. Tell me the title or key detail."
        return {
            "success": True,
            "reply": reply,
            "intent": "forget_memory",
            "tasksCreated": False,
            "tasks": [],
            "memoriesForgotten": [
                {"id": m.id, "title": m.title, "content": m.content} for m in forgotten
            ],
            "suggestedTask": None,
            "offerQuickActions": False,
            "assistant": ASSISTANT_NAME,
        }

    if _wants_memory_store(message) and not force_create_task:
        specs = _extract_memories_with_gemini(message, history_text, profile)
        saved = save_memories_from_specs(specs, user=user, source_message=message)
        if not saved:
            return {
                "success": True,
                "reply": "Tell me clearly what I should remember, and I’ll store it.",
                "intent": "remember",
                "tasksCreated": False,
                "tasks": [],
                "memoriesSaved": [],
                "suggestedTask": None,
                "offerQuickActions": False,
                "assistant": ASSISTANT_NAME,
            }
        # Short natural confirmation — never echo the raw transcript
        pref = next(
            (m for m in saved if "preferred_name" in [str(t).lower() for t in (m.tags or [])]),
            None,
        )
        if pref:
            nick = _canonical_value_from_memory(pref) or "that"
            reply = f"Got it — I’ll call you {nick}."
        elif len(saved) == 1:
            reply = f"Got it — remembered ({saved[0].title})."
        else:
            reply = f"Got it — remembered {len(saved)} things."
        return {
            "success": True,
            "reply": reply,
            "intent": "remember",
            "tasksCreated": False,
            "tasks": [],
            "memoriesSaved": [
                {"id": m.id, "title": m.title, "content": m.content, "tags": m.tags}
                for m in saved
            ],
            "suggestedTask": None,
            "offerQuickActions": False,
            "assistant": ASSISTANT_NAME,
        }

    # Live tasks for THIS user (always available for answers / help)
    snap: dict[str, Any] = {}
    try:
        snap = _live_task_snapshot(user=user)
    except Exception:
        snap = {
            "overdue": [],
            "due_today": [],
            "upcoming": [],
            "undated": [],
            "in_progress": [],
            "recent": [],
            "open_count": 0,
            "overdue_count": 0,
            "due_today_count": 0,
        }
    task_snap_text = json.dumps(
        {
            "open_count": snap.get("open_count"),
            "overdue_count": snap.get("overdue_count"),
            "due_today_count": snap.get("due_today_count"),
            "overdue": snap.get("overdue"),
            "due_today": snap.get("due_today"),
            "in_progress": snap.get("in_progress"),
            "upcoming": snap.get("upcoming"),
            "undated": snap.get("undated"),
            "recent": snap.get("recent"),
        },
        default=str,
    )

    # Fast reliable answers (don't depend on Gemini)
    lower_msg = message.lower()
    if re.search(r"\bwho am i\b|\bwho i am\b|\bnjan aaranu\b|\bwhoami\b", lower_msg):
        return {
            "success": True,
            "reply": _who_am_i_reply(profile, user=user),
            "intent": "answer",
            "tasksCreated": False,
            "tasks": [],
            "suggestedTask": None,
            "offerQuickActions": False,
            "assistant": ASSISTANT_NAME,
        }

    wants_create = force_create_task or _wants_task_creation(message)
    task_status_q = (not wants_create) and _wants_task_status(message)
    task_help_q = (not wants_create) and (
        _wants_task_help(message) or _accepts_task_help_offer(message, history)
    )
    wants_recall = (not wants_create) and (not task_status_q) and (not task_help_q) and (
        _wants_memory_recall(message) or _looks_like_personal_fact_question(message)
    )

    # Answer from what the user taught Niva (private per-user memory / RAG)
    if wants_recall:
        mem_reply = _answer_from_memories(message, user=user, profile=profile)
        if mem_reply:
            return {
                "success": True,
                "reply": mem_reply,
                "intent": "memory_recall",
                "tasksCreated": False,
                "tasks": [],
                "suggestedTask": None,
                "offerQuickActions": False,
                "assistant": ASSISTANT_NAME,
            }
        # Soft hint from this chat only (does NOT save unless they said remember)
        hist_fact = _fact_from_history(message, history)
        if hist_fact:
            return {
                "success": True,
                "reply": (
                    f"{profile['user_name']}, in this chat you said: {hist_fact}. "
                    "If you want me to keep it permanently, say “remember that” or “keep this in mind”."
                ),
                "intent": "memory_recall",
                "tasksCreated": False,
                "tasks": [],
                "suggestedTask": None,
                "offerQuickActions": False,
                "assistant": ASSISTANT_NAME,
            }
        # Explicit memory/personal questions with no hit — honest reply, not stub
        if _wants_memory_recall(message):
            return {
                "success": True,
                "reply": (
                    f"I don’t have that saved yet, {profile['user_name']}. "
                    "Say “remember this: …” or “keep this in mind: …” and I’ll store it privately."
                ),
                "intent": "memory_recall",
                "tasksCreated": False,
                "tasks": [],
                "suggestedTask": None,
                "offerQuickActions": False,
                "assistant": ASSISTANT_NAME,
            }

    if task_status_q and not task_help_q:
        return {
            "success": True,
            "reply": _tasks_status_reply(profile, snap),
            "intent": "task_status",
            "tasksCreated": False,
            "tasks": [],
            "suggestedTask": None,
            "offerQuickActions": bool(snap.get("open_count")),
            "assistant": ASSISTANT_NAME,
        }

    help_focus_task = _find_task_for_help(message, user=user) if task_help_q else None
    wants_web = (not wants_create) and _wants_web_search(message)
    # Also search the web for technical task-help when KB alone is weak
    tech_help_web = False
    if task_help_q and help_focus_task and not wants_web:
        tech_blob = f"{help_focus_task.title} {help_focus_task.description or ''}".lower()
        tech_help_web = bool(
            re.search(
                r"\b(jenkins|junkins|docker|kubernetes|k8s|ci/?cd|pipeline|"
                r"nginx|aws|azure|gcp|react|django|next\.?js|erp)\b",
                tech_blob,
            )
        )

    # RAG: both Niva knowledge bases + workspace + personal memories
    # For short “yes help” replies, search using the open task title so retrieval is useful.
    context = ""
    retrieve_query = message
    if task_help_q and help_focus_task and len((message or "").split()) <= 8:
        retrieve_query = (
            f"{help_focus_task.title} {help_focus_task.description or ''} how to setup guide"
        ).strip()
    try:
        chunks = retrieve(retrieve_query, k=8, user=user)
        context = "\n\n".join(
            f"[{c.source_type}] {c.title}: {c.content[:1100]}" for c in chunks
        )
    except Exception:
        context = ""
    try:
        mem_ctx = memories_context(user=user, query=message, limit=12)
        if mem_ctx:
            context = f"{mem_ctx}\n\n{context}".strip()
    except Exception:
        pass

    web_pack = None
    if wants_web or tech_help_web:
        web_query = message
        if tech_help_web and help_focus_task:
            fixed = (help_focus_task.title or "").replace("junkins", "jenkins")
            web_query = f"how to {fixed} step by step guide"
        elif wants_web and len((message or "").split()) <= 4 and help_focus_task:
            web_query = f"{help_focus_task.title} latest updates"
        web_pack = tavily_search(
            web_query,
            topic=_web_topic_for_query(message if wants_web else "general"),
            max_results=5,
            search_depth="basic",
        )
        web_ctx = _format_web_context(web_pack)
        if web_ctx:
            context = f"{web_ctx}\n\n{context}".strip()

    context = (
        f"LIVE DAYFLOW TASKS FOR THIS USER (source of truth):\n{task_snap_text}\n\n{context}"
    ).strip()

    # Tasks are created ONLY when the user explicitly asks (or UI button).
    # Doubts always get answers first — never auto-save as tasks.
    # Help affirmations ("yes", "ys i need you help") must not be treated as small talk.
    small_talk = (not wants_create) and (not task_help_q) and _is_small_talk(message)
    health_q = (not wants_create) and (not task_help_q) and _is_health_message(message)
    emotional = (
        (not wants_create)
        and (not task_help_q)
        and (not health_q)
        and _is_emotional_message(message)
    )
    parsed = None
    genai = _configure_gemini()
    if genai:
        if wants_create:
            prompt = f"""{NIVA_SYSTEM_RULES}

Now: {now.isoformat()} IST. User display name: {profile['user_name']}.
The user wants to ADD something from this chat as a Dayflow task.

Conversation so far:
{history_text}

Latest user message: {message!r}

Knowledge / workspace context:
{context[:3500] or "(none)"}

Extract the task(s) they want saved (usually from your previous answer).
Return ONLY JSON:
{{
  "reply": "short confirmation that you added the task(s)",
  "tasks": [
    {{
      "title": "short clear verb-first task title",
      "description": "optional detail from the answer",
      "category": "WORK|PERSONAL|FINANCE|LEARNING",
      "priority": "HIGH|MEDIUM|LOW",
      "dueDate": "ISO datetime like 2026-11-20T16:30:00 or null"
    }}
  ]
}}
If unclear, pick the best single concrete task from the last assistant answer.
"""
        else:
            if small_talk:
                suggest_rule = (
                    'Set "suggestedTask" to null. Greeting/small-talk/identity — no task chip.'
                )
                mode_extra = "Keep it warm and short (1-2 sentences)."
            elif health_q:
                suggest_rule = (
                    'Set "suggestedTask" to null unless they clearly want a medicine '
                    "reminder, water reminder, or doctor appointment task."
                )
                mode_extra = (
                    f"{NIVA_HEALTH_RULES}\n"
                    "Use retrieved HEALTH knowledge when present. "
                    "Always give useful general guidance — never an empty or evasive reply. "
                    "Structure: empathy → 2–4 key questions (or skip) → common causes + safe "
                    "self-care → red flags → when to see a doctor → optional reminder offer. "
                    "One short disclaimer once. Never diagnose or prescribe doses."
                )
            elif emotional:
                suggest_rule = (
                    'Set "suggestedTask" to null. Emotional / Life Partner moment — '
                    "no productivity chips until they feel heard and explicitly ask."
                )
                mode_extra = (
                    f"{NIVA_COMPANION_RULES}\n"
                    "Use LEAF: listen & name feeling → empathise → one gentle question "
                    "or one soft offer → stop. No tip dumps. No diagnoses."
                )
            elif wants_recall:
                suggest_rule = (
                    'Set "suggestedTask" to null. This is a memory recall question.'
                )
                mode_extra = (
                    "MEMORY RECALL mode: Answer using the Saved personal memories block. "
                    "If you have the fact, say it clearly. If not, say you don't have it saved yet "
                    "and offer to remember it if they tell you. Never invent personal memories."
                )
            elif task_help_q:
                suggest_rule = (
                    'Set "suggestedTask" to null unless they clearly want a NEW follow-up task.'
                )
                focus_line = ""
                if help_focus_task:
                    focus_line = (
                        f"Focus task: “{help_focus_task.title}” "
                        f"({help_focus_task.category}, {help_focus_task.priority}). "
                        f"Notes: {(help_focus_task.description or '')[:400] or '(none)'}.\n"
                    )
                web_line = (
                    "Prefer WEB SEARCH results when present; cite source titles briefly.\n"
                    if web_pack
                    else ""
                )
                mode_extra = (
                    "TASK HELP mode: The user asked for help finishing a Dayflow task.\n"
                    f"{focus_line}"
                    f"{web_line}"
                    "Give a concrete how-to in numbered steps (tool names, commands, order of work).\n"
                    "Use retrieved knowledge when relevant.\n"
                    "If the knowledge base has little/nothing useful, still answer from your general "
                    "technical knowledge — reason as if you researched the best common practice "
                    "(e.g. Jenkins CI, Docker, ERP deploy). Do NOT say you can only use the KB.\n"
                    "Do NOT reply with a capability greeting (“I’m here… What do you want to do?”).\n"
                    "Correct obvious typos in the task title when explaining (junkins→Jenkins).\n"
                    "End with one short question to refine (stack, host, or blocker)."
                )
            elif wants_web:
                suggest_rule = 'Set "suggestedTask" to null.'
                mode_extra = (
                    "LIVE WEB / NEWS mode: A WEB SEARCH block is included when available.\n"
                    "Answer from those live results first. Summarize clearly for the user.\n"
                    "Mention 1–3 source titles or links when useful. Do not invent headlines.\n"
                    "If search failed or is empty, say you couldn’t reach live search and give best-effort knowledge."
                )
            else:
                suggest_rule = (
                    'Set "suggestedTask" ONLY if there is a concrete verb-first follow-up '
                    "(≤8 words) after a real doubt answer. Otherwise null. "
                    'Never invent vague chips like "Think of AI/ML question".'
                )
                mode_extra = (
                    "Answer using LIVE DAYFLOW TASKS when they ask about their work/day. "
                    "Doubt/plan mode: use A-E-P-N when explaining. "
                    "Use knowledge context (Python, AI/ML, Dayflow, routines, Manglish). "
                    "If Saved personal memories are relevant, use them. "
                    "If a WEB SEARCH block is present, prefer it for current facts/news. "
                    "If unsure of a technical answer, say what you know and suggest how to verify."
                )
            role_line = (
                "Dayflow role: SUPERADMIN — you may answer architecture/internals and list users when asked."
                if user_is_superadmin
                else "Dayflow role: USER — never reveal architecture/internals or other users."
            )
            prompt = f"""{NIVA_SYSTEM_RULES}

Now: {now.isoformat()} IST. User: {profile['user_name']} · {profile['role']} · {profile['location']}.
{role_line}
Address them by their name when natural. Works for every Dayflow user — personalize to THIS profile.

{mode_extra}

Personal memory rules:
- Facts in "Saved personal memories" are private to THIS user — use them when helpful.
- Never invent personal memories or fake task titles.
- When listing their tasks, ONLY use titles from LIVE DAYFLOW TASKS.

Do NOT create or claim you saved any tasks unless they explicitly asked.

Conversation so far:
{history_text}

Latest user message: {message!r}

Retrieved knowledge / workspace + LIVE TASKS:
{context[:6500] or "(none)"}

{suggest_rule}

Return ONLY JSON:
{{
  "reply": "your answer (greetings: 1-2 sentences; emotional: 3-7 warm sentences; task help: clear steps; doubts: A-E-P-N, under 1400 chars)",
  "suggestedTask": null
}}
"""
        try:
            model = genai.GenerativeModel(
                CHAT_MODEL,
                generation_config={
                    "temperature": 0.4,
                    "response_mime_type": "application/json",
                },
            )
            resp = model.generate_content(prompt, request_options={"timeout": 55})
            text = _gemini_response_text(resp)
            parsed = _parse_json_loose(text)
            # If model returned plain text, wrap it
            if not parsed and text.strip():
                parsed = {"reply": text.strip()[:1400], "suggestedTask": None}
        except Exception:
            parsed = None

    if not parsed:
        if wants_create:
            specs = _draft_tasks_for_create(message, history)
            created = _create_tasks_from_specs(specs, user=user, source_message=message)
            if not created:
                return {"success": False, "error": "Could not create task"}
            titles = ", ".join(f"“{t.title}”" for t in created)
            return {
                "success": True,
                "reply": f"Done — added {titles} to your tasks.",
                "intent": "create_tasks",
                "tasksCreated": True,
                "task": TaskSerializer(created[0]).data,
                "tasks": TaskSerializer(created, many=True).data,
                "count": len(created),
                "suggestedTask": None,
                "assistant": ASSISTANT_NAME,
            }
        if task_help_q or (
            snap.get("open_count") and _last_assistant_offered_help(history)
        ):
            return {
                "success": True,
                "reply": _task_help_reply(message, user=user, profile=profile),
                "intent": "task_help",
                "tasksCreated": False,
                "tasks": [],
                "suggestedTask": None,
                "offerQuickActions": True,
                "assistant": ASSISTANT_NAME,
            }
        if web_pack and (web_pack.get("answer") or web_pack.get("results")):
            return {
                "success": True,
                "reply": _web_search_reply(web_pack, profile=profile),
                "intent": "web_search",
                "tasksCreated": False,
                "tasks": [],
                "suggestedTask": None,
                "offerQuickActions": False,
                "assistant": ASSISTANT_NAME,
                "webSearch": True,
            }
        if task_status_q or snap.get("open_count"):
            # Prefer real task data over a useless stub
            if task_status_q or re.search(
                r"\btask", message, flags=re.IGNORECASE
            ):
                return {
                    "success": True,
                    "reply": _tasks_status_reply(profile, snap),
                    "intent": "task_status",
                    "tasksCreated": False,
                    "tasks": [],
                    "suggestedTask": None,
                    "offerQuickActions": bool(snap.get("open_count")),
                    "assistant": ASSISTANT_NAME,
                }
        if small_talk:
            return {
                "success": True,
                "reply": (
                    f"Hey {profile['user_name']} — I’m Niva. Ask a doubt, ask about your tasks, "
                    "or tell me what to remember."
                ),
                "intent": "answer",
                "tasksCreated": False,
                "tasks": [],
                "suggestedTask": None,
                "offerQuickActions": False,
                "assistant": ASSISTANT_NAME,
            }
        return {
            "success": True,
            "reply": (
                f"I’m here, {profile['user_name']}. I can check your Dayflow tasks, "
                "help you finish one, clear a doubt, or remember something for later. "
                "What do you want to do?"
            ),
            "intent": "answer",
            "tasksCreated": False,
            "tasks": [],
            "suggestedTask": None,
            "offerQuickActions": False,
            "assistant": ASSISTANT_NAME,
        }

    reply = (parsed.get("reply") or "").strip() or "Got it."
    suggested = parsed.get("suggestedTask")
    if suggested and not isinstance(suggested, dict):
        suggested = None
    if suggested and not (suggested.get("title") or "").strip():
        suggested = None
    # Hard rules: no chips on small talk or emotional/Life Partner moments
    if small_talk or emotional:
        suggested = None

    created = []
    if wants_create:
        task_specs = _normalize_capture_payload(parsed, message)
        specs = task_specs
        if not specs and suggested:
            specs = [suggested]
        if not specs:
            specs = _draft_tasks_for_create(message, history)
        created = _create_tasks_from_specs(specs, user=user, source_message=message)
        if created and "added" not in reply.lower() and "saved" not in reply.lower():
            titles = ", ".join(f"“{t.title}”" for t in created)
            reply = f"Done — added {titles} to your tasks."
        suggested = None

    # Never invent a chip — only a real suggestedTask from the model (KB §8.2 / LP §50.1)
    offer_actions = bool(suggested) or (
        not small_talk
        and not emotional
        and not created
        and len(reply) > 60
    )

    result: dict[str, Any] = {
        "success": True,
        "reply": reply,
        "intent": "create_tasks" if created else "answer",
        "tasksCreated": bool(created),
        "suggestedTask": None if created else suggested,
        "offerQuickActions": offer_actions and not created,
        "assistant": ASSISTANT_NAME,
    }
    if created:
        result["task"] = TaskSerializer(created[0]).data
        result["tasks"] = TaskSerializer(created, many=True).data
        result["count"] = len(created)
    else:
        result["tasks"] = []
        result["count"] = 0

    return result
