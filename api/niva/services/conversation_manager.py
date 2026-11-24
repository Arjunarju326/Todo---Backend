"""Conversation continuity + rolling summaries."""

from __future__ import annotations

from api.models import NivaConversation, NivaConversationSummary


def get_or_create_conversation(user, conversation_id: int | None = None) -> NivaConversation:
    if conversation_id:
        conv = NivaConversation.objects.filter(id=conversation_id, user=user).first()
        if conv:
            return conv
    conv = (
        NivaConversation.objects.filter(user=user, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if conv:
        return conv
    return NivaConversation.objects.create(user=user, title="Niva chat")


def get_summary_text(conversation: NivaConversation) -> str:
    summary = getattr(conversation, "summary", None)
    if summary is None:
        try:
            summary = conversation.summary
        except NivaConversationSummary.DoesNotExist:
            return ""
    return (summary.summary or "").strip()


def maybe_update_summary(
    conversation: NivaConversation,
    *,
    message: str,
    reply: str,
    intent: str,
    history: list | None = None,
) -> None:
    """Update rolling summary every few turns or on major intents."""
    hist_len = len(history or [])
    major = intent.startswith(("day.", "task.create", "learning.", "goal.", "memory.save"))
    if not major and hist_len and hist_len % 6 != 0:
        return

    topic = intent.replace(".", " ")
    snippet = f"User: {(message or '')[:180]} | Niva: {(reply or '')[:180]}"
    obj, _ = NivaConversationSummary.objects.get_or_create(conversation=conversation)
    prev = (obj.summary or "").strip()
    combined = f"{prev}\n{snippet}".strip() if prev else snippet
    # Keep summary bounded
    if len(combined) > 1800:
        combined = combined[-1800:]
    unresolved = list(obj.unresolved_items or [])
    if intent in ("day.plan", "task.create", "learning.plan") and message:
        unresolved = (unresolved + [message[:120]])[-8:]
    obj.summary = combined
    obj.current_topic = topic[:255]
    obj.unresolved_items = unresolved
    obj.save()
    conversation.save(update_fields=["updated_at"])
    try:
        from api.niva.services.rag.indexer import index_summary_document

        index_summary_document(obj, force_embed=True)
    except Exception:
        pass
