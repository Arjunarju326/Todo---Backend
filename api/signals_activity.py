"""Django signals → NivaActivityEvent (Phase 8)."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from api.models import Habit, LearningGoal, Note, Task, TaskStatus, Transaction
from api.niva.services.activity import record_event

# Cache previous state for update-kind detection
_TASK_BEFORE: dict[int, dict] = {}
_HABIT_BEFORE: dict[int, dict] = {}
_GOAL_BEFORE: dict[int, dict] = {}
_NOTE_BEFORE: dict[int, dict] = {}
_TX_BEFORE: dict[int, dict] = {}


@receiver(pre_save, sender=Task)
def task_pre_save(sender, instance: Task, **kwargs):
    if not instance.pk:
        return
    try:
        old = Task.objects.filter(pk=instance.pk).values("status", "title", "priority").first()
        if old:
            _TASK_BEFORE[instance.pk] = old
    except Exception:
        pass


@receiver(post_save, sender=Task)
def task_post_save(sender, instance: Task, created: bool, **kwargs):
    user = instance.user
    if created:
        record_event(
            user=user,
            kind="task.created",
            entity_type="task",
            entity_id=instance.id,
            summary=f"Created task “{instance.title}” ({instance.status}).",
            payload={"title": instance.title, "status": instance.status, "priority": instance.priority},
        )
        return
    old = _TASK_BEFORE.pop(instance.pk, None) or {}
    if old.get("status") != instance.status:
        if instance.status == TaskStatus.DONE:
            record_event(
                user=user,
                kind="task.completed",
                entity_type="task",
                entity_id=instance.id,
                summary=f"Completed task “{instance.title}”.",
                payload={"title": instance.title, "from": old.get("status"), "to": instance.status},
            )
        else:
            record_event(
                user=user,
                kind="task.updated",
                entity_type="task",
                entity_id=instance.id,
                summary=f"Updated task “{instance.title}” status to {instance.status}.",
                payload={"title": instance.title, "from": old.get("status"), "to": instance.status},
            )
    elif old.get("title") != instance.title or old.get("priority") != instance.priority:
        record_event(
            user=user,
            kind="task.updated",
            entity_type="task",
            entity_id=instance.id,
            summary=f"Updated task “{instance.title}”.",
            payload={"title": instance.title, "priority": instance.priority},
        )


@receiver(post_delete, sender=Task)
def task_post_delete(sender, instance: Task, **kwargs):
    record_event(
        user=instance.user,
        kind="task.deleted",
        entity_type="task",
        entity_id=instance.id,
        summary=f"Deleted task “{instance.title}”.",
        payload={"title": instance.title},
    )


@receiver(pre_save, sender=Transaction)
def transaction_pre_save(sender, instance: Transaction, **kwargs):
    if not instance.pk:
        return
    try:
        old = (
            Transaction.objects.filter(pk=instance.pk)
            .values("title", "type", "amount", "category")
            .first()
        )
        if old:
            _TX_BEFORE[instance.pk] = old
    except Exception:
        pass


@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance: Transaction, created: bool, **kwargs):
    user = instance.user
    amount = str(instance.amount)
    if created:
        record_event(
            user=user,
            kind="transaction.created",
            entity_type="transaction",
            entity_id=instance.id,
            summary=f"Logged {instance.type.lower()} “{instance.title}” ({amount}, {instance.category}).",
            payload={
                "title": instance.title,
                "type": instance.type,
                "amount": amount,
                "category": instance.category,
            },
        )
        return
    _TX_BEFORE.pop(instance.pk, None)
    record_event(
        user=user,
        kind="transaction.updated",
        entity_type="transaction",
        entity_id=instance.id,
        summary=f"Updated transaction “{instance.title}” ({amount}).",
        payload={
            "title": instance.title,
            "type": instance.type,
            "amount": amount,
            "category": instance.category,
        },
    )


@receiver(post_delete, sender=Transaction)
def transaction_post_delete(sender, instance: Transaction, **kwargs):
    record_event(
        user=instance.user,
        kind="transaction.deleted",
        entity_type="transaction",
        entity_id=instance.id,
        summary=f"Deleted transaction “{instance.title}”.",
        payload={"title": instance.title, "amount": str(instance.amount)},
    )


@receiver(pre_save, sender=Habit)
def habit_pre_save(sender, instance: Habit, **kwargs):
    if not instance.pk:
        return
    try:
        old = (
            Habit.objects.filter(pk=instance.pk)
            .values("name", "streak", "completed_dates")
            .first()
        )
        if old:
            _HABIT_BEFORE[instance.pk] = old
    except Exception:
        pass


@receiver(post_save, sender=Habit)
def habit_post_save(sender, instance: Habit, created: bool, **kwargs):
    user = instance.user
    if created:
        record_event(
            user=user,
            kind="habit.created",
            entity_type="habit",
            entity_id=instance.id,
            summary=f"Created habit “{instance.name}”.",
            payload={"name": instance.name},
        )
        return
    old = _HABIT_BEFORE.pop(instance.pk, None) or {}
    old_dates = old.get("completed_dates") or []
    new_dates = instance.completed_dates or []
    if len(new_dates) > len(old_dates):
        record_event(
            user=user,
            kind="habit.logged",
            entity_type="habit",
            entity_id=instance.id,
            summary=f"Logged habit “{instance.name}” (streak {instance.streak}).",
            payload={"name": instance.name, "streak": instance.streak},
        )
    elif old.get("name") != instance.name or old.get("streak") != instance.streak:
        record_event(
            user=user,
            kind="habit.updated",
            entity_type="habit",
            entity_id=instance.id,
            summary=f"Updated habit “{instance.name}” (streak {instance.streak}).",
            payload={"name": instance.name, "streak": instance.streak},
        )


@receiver(post_delete, sender=Habit)
def habit_post_delete(sender, instance: Habit, **kwargs):
    record_event(
        user=instance.user,
        kind="habit.deleted",
        entity_type="habit",
        entity_id=instance.id,
        summary=f"Deleted habit “{instance.name}”.",
        payload={"name": instance.name},
    )


@receiver(pre_save, sender=LearningGoal)
def goal_pre_save(sender, instance: LearningGoal, **kwargs):
    if not instance.pk:
        return
    try:
        old = (
            LearningGoal.objects.filter(pk=instance.pk)
            .values("title", "status", "progress_percentage")
            .first()
        )
        if old:
            _GOAL_BEFORE[instance.pk] = old
    except Exception:
        pass


@receiver(post_save, sender=LearningGoal)
def goal_post_save(sender, instance: LearningGoal, created: bool, **kwargs):
    user = instance.user
    if created:
        record_event(
            user=user,
            kind="goal.created",
            entity_type="goal",
            entity_id=instance.id,
            summary=f"Created goal “{instance.title}”.",
            payload={"title": instance.title, "status": instance.status},
        )
        return
    old = _GOAL_BEFORE.pop(instance.pk, None) or {}
    record_event(
        user=user,
        kind="goal.updated",
        entity_type="goal",
        entity_id=instance.id,
        summary=(
            f"Updated goal “{instance.title}” "
            f"({instance.progress_percentage}% · {instance.status})."
        ),
        payload={
            "title": instance.title,
            "status": instance.status,
            "progress": instance.progress_percentage,
            "from_progress": old.get("progress_percentage"),
        },
    )


@receiver(post_delete, sender=LearningGoal)
def goal_post_delete(sender, instance: LearningGoal, **kwargs):
    record_event(
        user=instance.user,
        kind="goal.deleted",
        entity_type="goal",
        entity_id=instance.id,
        summary=f"Deleted goal “{instance.title}”.",
        payload={"title": instance.title},
    )


@receiver(pre_save, sender=Note)
def note_pre_save(sender, instance: Note, **kwargs):
    if not instance.pk:
        return
    try:
        old = Note.objects.filter(pk=instance.pk).values("title", "category").first()
        if old:
            _NOTE_BEFORE[instance.pk] = old
    except Exception:
        pass


@receiver(post_save, sender=Note)
def note_post_save(sender, instance: Note, created: bool, **kwargs):
    user = instance.user
    if created:
        record_event(
            user=user,
            kind="note.created",
            entity_type="note",
            entity_id=instance.id,
            summary=f"Created note “{instance.title}”.",
            payload={"title": instance.title, "category": instance.category},
        )
    else:
        _NOTE_BEFORE.pop(instance.pk, None)
        record_event(
            user=user,
            kind="note.updated",
            entity_type="note",
            entity_id=instance.id,
            summary=f"Updated note “{instance.title}”.",
            payload={"title": instance.title, "category": instance.category},
        )
    try:
        from api.niva.services.rag.indexer import index_note_document

        index_note_document(instance, force_embed=True)
    except Exception:
        pass


@receiver(post_delete, sender=Note)
def note_post_delete(sender, instance: Note, **kwargs):
    record_event(
        user=instance.user,
        kind="note.deleted",
        entity_type="note",
        entity_id=instance.id,
        summary=f"Deleted note “{instance.title}”.",
        payload={"title": instance.title},
    )
    try:
        from api.models import AssistantChunk, AssistantSourceType

        AssistantChunk.objects.filter(
            user=instance.user,
            source_type__in=[AssistantSourceType.NOTE, AssistantSourceType.JOURNAL],
            source_id__startswith=str(instance.id),
        ).delete()
        AssistantChunk.objects.filter(
            user=instance.user,
            source_type__in=[AssistantSourceType.NOTE, AssistantSourceType.JOURNAL],
            source_id=str(instance.id),
        ).delete()
    except Exception:
        pass
