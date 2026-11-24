"""Load / seed the niva-intel-lab-100@1.0 suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUITE_SLUG = "niva-intel-lab-100"
SUITE_VERSION = "1.0"
SUITE_NAME = "Niva Intelligence Lab 100"


def _s(
    sid: str,
    category: str,
    text: str,
    *,
    intent: str | None = None,
    intent_any: list[str] | None = None,
    tools: list[str] | None = None,
    tools_include: list[str] | None = None,
    tools_any_of: list[str] | None = None,
    tools_exclude: list[str] | None = None,
    title: str = "",
    history: list | None = None,
    fixtures: dict | None = None,
    weight: float = 1.0,
    tags: list | None = None,
    **expect_extra: Any,
) -> dict[str, Any]:
    expect: dict[str, Any] = dict(expect_extra)
    if intent is not None:
        expect["intent"] = intent
    if intent_any is not None:
        expect["intent_any"] = intent_any
    if tools is not None:
        expect["tools"] = tools
    if tools_include is not None:
        expect["tools_include"] = tools_include
    if tools_any_of is not None:
        expect["tools_any_of"] = tools_any_of
    if tools_exclude is not None:
        expect["tools_exclude"] = tools_exclude
    return {
        "id": sid,
        "category": category,
        "title": title or sid,
        "input": text,
        "history": history or [],
        "fixtures": fixtures or {},
        "expect": expect,
        "weight": weight,
        "tags": tags or [],
    }


def build_default_scenarios() -> list[dict[str, Any]]:
    """Exactly 100 scenarios covering Sprint 1 categories."""
    out: list[dict[str, Any]] = []

    # A — Intent routing (20)
    intent_cases = [
        ("A01", "add a task to finish Jenkins setup", "task.create", ["task_create"]),
        ("A02", "create a new task for grocery shopping", "task.create", ["task_create"]),
        ("A03", "remind me to call mom tomorrow", "task.create", ["task_create"]),
        ("A04", "what are my tasks today", "task.list", ["task_list"]),
        ("A05", "show overdue tasks", "task.list", ["task_list"]),
        ("A06", "mark the jenkins task done", "task.complete", ["task_complete"]),
        ("A07", "plan my day", "day.plan", None),
        ("A08", "I only have 30 minutes", "day.plan", None),
        ("A09", "review my day", "day.review", None),
        ("A10", "I want to learn RAG properly", "learning.plan", ["learning_create_plan"]),
        ("A11", "give me a quiz on transformers", "learning.practice", ["learning_generate_practice"]),
        ("A12", "what is my learning progress", "learning.progress", ["learning_get_progress"]),
        ("A13", "explain attention mechanism", "learning.explain", []),
        ("A14", "latest tech news", "research.news", ["news_search"]),
        ("A15", "search online for Django 5 release", "research.web", ["web_search"]),
        ("A16", "remember this: I prefer short replies", "memory.save", ["memory_save"]),
        ("A17", "do you remember where I work", "memory.recall", ["memory_search"]),
        ("A18", "who am i", "profile.identity", []),
        ("A19", "what can you do", "system.help", []),
        ("A20", "my habits", "habit.query", ["habit_get_today"]),
    ]
    for sid, text, intent, tools in intent_cases:
        kwargs: dict[str, Any] = {"intent": intent, "critical_intent": True}
        if tools is not None:
            kwargs["tools"] = tools
        out.append(_s(sid, "intent", text, **kwargs))

    # B — Memory (20)
    memory_cases = [
        ("B01", "remember this: my preferred name is Arjuoo", "memory.save", ["memory_save"]),
        ("B02", "keep this in mind I work at IBM", "memory.save", ["memory_save"]),
        ("B03", "don't forget I live in Kochi", "memory.save", ["memory_save"]),
        ("B04", "ormikkane call me Arjun", "memory.save", ["memory_save"]),
        ("B05", "save this in memory: quiet hours after 10pm", "memory.save", ["memory_save"]),
        ("B06", "forget that about my old nickname", "memory.forget", ["memory_archive"]),
        ("B07", "delete memory of temporary internship", "memory.forget", ["memory_archive"]),
        ("B08", "what did I tell you about work", "memory.recall", ["memory_search"]),
        ("B09", "where do I live", "memory.recall", ["memory_search"]),
        ("B10", "who am i?", "profile.identity", [], {
            "max_sentences": 3,
            "forbid_substrings": ["AssistantMemory", "episodic dump", "memory bank"],
            "memory_hygiene": True,
            "forbid_critical": True,
        }),
        ("B11", "who i am", "profile.identity", [], {"max_sentences": 3, "memory_hygiene": True}),
        ("B12", "what's my preferred name", "memory.recall", ["memory_search"]),
        ("B13", "do you remember my goals", "memory.recall", ["memory_search"]),
        ("B14", "what do you know about me", "memory.recall", ["memory_search"]),
        ("B15", "remember that RAG project is my active goal", "memory.save", ["memory_save"]),
        ("B16", "keep in mind I hate long motivational speeches", "memory.save", ["memory_save"]),
        ("B17", "forget this temporary note xyz", "memory.forget", ["memory_archive"]),
        ("B18", "hello", "chat.general", [], {"expect_no_mutation": True}),
        ("B19", "thanks", "chat.general", [], {"expect_no_mutation": True}),
        ("B20", "njan aaranu", "profile.identity", [], {"memory_hygiene": True}),
    ]
    for item in memory_cases:
        sid, text, intent, tools = item[0], item[1], item[2], item[3]
        extra = item[4] if len(item) > 4 else {}
        out.append(_s(sid, "memory", text, intent=intent, tools=tools, **extra))

    # C — Tools (20)
    tool_cases = [
        ("C01", "add a task to write unit tests", "task.create", ["task_create"], True),
        ("C02", "create task: review PR #42", "task.create", ["task_create"], True),
        ("C03", "new task prepare slides", "task.create", ["task_create"], True),
        ("C04", "make a task for dentist appointment", "task.create", ["task_create"], True),
        ("C05", "list my tasks", "task.list", ["task_list"], True),
        ("C06", "any tasks due today", "task.list", ["task_list"], True),
        ("C07", "task list please", "task.list", ["task_list"], True),
        ("C08", "finish the task about slides", "task.complete", ["task_complete"], True),
        ("C09", "mark grocery task completed", "task.complete", ["task_complete"], True),
        ("C10", "my goals", "goal.progress", ["goal_get_active"], False),
        ("C11", "goal progress", "goal.progress", ["goal_get_active"], False),
        ("C12", "habit streak", "habit.query", ["habit_get_today"], False),
        ("C13", "did I complete my habit", "habit.query", ["habit_get_today"], False),
        ("C14", "add tasks for laundry and bills", "task.create", ["task_create"], True),
        ("C15", "remind me to stretch at 5pm", "task.create", ["task_create"], True),
        ("C16", "what should I have to do", "task.list", ["task_list"], False),
        ("C17", "overdue", "task.list", ["task_list"], False),
        ("C18", "mark finished the learning task", "task.complete", ["task_complete"], True),
        ("C19", "create a task titled backlog cleanup", "task.create", ["task_create"], True),
        ("C20", "show my open tasks", "task.list", ["task_list"], False),
    ]
    for sid, text, intent, tools, crit in tool_cases:
        out.append(
            _s(
                sid,
                "tools",
                text,
                intent=intent,
                tools=tools,
                critical_tools=crit,
                critical_intent=True,
            )
        )

    # D — Planning / companion (15)
    plan_cases = [
        ("D01", "plan my day", "day.plan"),
        ("D02", "schedule my day", "day.plan"),
        ("D03", "what should I focus on today", "day.plan"),
        ("D04", "what should I do now", "recommendation"),
        ("D05", "I only have 15 minutes", "day.plan"),
        ("D06", "I only have 2 hours", "day.plan"),
        ("D07", "plan my week", "day.plan"),
        ("D08", "evening review", "day.review"),
        ("D09", "how did my day go", "day.review"),
        ("D10", "how did I do today", "day.review"),
        ("D11", "recommend something productive", "recommendation"),
        ("D12", "suggest what to focus on", "recommendation"),
        ("D13", "hi niva", "chat.general"),
        ("D14", "just chatting, no tasks please", "chat.general"),
        ("D15", "good morning", "chat.general"),
    ]
    for sid, text, intent in plan_cases:
        extra: dict[str, Any] = {"intent": intent}
        if intent == "chat.general":
            extra["expect_no_mutation"] = True
            extra["tools"] = []
        out.append(_s(sid, "planning", text, **extra))

    # E — Learning (10)
    learn_cases = [
        ("E01", "I want to learn system design", "learning.plan", ["learning_create_plan"]),
        ("E02", "learning roadmap for python", "learning.plan", ["learning_create_plan"]),
        ("E03", "teach me a path for ML interview", "learning.plan", ["learning_create_plan"]),
        ("E04", "practice question on RAG", "learning.practice", ["learning_generate_practice"]),
        ("E05", "test me on embeddings", "learning.practice", ["learning_generate_practice"]),
        ("E06", "give me a quiz", "learning.practice", ["learning_generate_practice"]),
        ("E07", "my skills", "learning.progress", ["learning_get_progress"]),
        ("E08", "what have I learned", "learning.progress", ["learning_get_progress"]),
        ("E09", "learning progress", "learning.progress", ["learning_get_progress"]),
        ("E10", "how does vector search work", "learning.explain", []),
    ]
    for sid, text, intent, tools in learn_cases:
        out.append(_s(sid, "learning", text, intent=intent, tools=tools))

    # F — Research (10)
    research_cases = [
        ("F01", "tech news", "research.news", ["news_search"], False),
        ("F02", "today's news", "research.news", ["news_search"], False),
        ("F03", "breaking news in AI", "research.news", ["news_search"], False),
        ("F04", "google the latest Next.js version", "research.web", ["web_search"], False),
        ("F05", "look up Tavily API pricing", "research.web", ["web_search"], False),
        ("F06", "search the web for pgvector tips", "research.web", ["web_search"], False),
        ("F07", "check online for Gemini rate limits", "research.web", ["web_search"], False),
        ("F08", "who am i", "profile.identity", [], True),  # must not search
        ("F09", "what are my tasks", "task.list", ["task_list"], True),
        ("F10", "headlines", "research.news", ["news_search"], False),
    ]
    for sid, text, intent, tools, forbid_search in research_cases:
        kw: dict[str, Any] = {"intent": intent}
        if tools:
            kw["tools"] = tools
        else:
            kw["tools"] = []
        if forbid_search:
            kw["forbid_search_tools"] = True
            kw["tools_exclude"] = ["web_search", "news_search"]
        out.append(_s(sid, "research", text, **kw))

    # G — Conversation quality (5)
    conv_cases = [
        ("G01", "who am i?", "profile.identity", {
            "max_sentences": 3,
            "memory_hygiene": True,
            "forbid_substrings": ["JSON", "dump"],
        }),
        ("G02", "yes", "learning.explain", {
            "history": [
                {"role": "assistant", "content": "Want help on how to do that Jenkins task?"},
                {"role": "user", "content": "yes"},
            ],
        }),
        ("G03", "ok help me", "learning.explain", {
            "history": [
                {"role": "assistant", "content": "Want help on how to do that?"},
            ],
        }),
        ("G04", "hello there", "chat.general", {"expect_no_mutation": True, "tools": []}),
        ("G05", "what should I focus on now", "recommendation", {}),
    ]
    for sid, text, intent, extra in conv_cases:
        hist = extra.pop("history", None)
        out.append(
            _s(sid, "conversation", text, intent=intent, history=hist, **extra)
        )

    assert len(out) == 100, f"expected 100 scenarios, got {len(out)}"
    return out


def scenarios_json_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "lab" / "scenarios" / "intel_lab_100.json"


def load_scenario_dicts() -> list[dict[str, Any]]:
    path = scenarios_json_path()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios = data.get("scenarios") or data
        if isinstance(scenarios, list) and len(scenarios) >= 50:
            return scenarios
    return build_default_scenarios()


def write_scenarios_json() -> Path:
    path = scenarios_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "suite": SUITE_SLUG,
        "version": SUITE_VERSION,
        "name": SUITE_NAME,
        "scenarios": build_default_scenarios(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
