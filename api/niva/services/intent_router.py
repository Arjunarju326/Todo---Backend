"""Intent detection for Niva v2 — structured, internal only."""

from __future__ import annotations

import re
from typing import Any


INTENT_PATTERNS: list[tuple[str, tuple[str, ...], float]] = [
    ("profile.identity", (r"\bwho am i\b", r"\bwho i am\b", r"\bnjan aaranu\b"), 0.98),
    ("memory.forget", (r"\bforget (that|this|about|my)\b", r"\bdelete memory\b"), 0.95),
    (
        "memory.save",
        (
            r"\bremember (this|that)\b",
            r"\bkeep (this |that )?in mind\b",
            r"\bdon'?t forget\b",
            r"\bormikkane\b",
            r"\bsave (this )?in (your )?memory\b",
        ),
        0.96,
    ),
    (
        "memory.recall",
        (
            r"\bdo you remember\b",
            r"\bwhat did i tell\b",
            r"\bwhat do you (know|remember)\b",
            r"\bwhere (am i|do i) work\b",
            r"\bwhere (am i|do i) live\b",
            r"\bwhat('s| is|s) my\b",
        ),
        0.9,
    ),
    (
        "task.create",
        (
            r"\badd\b.{0,48}\btasks?\b",
            r"\bcreate\b.{0,40}\btasks?\b",
            r"\bnew\s+tasks?\b",
            r"\bmake\b.{0,30}\btasks?\b",
            r"\bremind me\b",
        ),
        0.94,
    ),
    (
        "task.complete",
        (r"\bmark .{0,40}\b(done|complete|completed)\b", r"\bfinish(ed)? (the |my )?task\b"),
        0.9,
    ),
    (
        "task.list",
        (
            r"\b(my |any |today'?s? )?tasks?\b",
            r"\bdue today\b",
            r"\bwhat (do i|should i) (have|do)\b",
            r"\boverdue\b",
            r"\btask list\b",
        ),
        0.88,
    ),
    (
        "day.plan",
        (
            r"\bplan my (day|week)\b",
            r"\bschedule my day\b",
            r"\bwhat should i (focus on|do) (now|today)\b",
            r"\bi only have \d+\s*(min|minutes|hour|hours)\b",
        ),
        0.92,
    ),
    ("day.review", (r"\breview (my )?day\b", r"\bevening review\b", r"\bhow did (i|my day) (do|go)\b"), 0.9),
    (
        "companion.weekly",
        (
            r"\bweekly review\b",
            r"\breview (my )?week\b",
            r"\bhow (was|did) (my )?week\b",
            r"\bweek(ly)? summary\b",
        ),
        0.93,
    ),
    (
        "companion.morning",
        (r"\bmorning (brief|briefing|check[- ]?in)\b", r"\bgood morning\b.{0,20}\bplan\b"),
        0.88,
    ),
    (
        "activity.recall",
        (
            r"\bwhat did i do\b",
            r"\bwhat have i done\b",
            r"\bmy (activity|activities)\b",
            r"\bactivity (log|timeline|today|yesterday)\b",
            r"\benthokke cheyth",
            r"\bnjan enthokke\b",
            r"\binnale .{0,40}\bcheyth",
            r"\bwhat (all )?happened (today|yesterday|this week)\b",
            r"\bshow (my )?(recent )?activity\b",
        ),
        0.93,
    ),
    (
        "finance.add",
        (
            r"\badd (an? )?(expense|income|transaction)\b",
            r"\blog (an? )?(expense|income|transaction|spend)\b",
            r"\brecord (an? )?(expense|income|spend)\b",
            r"\badd expense\b",
            r"\badd income\b",
            r"\bspent \d+",
            r"\bchilavu (add|log|ayi)\b",
        ),
        0.95,
    ),
    (
        "finance.compare",
        (
            r"\bcompare .{0,40}\b(month|week|spending|expense)",
            r"\b(vs|versus|compared to) (last|this) (month|week)\b",
            r"\bspending (up|down) (vs|versus|from)\b",
        ),
        0.92,
    ),
    (
        "finance.top",
        (
            r"\btop (expenses?|spending|purchases?)\b",
            r"\bbiggest (expenses?|purchases?|spends?)\b",
            r"\blargest (expenses?|transactions?)\b",
        ),
        0.92,
    ),
    (
        "finance.budget",
        (
            r"\bbudget (status|check|left|remaining)\b",
            r"\bam i over budget\b",
            r"\bhow('?s| is) my budget\b",
            r"\bincome vs (expense|spend)",
        ),
        0.9,
    ),
    (
        "finance.insights",
        (
            r"\b(finance|money|spending) insights?\b",
            r"\bany (spending|money) (alerts?|warnings?|flags?)\b",
            r"\bspending patterns?\b",
        ),
        0.9,
    ),
    (
        "finance.list",
        (
            r"\b(list|show) (my )?(transactions?|expenses?|spending)\b",
            r"\brecent (transactions?|expenses?)\b",
            r"\bmy (transactions?|expenses?) (this|last|today)",
        ),
        0.9,
    ),
    (
        "finance.summary",
        (
            r"\bhow much (did i|have i) spend",
            r"\bhow much .{0,30}\b(spend|spent|spending|chilavu)",
            r"\b(my )?spending (this|last|today|summary)",
            r"\bspending summary\b",
            r"\btotal (expenses?|spending|chilavu)\b",
            r"\bethra chilav",
            r"\bchilavu .{0,40}\bethra\b",
            r"\bee maasam .{0,40}\b(chilavu|ethra)",
            r"\b(food|rent|transport).{0,20}\b(spend|spent|chilavu|ethra)",
            r"\bwhat did i spend\b",
        ),
        0.94,
    ),
    (
        "learning.plan",
        (r"\blearning (plan|roadmap|path)\b", r"\bi want to learn\b", r"\bteach me a path\b"),
        0.9,
    ),
    (
        "learning.practice",
        (r"\bpractice (question|quiz|exercise)\b", r"\bgive me (a )?quiz\b", r"\btest me on\b"),
        0.9,
    ),
    (
        "learning.progress",
        (r"\blearning progress\b", r"\bmy skill(s)?\b", r"\bwhat have i learned\b"),
        0.88,
    ),
    (
        "health.guidance",
        (
            r"\bheadache\b",
            r"\bmigraine\b",
            r"\bfever\b",
            r"\bcough\b",
            r"\bsore throat\b",
            r"\bstomach (ache|pain|upset)\b",
            r"\bnausea\b",
            r"\bvomit",
            r"\bdiarrh",
            r"\bdizzy\b",
            r"\bdizziness\b",
            r"\bbody pain\b",
            r"\bback pain\b",
            r"\bchest pain\b",
            r"\beye strain\b",
            r"\binsomnia\b",
            r"\bcan'?t sleep\b",
            r"\bcannot sleep\b",
            r"\b(i('m| am)|feeling) (sick|ill|unwell)\b",
            r"\bi (have|got|feel).{0,40}\b(pain|ache|fever|cold)\b",
            r"\b(medicine|medication|tablet|paracetamol|dolo|ors)\b",
            r"\bshould i see (a )?doctor\b",
            r"\bhealth (tip|advice|help)\b",
        ),
        0.93,
    ),
    (
        "doubt.save",
        (
            r"\bsave (this |that )?(to )?(my )?(learning|notes?)\b",
            r"\byes[,.]? (save|remember) (it|this|that)\b",
            r"\bsave (it|this|that)\b",
            r"^yes\b.{0,20}\bsave\b",
        ),
        0.96,
    ),
    (
        "doubt.ask",
        (
            r"\bwhat is\b",
            r"\bwhat'?s\b",
            r"\bwhy (does|do|is|are|did)\b",
            r"\bhow (do|does|to|can)\b",
            r"\bexplain\b",
            r"\bteach me\b",
            r"\bdifference between\b",
            r"\benthaanu\b",
            r"\benthaa\b",
            r"\bi('?m| am) (confused|doubtful) (about|on)\b",
            r"\bi have (a )?doubt\b",
        ),
        0.91,
    ),
    (
        "learning.explain",
        (r"\bhow does .{0,40} work\b",),
        0.7,
    ),
    (
        "research.news",
        (r"\b(latest |today'?s? |breaking )?news\b", r"\bheadlines\b", r"\btech news\b"),
        0.93,
    ),
    (
        "research.web",
        (
            r"\bgoogle\b",
            r"\bsearch (online|the web|for)\b",
            r"\blook( it)? up\b",
            r"\blatest (version|update|release)\b",
            r"\bcheck online\b",
            r"\bfrom the web\b",
        ),
        0.92,
    ),
    (
        "habit.query",
        (r"\bmy habits?\b", r"\bhabit streak\b", r"\bdid i (do|complete) my habit\b"),
        0.88,
    ),
    ("goal.progress", (r"\bmy goals?\b", r"\bgoal progress\b", r"\bactive goals?\b", r"\bgoals? progress\b"), 0.85),
    ("recommendation", (r"\bwhat should i (do|focus on) now\b", r"\brecommend\b", r"\bsuggest\b"), 0.8),
    ("system.help", (r"\bwhat can you do\b", r"\bhelp me\b.*\bniva\b", r"\byour capabilities\b"), 0.85),
    (
        "admin.users",
        (
            r"\blist (all )?users?\b",
            r"\bshow (all )?users?\b",
            r"\b(all )?dayflow users?\b",
            r"\bwho (all )?signed up\b",
            r"\buser list\b",
            r"\bregistered users?\b",
            r"\bhow many users?\b",
        ),
        0.96,
    ),
    (
        "system.internals",
        (
            r"\bhow (are|r) you (built|made|designed)\b",
            r"\bhow (do|does) (you|niva) work\b",
            r"\bhow (is|was) (niva|you) (built|made|implemented)\b",
            r"\byour (architecture|internals|pipeline|orchestrator)\b",
            r"\b(niva|your) (tech|technical) (stack|architecture|design)\b",
            r"\bwhat (model|llm|api) (do you|are you) (use|using)\b",
            r"\bexplain (your|niva('s)?) (architecture|system|pipeline)\b",
            r"\bhow (is|are) (you|niva) (implemented|coded)\b",
        ),
        0.95,
    ),
]


