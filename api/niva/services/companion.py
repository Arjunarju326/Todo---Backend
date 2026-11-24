"""Companion layer — personality, mood tone, check-ins, weekly review (opt-in)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.utils import timezone

from api.models import Habit, Task, TaskStatus
from api.niva.services.finance import money, rule_based_insights, spending_summary


MOOD_TIRED = "tired"
MOOD_STRESSED = "stressed"
MOOD_NEUTRAL = "neutral"
MOOD_UPBEAT = "upbeat"

_TIRED = re.compile(
    r"\b(tired|exhausted|sleepy|drained|no energy|burnt out|burned out|kazhinju)\b",
    re.I,
)
_STRESSED = re.compile(
    r"\b(stressed|stress|anxious|overwhelmed|pressure|panic|hectic|too much)\b",
    re.I,
)
_UPBEAT = re.compile(
    r"\b(excited|great day|feeling good|pumped|motivated|happy|awesome)\b",
    re.I,
)


def detect_mood(message: str) -> str:
    text = message or ""
    if _STRESSED.search(text):
        return MOOD_STRESSED
    if _TIRED.search(text):
        return MOOD_TIRED
    if _UPBEAT.search(text):
        return MOOD_UPBEAT
    return MOOD_NEUTRAL


def preferred_name(profile: dict[str, Any] | None) -> str:
    return ((profile or {}).get("user_name") or "there").strip() or "there"


def apply_companion_tone(
    reply: str,
    *,
    mood: str = MOOD_NEUTRAL,
    profile: dict[str, Any] | None = None,
    celebrate: bool = False,
) -> str:
    """Light, practical tone shaping — no therapy claims."""
    text = (reply or "").strip()
    if not text:
        return text
    name = preferred_name(profile)

    if mood in (MOOD_TIRED, MOOD_STRESSED):
        # Soften + keep short — strip hustle language
        text = re.sub(
            r"\b(crush it|hustle|grind|push hard|no excuses)\b",
            "go easy",
            text,
            flags=re.I,
        )
        text = re.sub(r"(go easy\s*){2,}", "go easy ", text, flags=re.I)
        if mood == MOOD_TIRED and not text.lower().startswith(("hey", "hi ", name.lower())):
            text = f"Alright {name} — keep it light.\n{text}"
        elif mood == MOOD_STRESSED and "one thing" not in text.lower():
            text = f"{text}\nOne thing at a time is enough today."
        # Truncate if long
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
        if len(parts) > 4:
            text = " ".join(parts[:4])
    elif celebrate:
        if not re.search(r"\b(nice|well done|good work|solid)\b", text, re.I):
            text = f"{text} Nice work."
    elif mood == MOOD_UPBEAT and name and name != "there":
        if not text.lower().startswith(name.lower()):
            text = f"{name}, {text[0].lower()}{text[1:]}" if len(text) > 1 else text

    return text.strip()


def shrink_plan_for_mood(plan: dict[str, Any], mood: str) -> dict[str, Any]:
    """When tired/stressed, keep only the top focus items."""
    if mood not in (MOOD_TIRED, MOOD_STRESSED):
        return plan
    out = dict(plan or {})
    blocks = list(out.get("time_blocks") or [])
    focus = [b for b in blocks if (b.get("type") or "") != "break"][:2]
    breaks = [b for b in blocks if (b.get("type") or "") == "break"][:1]
    out["time_blocks"] = focus + breaks
    out["summary"] = (
        "Short plan — energy looks low, so just the essentials."
        if mood == MOOD_TIRED
        else "Short plan — one clear focus, nothing extra."
    )
    out["mood_adjusted"] = mood
    return out


def top_open_tasks(user, *, limit: int = 3) -> list[dict[str, Any]]:
    qs = (
        Task.objects.filter(user=user)
        .exclude(status=TaskStatus.DONE)
        .order_by("due_date", "-priority", "-is_important")[:limit]
    )
    return [
        {
            "id": t.id,
            "title": t.title,
            "priority": t.priority,
            "dueDate": t.due_date.isoformat() if t.due_date else None,
        }
        for t in qs
    ]


def habit_reminder(user) -> dict[str, Any] | None:
    habits = list(Habit.objects.filter(user=user).order_by("-streak", "name")[:10])
    if not habits:
        return None
    today = timezone.localdate().isoformat()
    for h in habits:
        dates = h.completed_dates or []
        if today not in [str(d)[:10] for d in dates]:
            return {"id": h.id, "name": h.name, "streak": h.streak}
    # All done — celebrate streak leader
    top = habits[0]
    return {"id": top.id, "name": top.name, "streak": top.streak, "done_today": True}


def build_morning_checkin(user, *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    name = preferred_name(profile)
    tasks = top_open_tasks(user, limit=3)
    habit = habit_reminder(user)
    lines = [f"Good morning, {name}."]
    if tasks:
        lines.append("Top 3 for today:")
        for i, t in enumerate(tasks, 1):
            lines.append(f"{i}. {t['title']}")
    else:
        lines.append("No open tasks on the board — nice clear start.")
    if habit:
        if habit.get("done_today"):
            lines.append(f"Habit “{habit['name']}” already logged (streak {habit['streak']}).")
        else:
            lines.append(
                f"Gentle habit nudge: “{habit['name']}” (streak {habit['streak']})."
            )
    reply = "\n".join(lines)
    return {
        "reply": reply,
        "response_type": "companion_morning",
        "data": {"tasks": tasks, "habit": habit},
    }


def build_evening_checkin(user, *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    from api.niva.services.planning.planner import review_day

    name = preferred_name(profile)
    review = review_day(user)
    done = review.get("completed_today") or 0
    open_count = review.get("open_count") or 0
    focus = review.get("focus_task")

    lines = [f"Evening check-in, {name}."]
    lines.append(f"Finished {done} task(s) today. Still open: {open_count}.")
    if focus:
        lines.append(f"“{focus}” can carry over — no rush.")
    lines.append("Rest well — tomorrow can take the rest.")
    return {
        "reply": "\n".join(lines),
        "response_type": "companion_evening",
        "data": review if isinstance(review, dict) else {"review": review},
    }


def build_weekly_review(user, *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    name = preferred_name(profile)
    now = timezone.localtime()
    week_start = now - timedelta(days=now.weekday())
    start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    done_tasks = Task.objects.filter(
        user=user, status=TaskStatus.DONE, completed_at__gte=start
    ).count()
    open_tasks = Task.objects.filter(user=user).exclude(status=TaskStatus.DONE).count()

    spend = spending_summary(user, period="this_week")
    habits = list(Habit.objects.filter(user=user).order_by("-streak")[:5])
    streak_bits = [f"{h.name} ({h.streak}d)" for h in habits if h.streak]

    insights = rule_based_insights(user)
    insight_line = ""
    for i in insights.get("insights") or []:
        if i.get("type") in ("category_spike", "large_one_off", "balance"):
            insight_line = i.get("message") or ""
            break

    suggestion = "Pick one small habit to protect next week — consistency over intensity."
    if open_tasks > 8:
        suggestion = "You have a lot open — park or delete 2 low-value tasks to breathe."
    elif done_tasks >= 5:
        suggestion = "Solid completion week. Keep one deep-work block on the calendar."

    cur = spend.get("currency") or "₹"
    lines = [
        f"Weekly review for {name}",
        f"Tasks completed this week: {done_tasks}. Still open: {open_tasks}.",
        f"Spending this week: {money(spend.get('expense_total'), cur)}.",
    ]
    if streak_bits:
        lines.append("Habit streaks: " + ", ".join(streak_bits[:4]) + ".")
    if insight_line:
        lines.append(insight_line)
    lines.append(f"One suggestion: {suggestion}")

    return {
        "reply": "\n".join(lines),
        "response_type": "weekly_review",
        "data": {
            "tasksCompleted": done_tasks,
            "tasksOpen": open_tasks,
            "spending": spend,
            "habits": [
                {"id": h.id, "name": h.name, "streak": h.streak} for h in habits
            ],
            "suggestion": suggestion,
            "insights": insights.get("insights") or [],
        },
    }


def overdue_nudge(user, *, settings_obj=None, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """At most one overdue nudge per day (caller enforces date)."""
    now = timezone.localtime()
    overdue = list(
        Task.objects.filter(user=user, due_date__lt=now)
        .exclude(status=TaskStatus.DONE)
        .order_by("due_date")[:3]
    )
    if not overdue:
        return None
    name = preferred_name(profile)
    titles = ", ".join(f"“{t.title}”" for t in overdue[:2])
    extra = f" (+{len(overdue) - 2} more)" if len(overdue) > 2 else ""
    return {
        "reply": (
            f"Hey {name} — gentle nudge: {titles}{extra} "
            f"{'is' if len(overdue) == 1 else 'are'} overdue. "
            "No guilt — want to reschedule or mark one done?"
        ),
        "response_type": "companion_nudge",
        "data": {
            "kind": "overdue",
            "tasks": [{"id": t.id, "title": t.title} for t in overdue],
        },
    }


def spend_alert(user, *, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Only when a finance rule triggers — not daily noise."""
    insights = rule_based_insights(user)
    warn = [
        i
        for i in (insights.get("insights") or [])
        if i.get("severity") == "warn" or i.get("type") in ("category_spike", "large_one_off")
    ]
    if not warn:
        return None
    name = preferred_name(profile)
    msg = warn[0].get("message") or "Unusual spending pattern spotted."
    return {
        "reply": f"{name}, quick money note — {msg}",
        "response_type": "companion_nudge",
        "data": {"kind": "spend", "insight": warn[0]},
    }
