from __future__ import annotations

from typing import Any

from api.models import LearningGoal, LearningGoalStatus


def goal_get_active(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    goals = list(
        LearningGoal.objects.filter(user=user)
        .exclude(status=LearningGoalStatus.COMPLETED)
        .order_by("-progress_percentage")[:15]
    )
    if not goals:
        return {
            "ok": True,
            "user_message": "No active learning goals yet. Say “I want to learn …” and I’ll set one up.",
            "response_type": "text",
            "data": {"goals": []},
        }
    lines = [
        f"• {g.title} — {g.progress_percentage}% ({g.status})"
        for g in goals
    ]
    return {
        "ok": True,
        "user_message": "Active goals:\n" + "\n".join(lines),
        "response_type": "learning_progress",
        "data": {
            "goals": [
                {
                    "id": g.id,
                    "title": g.title,
                    "progress": g.progress_percentage,
                    "status": g.status,
                }
                for g in goals
            ]
        },
    }
