"""Superadmin-only Dayflow admin tools for Niva."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.utils import timezone


def _is_super_admin(user) -> bool:
    try:
        from api.views import is_super_admin

        return is_super_admin(user)
    except Exception:
        return False


def users_list(*, user, message: str = "", intent: dict | None = None, **_kwargs) -> dict[str, Any]:
    if not _is_super_admin(user):
        return {
            "ok": True,
            "response_type": "text",
            "user_message": (
                "I can only share the Dayflow user list with the superadmin. "
                "If you need something else, ask about your own tasks or plans."
            ),
            "data": {"users": [], "denied": True},
        }

    User = get_user_model()
    now = timezone.now()
    rows = []
    for u in User.objects.all().order_by("-date_joined"):
        last = u.last_login
        # Active account flag + recently seen heuristic (30 days)
        recently = bool(last and (now - last).days <= 30)
        display = (u.first_name or "").strip() or u.username
        try:
            from api.models import UserSettings

            s = UserSettings.objects.filter(user=u).first()
            if s and (s.user_name or "").strip():
                display = s.user_name.strip()
        except Exception:
            pass
        rows.append(
            {
                "id": u.id,
                "username": u.username,
                "displayName": display,
                "email": u.email or "",
                "isActive": bool(u.is_active),
                "isSuperAdmin": _is_super_admin(u),
                "dateJoined": u.date_joined.isoformat() if u.date_joined else None,
                "lastLogin": last.isoformat() if last else None,
                "recentlyActive": recently,
            }
        )

    lines = [f"Dayflow users ({len(rows)}):"]
    for r in rows:
        joined = (r["dateJoined"] or "")[:10] or "—"
        last = (r["lastLogin"] or "never")[:16].replace("T", " ")
        status = "active" if r["isActive"] else "inactive"
        recent = " · recently seen" if r["recentlyActive"] else ""
        admin = " · superadmin" if r["isSuperAdmin"] else ""
        lines.append(
            f"• {r['displayName']} (@{r['username']}) — {status}{admin}, "
            f"joined {joined}, last login {last}{recent}"
        )

    return {
        "ok": True,
        "response_type": "admin_users",
        "user_message": "\n".join(lines),
        "data": {"users": rows, "count": len(rows)},
    }


def system_internals_reply(*, user, message: str = "", **_kwargs) -> dict[str, Any]:
    """How Niva is built / works — superadmin only."""
    if not _is_super_admin(user):
        return {
            "ok": True,
            "response_type": "text",
            "user_message": (
                "I keep my internal build details private. "
                "I can still help with your tasks, plans, learning, health tips, and reminders — "
                "what do you need?"
            ),
            "data": {"denied": True},
        }

    reply = (
        "Here’s how I’m built inside Dayflow (superadmin view):\n"
        "• Chat entry: `/api/assistant/chat` → Niva v2 orchestrator\n"
        "• Pipeline: intent router → context builder (memory + Dayflow snapshot) → "
        "verified tools → response composer (Gemini fallback for explain/chat)\n"
        "• Memory: selective long-term facts per user (AssistantMemory), ranked retrieval — not full chat dumps\n"
        "• Knowledge: three RAG KBs — productivity, life partner, health — seeded into AssistantChunk\n"
        "• Tools: tasks, habits, goals, memory, research (Tavily when needed), learning, "
        "and admin user-list for you\n"
        "• Models: Gemini for chat/embeddings; regex intent routing for speed\n"
        "• Intelligence Lab: eval suite + optional traces (`NIVA_TRACE_ENABLED`)\n"
        "I never invent successful actions — tools confirm against the Django DB first."
    )
    return {
        "ok": True,
        "response_type": "system_internals",
        "user_message": reply,
        "data": {"superadmin": True},
    }
