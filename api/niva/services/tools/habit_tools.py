from __future__ import annotations

from typing import Any

from api.models import Habit


def habit_get_today(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    habits = list(Habit.objects.filter(user=user).order_by("-streak", "name")[:20])
    if not habits:
        return {
            "ok": True,
            "user_message": "You don’t have habits tracked yet. Add one in Habits when you’re ready.",
            "response_type": "text",
            "data": {"habits": []},
        }
    lines = [f"• {h.name} — streak {h.streak} days ({h.category})" for h in habits]
    return {
        "ok": True,
        "user_message": "Your habits:\n" + "\n".join(lines),
        "response_type": "text",
        "data": {
            "habits": [
                {"id": h.id, "name": h.name, "streak": h.streak, "category": h.category}
                for h in habits
            ]
        },
    }
