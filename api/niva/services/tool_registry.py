"""Niva tool registry — name, description, JSON schema for Gemini function calling."""

from __future__ import annotations

from typing import Any

# Each entry: handler key in TOOL_HANDLERS + Gemini-facing schema.
# Args are merged into intent["entities"] before the handler runs.

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "task_create",
        "description": "Create one or more tasks in Dayflow from the user message. Use when the user wants to add/remind a task.",
        "parameters": {
            "type": "object",
            "properties": {
                "title_hint": {
                    "type": "string",
                    "description": "Optional short task title if clearly stated",
                },
            },
        },
        "intent": "task.create",
    },
    {
        "name": "task_list",
        "description": "List the user's open tasks / due today / overdue from the database.",
        "parameters": {"type": "object", "properties": {}},
        "intent": "task.list",
    },
    {
        "name": "task_complete",
        "description": "Mark a matching open task as done.",
        "parameters": {
            "type": "object",
            "properties": {
                "title_hint": {
                    "type": "string",
                    "description": "Title fragment of the task to complete",
                },
            },
        },
        "intent": "task.complete",
    },
    {
        "name": "habit_get_today",
        "description": "Show habit streaks / today's habit status.",
        "parameters": {"type": "object", "properties": {}},
        "intent": "habit.query",
    },
    {
        "name": "goal_get_active",
        "description": "Show active learning goals and progress.",
        "parameters": {"type": "object", "properties": {}},
        "intent": "goal.progress",
    },
    {
        "name": "memory_save",
        "description": "Save a fact or preference the user asked to remember.",
        "parameters": {"type": "object", "properties": {}},
        "intent": "memory.save",
    },
    {
        "name": "memory_search",
        "description": "Recall saved memories about the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up in memory"},
            },
        },
        "intent": "memory.recall",
    },
    {
        "name": "memory_archive",
        "description": "Forget / archive a memory the user wants removed.",
        "parameters": {"type": "object", "properties": {}},
        "intent": "memory.forget",
    },
    {
        "name": "web_search",
        "description": "Search the live web (Tavily) for current external facts. Not for personal Dayflow data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "English search query"},
            },
            "required": ["query"],
        },
        "intent": "research.web",
    },
    {
        "name": "news_search",
        "description": "Search recent news headlines via Tavily.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "News topic query"},
            },
        },
        "intent": "research.news",
    },
    {
        "name": "learning_create_plan",
        "description": "Create or refresh a learning roadmap for a skill/topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Skill or topic to learn"},
            },
        },
        "intent": "learning.plan",
    },
    {
        "name": "learning_get_progress",
        "description": "Show learning skill progress.",
        "parameters": {"type": "object", "properties": {}},
        "intent": "learning.progress",
    },
    {
        "name": "learning_generate_practice",
        "description": "Generate a practice question / quiz on a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
            },
        },
        "intent": "learning.practice",
    },
    {
        "name": "get_activity",
        "description": "What the user did in Dayflow for a period (tasks, transactions, habits, notes). Use for 'what did I do' / activity recall.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "today | yesterday | this_week | last_week | this_month",
                },
                "kind": {
                    "type": "string",
                    "description": "Optional filter: task | transaction | habit | note | goal",
                },
            },
        },
        "intent": "activity.recall",
    },
    {
        "name": "add_transaction",
        "description": "Log an expense or income into Dayflow finance. Only after amount is clear. Confirm only after DB write.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "amount": {"type": "number"},
                "type": {
                    "type": "string",
                    "enum": ["EXPENSE", "INCOME", "DEBT_PAYMENT", "TRANSFER"],
                },
                "category": {"type": "string"},
            },
            "required": ["amount"],
        },
        "intent": "finance.add",
    },
    {
        "name": "list_transactions",
        "description": "List recent transactions with optional period/category filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string"},
                "category": {"type": "string"},
                "tx_type": {"type": "string"},
            },
        },
        "intent": "finance.list",
    },
    {
        "name": "spending_summary",
        "description": "Exact spending totals from the database for a period, optionally by category. Never invent numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "today | yesterday | this_week | last_week | this_month | last_month",
                },
                "category": {"type": "string", "description": "e.g. FOOD, TRANSPORT"},
                "group_by": {"type": "string", "enum": ["category", "type"]},
            },
        },
        "intent": "finance.summary",
    },
    {
        "name": "compare_periods",
        "description": "Compare spending between two periods using DB aggregates.",
        "parameters": {
            "type": "object",
            "properties": {
                "period_a": {"type": "string"},
                "period_b": {"type": "string"},
            },
        },
        "intent": "finance.compare",
    },
    {
        "name": "top_expenses",
        "description": "Largest expenses in a period.",
        "parameters": {
            "type": "object",
            "properties": {"period": {"type": "string"}},
        },
        "intent": "finance.top",
    },
    {
        "name": "budget_status",
        "description": "Budget / income vs expense status for this month (no per-category limits yet).",
        "parameters": {
            "type": "object",
            "properties": {"category": {"type": "string"}},
        },
        "intent": "finance.budget",
    },
    {
        "name": "finance_insights",
        "description": "Rule-based spending insights (spikes, large one-offs, recurring).",
        "parameters": {"type": "object", "properties": {}},
        "intent": "finance.insights",
    },
    {
        "name": "users_list",
        "description": "List Dayflow users (superadmin only).",
        "parameters": {"type": "object", "properties": {}},
        "intent": "admin.users",
        "admin_only": True,
    },
    {
        "name": "system_internals",
        "description": "Explain how Niva is built / architecture (high level).",
        "parameters": {"type": "object", "properties": {}},
        "intent": "system.internals",
    },
    {
        "name": "doubt_explain",
        "description": (
            "Answer a conceptual doubt (what/why/how). Searches the web only when "
            "fresh/external info is needed. Cites sources and offers to save learning — never auto-saves."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "English form of the user's doubt",
                },
                "force_search": {
                    "type": "boolean",
                    "description": "True if user asked to search online or needs latest info",
                },
            },
            "required": ["query"],
        },
        "intent": "doubt.ask",
    },
    {
        "name": "save_doubt_learning",
        "description": (
            "Save the last doubt explanation to learning notes. Only when the user "
            "explicitly confirms (yes / save this). Never auto-save web results."
        ),
        "parameters": {"type": "object", "properties": {}},
        "intent": "doubt.save",
    },
]

