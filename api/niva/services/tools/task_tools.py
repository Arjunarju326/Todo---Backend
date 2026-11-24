"""Verified task tools — Django is source of truth."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from api.models import Task, TaskStatus
from api.serializers import TaskSerializer


def task_create(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from api.assistant_service import _draft_tasks_for_create, _create_tasks_from_specs

    specs = []
    if draft_task and isinstance(draft_task, dict) and draft_task.get("title"):
        specs = [draft_task]
    else:
        specs = _draft_tasks_for_create(message, intent.get("_history") or [])

    created = _create_tasks_from_specs(specs, user=user, source_message=message)
    if not created:
        return {
            "ok": False,
            "user_message": "I couldn’t save that task. It hasn’t been added yet — try again.",
            "response_type": "error",
        }
    titles = ", ".join(f"“{t.title}”" for t in created)
    data = TaskSerializer(created, many=True).data
    return {
        "ok": True,
        "user_message": f"Done — added {titles} to your tasks.",
        "response_type": "task_confirmation",
        "data": {"tasks": data, "task": data[0] if data else None, "count": len(created)},
        "actions": [
            {"type": "open_task", "label": "View task", "target_id": created[0].id}
        ],
        "tasks": data,
        "tasksCreated": True,
        "task": data[0],
        "count": len(created),
    }


def task_list(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    from api.assistant_service import _live_task_snapshot, _tasks_status_reply, get_profile

    snap = _live_task_snapshot(user=user)
    profile = get_profile(user)
    reply = _tasks_status_reply(profile, snap)
    open_tasks = []
    for key in ("overdue", "due_today", "in_progress", "undated", "upcoming"):
        open_tasks.extend(snap.get(key) or [])
    return {
        "ok": True,
        "user_message": reply,
        "response_type": "task_list",
        "data": {"snapshot": snap, "tasks": open_tasks[:20]},
        "actions": [],
        "offerQuickActions": bool(snap.get("open_count")),
    }


def task_complete(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    qs = list(
        Task.objects.filter(user=user)
        .exclude(status=TaskStatus.DONE)
        .order_by("due_date", "-priority")[:40]
    )
    if not qs:
        return {
            "ok": False,
            "user_message": "You don’t have any open tasks to mark complete.",
            "response_type": "text",
        }
    lower = (message or "").lower()
    target = None
    for t in qs:
        if len(t.title) >= 4 and t.title.lower() in lower:
            target = t
            break
    if not target:
        target = qs[0]
    target.status = TaskStatus.DONE
    target.completed_at = timezone.now()
    target.save(update_fields=["status", "completed_at", "updated_at"])
    data = TaskSerializer(target).data
    return {
        "ok": True,
        "user_message": f"Marked “{target.title}” as done.",
        "response_type": "task_confirmation",
        "data": {"task": data},
        "actions": [{"type": "open_task", "label": "View task", "target_id": target.id}],
    }


def task_update(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    return {
        "ok": False,
        "user_message": "Tell me which task to change and what to update (title, due date, or priority).",
        "response_type": "clarification",
    }
