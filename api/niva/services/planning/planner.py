"""Daily planner from real Dayflow task data."""

from __future__ import annotations

from datetime import datetime, timedelta, time as dtime
from typing import Any

from django.utils import timezone

from api.models import Habit, LearningGoal, LearningGoalStatus, NivaDailyPlan, Task
from api.niva.services.planning.prioritizer import prioritized_open_tasks


def build_daily_plan(
    user,
    *,
    available_minutes: int | None = None,
    message: str = "",
) -> dict[str, Any]:
    now = timezone.localtime()
    today = now.date()
    scored = prioritized_open_tasks(user, limit=15)
    minutes = available_minutes or 240  # default 4h focus budget

    blocks = []
    cursor = now.replace(second=0, microsecond=0)
    if cursor.hour < 9:
        cursor = cursor.replace(hour=9, minute=0)
    used = 0
    focus_id = None
    scheduled_ids = set()

    for score, task in scored:
        slot = 45 if (task.priority or "").upper() == "HIGH" else 30
        if used + slot > minutes:
            if minutes - used >= 15:
                slot = minutes - used
            else:
                break
        start = cursor
        end = cursor + timedelta(minutes=slot)
        blocks.append(
            {
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "type": "task",
                "task_id": task.id,
                "title": task.title,
                "reason": f"Priority score {score:.2f}",
                "priority": task.priority,
            }
        )
        if focus_id is None:
            focus_id = task.id
        scheduled_ids.add(task.id)
        used += slot
        cursor = end + timedelta(minutes=10)  # break buffer
        blocks.append(
            {
                "start": end.strftime("%H:%M"),
                "end": cursor.strftime("%H:%M"),
                "type": "break",
                "title": "Short break",
            }
        )
        if used >= minutes:
            break

    # Remove trailing break
    if blocks and blocks[-1].get("type") == "break":
        blocks.pop()

    learning = (
        LearningGoal.objects.filter(user=user)
        .exclude(status=LearningGoalStatus.COMPLETED)
        .order_by("-progress_percentage")
        .first()
    )
    learning_target = None
    if learning and minutes >= 60:
        learning_target = {
            "topic": learning.title,
            "duration_minutes": 30 if minutes >= 90 else 15,
        }

    unscheduled = [
        {"id": t.id, "title": t.title, "priority": t.priority}
        for _, t in scored
        if t.id not in scheduled_ids
    ][:10]

    habits = list(Habit.objects.filter(user=user).order_by("-streak")[:5])
    summary = (
        f"Focus on “{blocks[0]['title']}” first."
        if blocks and blocks[0].get("type") == "task"
        else "Your board is light — good day to capture or learn."
    )

    payload = {
        "date": today.isoformat(),
        "summary": summary,
        "focus_task_id": focus_id,
        "time_blocks": blocks,
        "learning_target": learning_target,
        "unscheduled_tasks": unscheduled,
        "habits": [{"id": h.id, "name": h.name, "streak": h.streak} for h in habits],
        "available_minutes": minutes,
        "warnings": [],
    }
    if available_minutes and available_minutes < 45 and len(blocks) > 1:
        payload["warnings"].append("Limited time — only the top priority was scheduled.")

    NivaDailyPlan.objects.update_or_create(
        user=user,
        plan_date=today,
        defaults={
            "summary": summary,
            "focus_task_id": focus_id,
            "payload": payload,
        },
    )
    return payload


def plan_as_reply(plan: dict[str, Any], *, user_name: str = "there") -> str:
    lines = [f"Here’s a realistic plan for today, {user_name}:", plan.get("summary") or ""]
    for b in plan.get("time_blocks") or []:
        if b.get("type") == "break":
            lines.append(f"- {b['start']}–{b['end']}: break")
        else:
            lines.append(f"- {b['start']}–{b['end']}: {b.get('title')}")
    lt = plan.get("learning_target")
    if lt:
        lines.append(
            f"Learning target: {lt.get('duration_minutes')} min on “{lt.get('topic')}”."
        )
    if plan.get("warnings"):
        lines.append("Note: " + "; ".join(plan["warnings"]))
    lines.append("Want me to replan with a different time budget?")
    return "\n".join([l for l in lines if l])


def review_day(user) -> dict[str, Any]:
    now = timezone.localtime()
    start = timezone.make_aware(datetime.combine(now.date(), dtime.min))
    end = timezone.make_aware(datetime.combine(now.date(), dtime.max))
    done = Task.objects.filter(
        user=user, status="DONE", completed_at__gte=start, completed_at__lte=end
    ).count()
    open_count = Task.objects.filter(user=user).exclude(status="DONE").count()
    plan = NivaDailyPlan.objects.filter(user=user, plan_date=now.date()).first()
    focus = None
    if plan and plan.focus_task_id:
        focus = Task.objects.filter(id=plan.focus_task_id, user=user).first()

    reply = (
        f"Today’s review: you completed {done} task(s). "
        f"{open_count} still open. "
    )
    if focus and focus.status != "DONE":
        reply += f"Your focus task “{focus.title}” is still open — want to move it to tomorrow?"
    elif done:
        reply += "Nice progress. Keep tomorrow’s list short."
    else:
        reply += "If today was heavy, we can plan a lighter tomorrow."

    return {
        "completed_today": done,
        "open_count": open_count,
        "focus_task": focus.title if focus else None,
        "reply": reply,
    }