def route_intent(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    force_create_task: bool = False,
) -> dict[str, Any]:
    text = (message or "").strip()
    lower = text.lower()
    lower = re.sub(r"\bnewtask\b", "new task", lower)
    lower = re.sub(r"\s+", " ", lower)

    if force_create_task:
        return {
            "primary_intent": "task.create",
            "secondary_intents": [],
            "confidence": 1.0,
            "entities": {},
            "tools_required": ["task_create"],
            "memory_categories": [],
            "requires_confirmation": False,
            "response_mode": "ACTION",
        }

    # Affirmation after help offer → treat as learning/task help chat
    if history and _accepts_help(lower, history):
        return {
            "primary_intent": "learning.explain",
            "secondary_intents": ["task.list"],
            "confidence": 0.86,
            "entities": {"help_followup": True},
            "tools_required": [],
            "memory_categories": ["active_context"],
            "requires_confirmation": False,
            "response_mode": "EXPLAIN",
        }

    best_intent = "chat.general"
    best_score = 0.4
    for intent, patterns, base in INTENT_PATTERNS:
        for pat in patterns:
            if re.search(pat, lower):
                # Prefer more specific intents over broad "what is"
                score = base
                if intent == "learning.explain" and re.search(
                    r"\b(latest|news|google|search online|version)\b", lower
                ):
                    continue
                if intent == "doubt.ask" and re.search(
                    r"\b(what('?s| is|s) my|who am i|my (task|habit|spend|expense))\b",
                    lower,
                ):
                    continue
                if score > best_score:
                    best_score = score
                    best_intent = intent
                break

    tools = _tools_for(best_intent)
    mode = _mode_for(best_intent)
    entities = _extract_entities(lower, best_intent)

    return {
        "primary_intent": best_intent,
        "secondary_intents": [],
        "confidence": round(best_score, 2),
        "entities": entities,
        "tools_required": tools,
        "memory_categories": _memory_cats(best_intent),
        "requires_confirmation": best_intent in ("task.delete",) or False,
        "response_mode": mode,
    }


