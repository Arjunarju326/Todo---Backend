"""Schedule builder helpers (time-block allocation used by planner)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def allocate_blocks(
    tasks: list[Any],
    *,
    start: datetime,
    available_minutes: int,
) -> list[dict[str, Any]]:
    """Allocate sequential focus blocks with short breaks."""
    blocks: list[dict[str, Any]] = []
    cursor = start
    used = 0
    for task in tasks:
        slot = 45 if getattr(task, "priority", "") == "HIGH" else 30
        if used + slot > available_minutes:
            break
        end = cursor + timedelta(minutes=slot)
        blocks.append(
            {
                "start": cursor.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "type": "task",
                "task_id": getattr(task, "id", None),
                "title": getattr(task, "title", str(task)),
            }
        )
        used += slot
        cursor = end + timedelta(minutes=10)
    return blocks
