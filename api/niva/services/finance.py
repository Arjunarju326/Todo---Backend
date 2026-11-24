"""Finance helpers — DB aggregation only; LLM never computes totals."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone

from api.models import Transaction, TransactionType, UserSettings

EXPENSE_TYPES = (TransactionType.EXPENSE, TransactionType.DEBT_PAYMENT)


def get_currency(user) -> str:
    try:
        s = UserSettings.objects.filter(user=user).first()
        if s and s.currency:
            return s.currency
    except Exception:
        pass
    return "₹"


def get_monthly_income_setting(user) -> Decimal:
    try:
        s = UserSettings.objects.filter(user=user).first()
        if s and s.monthly_income is not None:
            return Decimal(s.monthly_income)
    except Exception:
        pass
    return Decimal("0")


def money(amount: Decimal | float | int | None, currency: str = "₹") -> str:
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        n = 0.0
    # Indian-style grouping via format then strip .00 when whole
    formatted = f"{n:,.2f}"
    if formatted.endswith(".00"):
        formatted = formatted[:-3]
    return f"{currency}{formatted}"


def period_bounds(period: str, *, now=None) -> tuple[datetime, datetime, str]:
    now = now or timezone.localtime()
    today = now.date()
    period = (period or "this_month").strip().lower().replace(" ", "_").replace("-", "_")

    def day_start(d):
        return timezone.make_aware(datetime.combine(d, datetime.min.time()))

    if period in ("today", "innu"):
        start = day_start(today)
        return start, start + timedelta(days=1), "today"
    if period in ("yesterday", "innale"):
        start = day_start(today - timedelta(days=1))
        return start, start + timedelta(days=1), "yesterday"
    if period in ("this_week", "week", "ee_aazhcha", "ee_azhcha"):
        start_d = today - timedelta(days=today.weekday())
        start = day_start(start_d)
        end = day_start(today) + timedelta(days=1)
        return start, end, "this week"
    if period in ("last_week", "kazhinja_aazhcha", "kazhinja_azhcha"):
        start_d = today - timedelta(days=today.weekday() + 7)
        start = day_start(start_d)
        end = day_start(start_d + timedelta(days=7))
        return start, end, "last week"
    if period in ("last_month", "kazhinja_maasam"):
        first_this = today.replace(day=1)
        end = day_start(first_this)
        prev_last = first_this - timedelta(days=1)
        start = day_start(prev_last.replace(day=1))
        return start, end, "last month"
    if period in ("this_month", "month", "ee_maasam", "ee_masam"):
        start = day_start(today.replace(day=1))
        end = day_start(today) + timedelta(days=1)
        return start, end, "this month"
    # default last 30 days
    start = day_start(today - timedelta(days=29))
    end = day_start(today) + timedelta(days=1)
    return start, end, "the last 30 days"


def parse_period_from_message(message: str) -> str:
    lower = (message or "").lower()
    if any(k in lower for k in ("last month", "kazhinja maasam", "previous month")):
        return "last_month"
    if any(k in lower for k in ("innale", "yesterday")):
        return "yesterday"
    if any(k in lower for k in ("kazhinja aazhcha", "kazhinja azhcha", "last week")):
        return "last_week"
    if any(k in lower for k in ("ee aazhcha", "ee azhcha", "this week")):
        return "this_week"
    if any(k in lower for k in ("innu", "today")):
        return "today"
    if any(k in lower for k in ("ee maasam", "ee masam", "this month")):
        return "this_month"
    return "this_month"


_CATEGORY_ALIASES = {
    "food": "FOOD",
    "foods": "FOOD",
    "lunch": "FOOD",
    "dinner": "FOOD",
    "groceries": "FOOD",
    "grocery": "FOOD",
    "transport": "TRANSPORT",
    "travel": "TRANSPORT",
    "uber": "TRANSPORT",
    "fuel": "TRANSPORT",
    "rent": "RENT",
    "housing": "RENT",
    "shopping": "SHOPPING",
    "clothes": "SHOPPING",
    "bills": "BILLS",
    "utilities": "BILLS",
    "health": "HEALTH",
    "medical": "HEALTH",
    "entertainment": "ENTERTAINMENT",
    "fun": "ENTERTAINMENT",
    "education": "EDUCATION",
    "learning": "EDUCATION",
    "salary": "SALARY",
    "income": "SALARY",
    "other": "OTHER",
}


def parse_category_from_message(message: str) -> str | None:
    lower = (message or "").lower()
    # "food-inu", "on food", "for lunch"
    for alias, cat in sorted(_CATEGORY_ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(alias)}(-inu)?\b", lower):
            return cat
    m = re.search(r"\bcategory\s*[:=]?\s*([a-z_]+)", lower)
    if m:
        key = m.group(1)
        return _CATEGORY_ALIASES.get(key, key.upper())
    return None


def parse_add_transaction_draft(message: str) -> dict[str, Any] | None:
    """Extract amount / title / type from natural language. Returns None if unclear."""
    lower = (message or "").strip()
    if not lower:
        return None
    amount = None
    m = re.search(
        r"(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d{1,2})?)",
        lower,
        flags=re.I,
    )
    if m:
        amount = float(m.group(1).replace(",", ""))
    if amount is None:
        return None

    is_income = bool(
        re.search(r"\b(income|salary|earned|got paid|credit)\b", lower)
        or re.search(r"\bincome\b", lower)
    )
    t_type = TransactionType.INCOME if is_income else TransactionType.EXPENSE

    # Strip command words for title
    title = lower
    title = re.sub(
        r"\b(add|log|record|create|new)\b",
        " ",
        title,
        flags=re.I,
    )
    title = re.sub(
        r"\b(expense|income|transaction|spend|spent|chilavu|payment)\b",
        " ",
        title,
        flags=re.I,
    )
    title = re.sub(r"(?:₹|rs\.?|inr)?\s*\d+(?:[.,]\d{1,2})?", " ", title, flags=re.I)
    title = re.sub(r"\b(for|on|of|of|about|today|yesterday|innu|innale)\b", " ", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" .,:-")
    category = parse_category_from_message(lower) or "OTHER"
    if not title:
        title = category.title() if category != "OTHER" else ("Income" if is_income else "Expense")
    # Capitalize lightly
    title = title[:1].upper() + title[1:] if title else title
    return {
        "title": title[:255],
        "amount": amount,
        "type": t_type,
        "category": category,
    }


def txs_in_period(user, start, end, *, tx_type: str | None = None, category: str | None = None):
    qs = Transaction.objects.filter(user=user, date__gte=start, date__lt=end)
    if tx_type:
        qs = qs.filter(type=tx_type)
    if category:
        qs = qs.filter(category__iexact=category)
    return qs


def sum_amount(qs) -> Decimal:
    total = qs.aggregate(s=Sum("amount"))["s"]
    return Decimal(total or 0)


def spending_summary(
    user,
    *,
    period: str = "this_month",
    group_by: str = "category",
    category: str | None = None,
) -> dict[str, Any]:
    start, end, label = period_bounds(period)
    currency = get_currency(user)
    base = txs_in_period(user, start, end, category=category)
    expenses = base.filter(type__in=EXPENSE_TYPES)
    income = base.filter(type=TransactionType.INCOME)

    expense_total = sum_amount(expenses)
    income_total = sum_amount(income)

    groups: list[dict[str, Any]] = []
    if group_by == "category":
        rows = (
            expenses.values("category")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        )
        for r in rows:
            groups.append(
                {
                    "key": r["category"] or "OTHER",
                    "total": float(r["total"] or 0),
                    "count": r["count"],
                }
            )
    elif group_by == "type":
        rows = (
            base.values("type")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        )
        for r in rows:
            groups.append(
                {
                    "key": r["type"],
                    "total": float(r["total"] or 0),
                    "count": r["count"],
                }
            )

    return {
        "period": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "currency": currency,
        "expense_total": float(expense_total),
        "income_total": float(income_total),
        "net": float(income_total - expense_total),
        "expense_count": expenses.count(),
        "income_count": income.count(),
        "category_filter": category,
        "groups": groups,
    }


def compare_periods(user, period_a: str = "this_month", period_b: str = "last_month") -> dict[str, Any]:
    a = spending_summary(user, period=period_a)
    b = spending_summary(user, period=period_b)
    a_exp = Decimal(str(a["expense_total"]))
    b_exp = Decimal(str(b["expense_total"]))
    delta = a_exp - b_exp
    pct = None
    if b_exp > 0:
        pct = float((delta / b_exp) * 100)
    return {
        "a": a,
        "b": b,
        "expense_delta": float(delta),
        "expense_delta_pct": pct,
        "currency": a["currency"],
    }


def top_expenses(user, *, period: str = "this_month", limit: int = 5) -> dict[str, Any]:
    start, end, label = period_bounds(period)
    currency = get_currency(user)
    rows = list(
        txs_in_period(user, start, end)
        .filter(type__in=EXPENSE_TYPES)
        .order_by("-amount", "-date")[: max(1, min(limit, 20))]
    )
    return {
        "period": label,
        "currency": currency,
        "items": [
            {
                "id": t.id,
                "title": t.title,
                "amount": float(t.amount),
                "category": t.category,
                "date": timezone.localtime(t.date).isoformat() if t.date else None,
                "isRecurring": t.is_recurring,
            }
            for t in rows
        ],
    }


def list_transactions(
    user,
    *,
    period: str = "this_month",
    category: str | None = None,
    tx_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    start, end, label = period_bounds(period)
    currency = get_currency(user)
    qs = txs_in_period(user, start, end, tx_type=tx_type, category=category).order_by(
        "-date", "-created_at"
    )
    rows = list(qs[: max(1, min(limit, 50))])
    return {
        "period": label,
        "currency": currency,
        "count": qs.count(),
        "items": [
            {
                "id": t.id,
                "title": t.title,
                "type": t.type,
                "amount": float(t.amount),
                "category": t.category,
                "date": timezone.localtime(t.date).isoformat() if t.date else None,
                "isRecurring": t.is_recurring,
                "notes": t.notes or "",
            }
            for t in rows
        ],
    }


def budget_status(user, *, category: str | None = None) -> dict[str, Any]:
    """No per-category Budget model yet — compare spend vs monthly_income / category share."""
    currency = get_currency(user)
    income_setting = get_monthly_income_setting(user)
    summary = spending_summary(user, period="this_month", category=category)
    expense = Decimal(str(summary["expense_total"]))
    pct_of_income = None
    if income_setting > 0:
        pct_of_income = float((expense / income_setting) * 100)

    warning = None
    if income_setting > 0 and expense > income_setting:
        warning = "Expenses this month are above your set monthly income."
    elif pct_of_income is not None and pct_of_income >= 80:
        warning = "You've used 80%+ of monthly income on expenses so far."

    cat_note = None
    if category:
        full = spending_summary(user, period="this_month")
        total = Decimal(str(full["expense_total"])) or Decimal("0")
        share = float((expense / total) * 100) if total > 0 else 0.0
        cat_note = f"{category} is {share:.0f}% of this month’s spending."

    return {
        "currency": currency,
        "category": category,
        "month_expense_total": float(expense),
        "month_income_logged": summary["income_total"],
        "monthly_income_setting": float(income_setting),
        "pct_of_income": pct_of_income,
        "warning": warning,
        "category_note": cat_note,
        "has_category_budgets": False,
        "groups": summary["groups"],
    }


def rule_based_insights(user) -> dict[str, Any]:
    """Deterministic insights — no LLM."""
    currency = get_currency(user)
    insights: list[dict[str, Any]] = []
    now = timezone.localtime()
    this = spending_summary(user, period="this_month")

    # Income vs expense balance
    income_setting = get_monthly_income_setting(user)
    exp = Decimal(str(this["expense_total"]))
    inc_logged = Decimal(str(this["income_total"]))
    balance_income = income_setting if income_setting > 0 else inc_logged
    if balance_income > 0:
        net = balance_income - exp
        insights.append(
            {
                "type": "balance",
                "severity": "info" if net >= 0 else "warn",
                "message": (
                    f"This month: spent {money(exp, currency)} vs income base "
                    f"{money(balance_income, currency)} "
                    f"({'surplus' if net >= 0 else 'over by'} {money(abs(net), currency)})."
                ),
            }
        )

    # Category up >30% vs ~3-month average (prior 90 days before this month / 3)
    start_3m = timezone.make_aware(
        datetime.combine((now.date().replace(day=1) - timedelta(days=90)), datetime.min.time())
    )
    month_start = timezone.make_aware(
        datetime.combine(now.date().replace(day=1), datetime.min.time())
    )
    hist = (
        Transaction.objects.filter(
            user=user,
            type__in=EXPENSE_TYPES,
            date__gte=start_3m,
            date__lt=month_start,
        )
        .values("category")
        .annotate(total=Sum("amount"))
    )
    this_by_cat = {g["key"]: Decimal(str(g["total"])) for g in this["groups"]}
    for row in hist:
        cat = row["category"] or "OTHER"
        avg = Decimal(row["total"] or 0) / Decimal("3")
        cur = this_by_cat.get(cat, Decimal("0"))
        if avg > 0 and cur >= avg * Decimal("1.3") and cur >= 100:
            pct = float(((cur - avg) / avg) * 100)
            insights.append(
                {
                    "type": "category_spike",
                    "severity": "warn",
                    "category": cat,
                    "message": (
                        f"{cat} spending is up ~{pct:.0f}% vs your 3-month average "
                        f"({money(cur, currency)} this month vs ~{money(avg, currency)}/mo)."
                    ),
                }
            )

    # Large one-off (not recurring), >2x median of month expenses or >₹2000 absolute floor
    start, end, _ = period_bounds("this_month")
    month_exps = list(
        txs_in_period(user, start, end)
        .filter(type__in=EXPENSE_TYPES, is_recurring=False)
        .order_by("-amount")[:30]
    )
    if month_exps:
        amounts = sorted(float(t.amount) for t in month_exps)
        mid = amounts[len(amounts) // 2]
        threshold = max(mid * 2, 2000.0)
        for t in month_exps[:5]:
            if float(t.amount) >= threshold:
                insights.append(
                    {
                        "type": "large_one_off",
                        "severity": "info",
                        "message": (
                            f"Large one-off: “{t.title}” {money(t.amount, currency)} "
                            f"({t.category})."
                        ),
                        "transaction_id": t.id,
                    }
                )
                break

    # Subscriptions / repeating
    recurring_qs = Transaction.objects.filter(
        user=user, is_recurring=True, type__in=EXPENSE_TYPES
    )
    recurring_count = recurring_qs.count()
    if recurring_count:
        recurring = list(recurring_qs.order_by("-date")[:10])
        titles = ", ".join(f"“{t.title}”" for t in recurring[:4])
        insights.append(
            {
                "type": "subscriptions",
                "severity": "info",
                "message": f"Recurring charges on file: {titles}"
                + ("…" if recurring_count > 4 else "."),
            }
        )

    return {"currency": currency, "insights": insights, "month": this}


def format_summary_reply(summary: dict[str, Any]) -> str:
    cur = summary.get("currency") or "₹"
    lines = [
        f"Spending for {summary['period']}: {money(summary['expense_total'], cur)}"
        + (f" across {summary['expense_count']} expense(s)." if summary["expense_count"] else ".")
    ]
    if summary.get("category_filter"):
        lines[0] = (
            f"{summary['category_filter']} for {summary['period']}: "
            f"{money(summary['expense_total'], cur)}."
        )
    if summary.get("income_total"):
        lines.append(f"Income logged: {money(summary['income_total'], cur)}.")
    if summary.get("groups") and not summary.get("category_filter"):
        top = summary["groups"][:5]
        if top:
            bits = [f"{g['key']} {money(g['total'], cur)}" for g in top]
            lines.append("Top categories: " + "; ".join(bits) + ".")
    return " ".join(lines)