TOOL_BY_NAME: dict[str, dict[str, Any]] = {s["name"]: s for s in TOOL_SPECS}

# Intents that skip Gemini FC (cheap + deterministic).
FAST_PATH_INTENTS = frozenset(
    {
        "profile.identity",
        "day.plan",
        "day.review",
        "companion.weekly",
        "companion.morning",
        "task.create",
        "task.complete",
        "finance.add",
        "memory.save",
        "memory.forget",
        "doubt.save",
        "admin.users",
        "system.internals",
    }
)

MAX_TOOL_STEPS = 4


def specs_for_user(user) -> list[dict[str, Any]]:
    from api.views import is_super_admin

    admin = False
    try:
        admin = bool(user and is_super_admin(user))
    except Exception:
        admin = False
    out = []
    for s in TOOL_SPECS:
        if s.get("admin_only") and not admin:
            continue
        out.append(s)
    return out


def gemini_tools_for_user(user):
    """Build google.generativeai Tool list for the user."""
    from google.generativeai.types import FunctionDeclaration, Tool

    decls = []
    for s in specs_for_user(user):
        decls.append(
            FunctionDeclaration(
                name=s["name"],
                description=s["description"],
                parameters=s.get("parameters") or {"type": "object", "properties": {}},
            )
        )
    return [Tool(function_declarations=decls)] if decls else []


def intent_for_tool(name: str) -> str:
    spec = TOOL_BY_NAME.get(name) or {}
    return str(spec.get("intent") or "chat.general")