def _accepts_help(lower: str, history: list[dict[str, str]]) -> bool:
    for turn in reversed(history or []):
        if (turn.get("role") or "").lower() != "assistant":
            continue
        content = (turn.get("content") or "").lower()
        if re.search(r"want help|help on how to do|how to do that", content):
            if re.search(
                r"^(yes|ys|yeah|yep|sure|ok|okay)\b|need (your |you )?help|help me\b",
                lower,
            ):
                return True
        break
    return False


def _tools_for(intent: str) -> list[str]:
    mapping = {
        "task.create": ["task_create"],
        "task.list": ["task_list"],
        "task.complete": ["task_complete"],
        "task.update": ["task_update"],
        "habit.query": ["habit_get_today"],
        "goal.progress": ["goal_get_active"],
        "day.plan": ["task_list", "habit_get_today", "goal_get_active"],
        "day.review": ["task_list"],
        "companion.weekly": [],
        "companion.morning": [],
        "activity.recall": ["get_activity"],
        "finance.add": ["add_transaction"],
        "finance.summary": ["spending_summary"],
        "finance.list": ["list_transactions"],
        "finance.compare": ["compare_periods"],
        "finance.top": ["top_expenses"],
        "finance.budget": ["budget_status"],
        "finance.insights": ["finance_insights"],
        "doubt.ask": ["doubt_explain"],
        "doubt.save": ["save_doubt_learning"],
        "learning.explain": ["doubt_explain"],
        "research.web": ["web_search"],
        "research.news": ["news_search"],
        "memory.save": ["memory_save"],
        "memory.forget": ["memory_archive"],
        "memory.recall": ["memory_search"],
        "learning.plan": ["learning_create_plan"],
        "learning.progress": ["learning_get_progress"],
        "learning.practice": ["learning_generate_practice"],
        "admin.users": ["users_list"],
        "system.internals": ["system_internals"],
    }
    return mapping.get(intent, [])


