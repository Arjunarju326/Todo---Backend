from __future__ import annotations

from typing import Any

from django.utils import timezone

from api.models import NivaLearningSession, NivaSkillProgress


DEFAULT_ROADMAPS = {
    "rag": [
        "Embeddings and semantic similarity",
        "Chunking strategies",
        "Vector search",
        "Hybrid search",
        "Reranking",
        "Retrieval evaluation",
        "Hallucination reduction",
        "Tool-integrated RAG agents",
    ],
    "python": [
        "Core syntax and data structures",
        "Functions and modules",
        "OOP",
        "Debugging",
        "APIs and packaging",
        "Testing",
    ],
    "django": [
        "Models and ORM",
        "Views and URLs",
        "DRF serializers",
        "Authentication",
        "Permissions",
        "Performance",
    ],
    "ai": [
        "ML basics",
        "Model training and evaluation",
        "LLMs",
        "Prompting",
        "RAG",
        "Agents and tools",
    ],
}


def _pick_roadmap(topic: str) -> list[str]:
    t = (topic or "").lower()
    for key, path in DEFAULT_ROADMAPS.items():
        if key in t:
            return list(path)
    return [
        f"Foundations of {topic or 'the skill'}",
        "Core concepts",
        "Hands-on practice",
        "Mini project",
        "Review weak topics",
    ]


def learning_create_plan(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    topic = (intent.get("entities") or {}).get("topic") or ""
    if not topic:
        import re

        m = re.search(r"learn(?:ing)?\s+(.+)$", (message or "").lower())
        topic = (m.group(1) if m else message or "AI engineering").strip(" .!")[:120]
    skill_name = topic.split()[0][:80] if topic else "general"
    roadmap = _pick_roadmap(topic)
    skill, _ = NivaSkillProgress.objects.get_or_create(
        user=user,
        skill=skill_name.title(),
        defaults={
            "roadmap": roadmap,
            "target_level": "intermediate",
            "notes": topic,
        },
    )
    if not skill.roadmap:
        skill.roadmap = roadmap
        skill.save(update_fields=["roadmap", "updated_at"])
    lines = [f"{i+1}. {step}" for i, step in enumerate(skill.roadmap[:10])]
    return {
        "ok": True,
        "user_message": (
            f"Here’s a practical path for “{topic}”:\n"
            + "\n".join(lines)
            + "\nWe’ll track progress as you practice — not just when I explain."
        ),
        "response_type": "learning_plan",
        "data": {
            "skill_id": skill.id,
            "skill": skill.skill,
            "roadmap": skill.roadmap,
            "completed": skill.completed_topics,
            "weak": skill.weak_topics,
        },
        "actions": [{"type": "open_learning", "label": "View learning", "target_id": skill.id}],
    }


def learning_get_progress(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    skills = list(NivaSkillProgress.objects.filter(user=user).order_by("skill")[:20])
    if not skills:
        return {
            "ok": True,
            "user_message": "No skill profile yet. Say “I want to learn RAG” and I’ll build a path.",
            "response_type": "learning_progress",
            "data": {"skills": []},
        }
    lines = []
    for s in skills:
        done = len(s.completed_topics or [])
        total = max(1, len(s.roadmap or []))
        lines.append(
            f"• {s.skill}: {s.current_level} → {s.target_level} ({done}/{total} topics)"
        )
    return {
        "ok": True,
        "user_message": "Your learning progress:\n" + "\n".join(lines),
        "response_type": "learning_progress",
        "data": {
            "skills": [
                {
                    "id": s.id,
                    "skill": s.skill,
                    "level": s.current_level,
                    "completed": s.completed_topics,
                    "weak": s.weak_topics,
                    "roadmap": s.roadmap,
                }
                for s in skills
            ]
        },
    }


def learning_generate_practice(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    skill = NivaSkillProgress.objects.filter(user=user).order_by("-updated_at").first()
    topic = (skill.weak_topics or [None])[0] if skill else None
    if not topic and skill and skill.roadmap:
        done = set(skill.completed_topics or [])
        topic = next((t for t in skill.roadmap if t not in done), skill.roadmap[0])
    topic = topic or "Python basics"
    q = (
        f"Practice: Explain “{topic}” in your own words, then give one tiny code/example "
        f"you’d try in 10 minutes. Reply when done and I’ll mark progress."
    )
    return {
        "ok": True,
        "user_message": q,
        "response_type": "learning_plan",
        "data": {"topic": topic, "skill_id": skill.id if skill else None},
    }


def learning_record_session(*, user, message: str, intent: dict[str, Any], draft_task=None) -> dict[str, Any]:
    skill = NivaSkillProgress.objects.filter(user=user).order_by("-updated_at").first()
    topic = (intent.get("entities") or {}).get("topic") or "Practice session"
    session = NivaLearningSession.objects.create(
        user=user,
        skill=skill,
        topic=topic[:255],
        duration_minutes=25,
        notes=(message or "")[:1000],
    )
    if skill:
        completed = list(skill.completed_topics or [])
        if topic not in completed:
            completed.append(topic)
            skill.completed_topics = completed[-40:]
        skill.last_practice_at = timezone.now()
        skill.save(update_fields=["completed_topics", "last_practice_at", "updated_at"])
    return {
        "ok": True,
        "user_message": f"Logged a learning session on “{topic}”. Nice work — consistency beats cramming.",
        "response_type": "learning_progress",
        "data": {"session_id": session.id, "topic": topic},
    }
