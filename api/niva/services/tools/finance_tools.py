"""Verified finance tools — Django ORM aggregates; never invent totals."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from api.models import Transaction, TransactionType
from api.serializers import TransactionSerializer
from api.niva.services.finance import (
    budget_status as budget_status_fn,
    compare_periods as compare_periods_fn,
    format_summary_reply,
    get_currency,
    list_transactions as list_transactions_fn,
    money,
    parse_add_transaction_draft,
    parse_category_from_message,
    parse_period_from_message,
    rule_based_insights,
    spending_summary as spending_summary_fn,
    top_expenses as top_expenses_fn,
)


def add_transaction(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    draft = entities.get("transaction_draft")
    if not isinstance(draft, dict):
        draft = parse_add_transaction_draft(message)
    if not draft or draft.get("amount") is None:
        return {
            "ok": False,
            "user_message": (
                "I need an amount to log that. Try: “add expense 250 for lunch”."
            ),
            "response_type": "clarification",
        }

    title = (draft.get("title") or "Expense").strip()[:255]
    try:
        amount = float(draft["amount"])
    except (TypeError, ValueError):
        return {
            "ok": False,
            "user_message": "That amount doesn’t look valid. Nothing was saved.",
            "response_type": "error",
        }
    if amount <= 0:
        return {
            "ok": False,
            "user_message": "Amount must be greater than zero. Nothing was saved.",
            "response_type": "error",
        }

    t_type = (draft.get("type") or TransactionType.EXPENSE).upper()
    if t_type not in {c.value for c in TransactionType}:
        t_type = TransactionType.EXPENSE
    category = (draft.get("category") or "OTHER").upper()[:100]

    try:
        trans = Transaction.objects.create(
            user=user,
            title=title,
            type=t_type,
            amount=amount,
            category=category,
            date=timezone.now(),
            is_recurring=bool(draft.get("is_recurring") or draft.get("isRecurring")),
            notes=(draft.get("notes") or "")[:2000],
        )
    except Exception as exc:
        return {
            "ok": False,
            "user_message": (
                f"I couldn’t save that transaction. Nothing was changed. ({type(exc).__name__})"
            ),
            "response_type": "error",
        }

    # Verify from DB
    verified = Transaction.objects.filter(pk=trans.pk, user=user).first()
    if not verified:
        return {
            "ok": False,
            "user_message": "Save looked like it failed — I can’t confirm it in your ledger.",
            "response_type": "error",
        }

    cur = get_currency(user)
    data = TransactionSerializer(verified).data
    return {
        "ok": True,
        "user_message": (
            f"Done — logged {verified.type.lower()} “{verified.title}” "
            f"{money(verified.amount, cur)} ({verified.category})."
        ),
        "response_type": "finance_confirmation",
        "data": {"transaction": data},
        "actions": [
            {"type": "open_finance", "label": "View finance", "target_id": verified.id}
        ],
    }


def list_transactions(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    period = entities.get("period") or parse_period_from_message(message)
    category = entities.get("category") or parse_category_from_message(message)
    tx_type = entities.get("tx_type")
    result = list_transactions_fn(
        user, period=period, category=category, tx_type=tx_type, limit=15
    )
    cur = result["currency"]
    if not result["items"]:
        msg = f"No transactions found for {result['period']}."
        if category:
            msg = f"No {category} transactions for {result['period']}."
        return {
            "ok": True,
            "user_message": msg,
            "response_type": "finance_list",
            "data": result,
        }
    lines = [
        f"• {it['title']} — {money(it['amount'], cur)} ({it['type']}, {it['category']})"
        for it in result["items"][:10]
    ]
    head = f"{result['count']} transaction(s) for {result['period']}:"
    return {
        "ok": True,
        "user_message": head + "\n" + "\n".join(lines),
        "response_type": "finance_list",
        "data": result,
    }


def spending_summary(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    period = entities.get("period") or parse_period_from_message(message)
    category = entities.get("category") or parse_category_from_message(message)
    group_by = entities.get("group_by") or "category"
    summary = spending_summary_fn(
        user, period=period, group_by=group_by, category=category
    )
    return {
        "ok": True,
        "user_message": format_summary_reply(summary),
        "response_type": "finance_summary",
        "data": summary,
    }


def compare_periods(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    a = entities.get("period_a") or "this_month"
    b = entities.get("period_b") or "last_month"
    result = compare_periods_fn(user, period_a=a, period_b=b)
    cur = result["currency"]
    delta = result["expense_delta"]
    pct = result["expense_delta_pct"]
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    pct_bit = f" ({abs(pct):.0f}%)" if pct is not None else ""
    reply = (
        f"Expenses {result['a']['period']}: {money(result['a']['expense_total'], cur)}. "
        f"{result['b']['period'].capitalize()}: {money(result['b']['expense_total'], cur)}. "
        f"Change: {direction} {money(abs(delta), cur)}{pct_bit}."
    )
    return {
        "ok": True,
        "user_message": reply,
        "response_type": "finance_compare",
        "data": result,
    }


def top_expenses(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    period = entities.get("period") or parse_period_from_message(message)
    result = top_expenses_fn(user, period=period, limit=5)
    cur = result["currency"]
    if not result["items"]:
        return {
            "ok": True,
            "user_message": f"No expenses logged for {result['period']}.",
            "response_type": "finance_top",
            "data": result,
        }
    lines = [
        f"• {it['title']} — {money(it['amount'], cur)} ({it['category']})"
        for it in result["items"]
    ]
    return {
        "ok": True,
        "user_message": f"Top expenses for {result['period']}:\n" + "\n".join(lines),
        "response_type": "finance_top",
        "data": result,
    }


def budget_status(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    entities = intent.get("entities") or {}
    category = entities.get("category") or parse_category_from_message(message)
    result = budget_status_fn(user, category=category)
    cur = result["currency"]
    lines = [
        f"This month’s expenses: {money(result['month_expense_total'], cur)}."
    ]
    if result["monthly_income_setting"]:
        lines.append(
            f"Monthly income setting: {money(result['monthly_income_setting'], cur)}"
            + (
                f" ({result['pct_of_income']:.0f}% used)."
                if result.get("pct_of_income") is not None
                else "."
            )
        )
    elif result.get("month_income_logged"):
        lines.append(
            f"Income logged this month: {money(result['month_income_logged'], cur)}."
        )
    if result.get("category_note"):
        lines.append(result["category_note"])
    if result.get("warning"):
        lines.append(result["warning"])
    else:
        lines.append("No per-category budget limits are set yet — comparing against income.")
    return {
        "ok": True,
        "user_message": " ".join(lines),
        "response_type": "finance_budget",
        "data": result,
    }


def finance_insights(
    *,
    user,
    message: str,
    intent: dict[str, Any],
    draft_task=None,
) -> dict[str, Any]:
    result = rule_based_insights(user)
    insights = result.get("insights") or []
    if not insights:
        return {
            "ok": True,
            "user_message": "No notable finance insights yet — keep logging expenses and I’ll flag patterns.",
            "response_type": "finance_insights",
            "data": result,
        }
    lines = [f"• {i['message']}" for i in insights[:6]]
    return {
        "ok": True,
        "user_message": "Finance insights:\n" + "\n".join(lines),
        "response_type": "finance_insights",
        "data": result,
    }