def _mode_for(intent: str) -> str:
    mapping = {
        "chat.general": "CHAT",
        "profile.identity": "ANSWER",
        "memory.recall": "MEMORY",
        "memory.save": "MEMORY",
        "task.create": "ACTION",
        "task.list": "ANSWER",
        "task.complete": "ACTION",
        "day.plan": "PLAN",
        "day.review": "REVIEW",
        "companion.weekly": "REVIEW",
        "companion.morning": "ANSWER",
        "activity.recall": "ANSWER",
        "finance.add": "ACTION",
        "finance.summary": "ANSWER",
        "finance.list": "ANSWER",
        "finance.compare": "ANSWER",
        "finance.top": "ANSWER",
        "finance.budget": "ANSWER",
        "finance.insights": "ANSWER",
        "doubt.ask": "EXPLAIN",
        "doubt.save": "ACTION",
        "learning.explain": "EXPLAIN",
        "learning.plan": "LEARNING",
        "learning.practice": "LEARNING",
        "learning.progress": "LEARNING",
        "health.guidance": "HEALTH",
        "research.web": "RESEARCH",
        "research.news": "RESEARCH",
        "recommendation": "ANSWER",
        "admin.users": "ADMIN",
        "system.internals": "ADMIN",
    }
    return mapping.get(intent, "CHAT")


def _memory_cats(intent: str) -> list[str]:
    if intent == "profile.identity":
        return ["profile"]
    if intent.startswith("learning"):
        return ["goal", "active_context", "preference"]
    if intent.startswith("day") or intent == "recommendation":
        return ["active_context", "routine", "preference"]
    if intent == "activity.recall":
        return ["active_context", "routine"]
    if intent.startswith("memory"):
        return ["profile", "goal", "active_context", "preference"]
    return []


def _extract_entities(lower: str, intent: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    m = re.search(r"only have (\d+)\s*(min|minutes|hour|hours)", lower)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        entities["available_minutes"] = n * 60 if "hour" in unit else n
    if intent == "task.create":
        entities["raw"] = lower
    if intent.startswith("research"):
        entities["query"] = lower
    if intent == "activity.recall":
        from api.niva.services.activity import parse_period_from_message

        entities["period"] = parse_period_from_message(lower)
        if re.search(r"\b(task|tasks)\b", lower):
            entities["kind"] = "task"
        elif re.search(r"\b(transaction|expense|spend|money|finance|chilavu)\b", lower):
            entities["kind"] = "transaction"
        elif re.search(r"\bhabits?\b", lower):
            entities["kind"] = "habit"
        elif re.search(r"\b(notes?|journal)\b", lower):
            entities["kind"] = "note"
        elif re.search(r"\bgoals?\b", lower):
            entities["kind"] = "goal"
    if intent.startswith("finance"):
        from api.niva.services.finance import (
            parse_add_transaction_draft,
            parse_category_from_message,
            parse_period_from_message as finance_period,
        )

        entities["period"] = finance_period(lower)
        cat = parse_category_from_message(lower)
        if cat:
            entities["category"] = cat
        if intent == "finance.add":
            draft = parse_add_transaction_draft(lower)
            if draft:
                entities["transaction_draft"] = draft
        if intent == "finance.compare":
            entities["period_a"] = "this_month"
            entities["period_b"] = "last_month"
            if "week" in lower:
                entities["period_a"] = "this_week"
                entities["period_b"] = "last_week"
    if intent in ("doubt.ask", "learning.explain"):
        from api.niva.services.doubt import needs_fresh_info

        entities["query"] = lower
        entities["needs_fresh"] = needs_fresh_info(lower)
        entities["force_search"] = bool(
            re.search(r"\b(search|google|look up|online|from the web)\b", lower)
        )
    m = re.search(r"learn(?:ing)?\s+(.+)$", lower)
    if m and intent.startswith("learning"):
        entities["topic"] = m.group(1).strip(" .!")[:120]
    return entities
