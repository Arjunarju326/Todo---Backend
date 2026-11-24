from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Any

from django.utils import timezone

from api.models import Task, TaskStatus


def _priority_weight(p: str) -> float:
    return {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}.get((p or "").upper(), 0.5)


def score_task(task: Task, now=None) -> float:
    now = now or timezone.localtime()
    start = timezone.make_aware(datetime.combine(now.date(), dtime.min))
    end = timezone.make_aware(datetime.combine(now.date(), dtime.max))

    deadline = 0.3
    overdue = 0.0
    if task.due_date:
        if task.due_date < start:
            deadline = 1.0
            overdue = 1.0
        elif task.due_date <= end:
            deadline = 0.85
        else:
            days = max(1.0, (task.due_date - now).total_seconds() / 86400.0)
            deadline = max(0.2, 1.0 - min(days, 14) / 14.0)
    else:
        # Undated open tasks count as today's work (same as Tasks / Dashboard)
        deadline = 0.8

    user_importance = _priority_weight(task.priority)
    if task.is_important:
        user_importance = min(1.0, user_importance + 0.2)

    goal_alignment = 0.5
    if (task.category or "").upper() == "LEARNING":
        goal_alignment = 0.7
    elif (task.category or "").upper() == "WORK":
        goal_alignment = 0.75

    dependency = 0.5  # placeholder until dependency graph exists

    return (
        0.30 * deadline
        + 0.25 * user_importance
        + 0.20 * goal_alignment
        + 0.15 * dependency
        + 0.10 * overdue
    )


def prioritized_open_tasks(user, limit: int = 20) -> list[tuple[float, Task]]:
    qs = list(
        Task.objects.filter(user=user)
        .exclude(status=TaskStatus.DONE)
        .order_by("due_date", "-priority")[:60]
    )
    scored = [(score_task(t), t) for t in qs]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]
