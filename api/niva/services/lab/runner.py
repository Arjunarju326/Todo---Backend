"""Run Intelligence Lab suites and persist results."""

from __future__ import annotations

import time
from typing import Any

from django.db import transaction
from django.utils import timezone

from api.niva.services.intent_router import route_intent
from api.niva.services.lab.scenarios import (
    SUITE_NAME,
    SUITE_SLUG,
    SUITE_VERSION,
    load_scenario_dicts,
    write_scenarios_json,
)
from api.niva.services.lab.v3_scenarios import (
    SUITE_SLUG as V3_SUITE_SLUG,
    ensure_v3_suite,
)
from api.niva.services.lab.scorer import score_scenario
from api.niva.services.lab.tracer import emit_trace, new_request_id


def ensure_default_suite(*, refresh_scenarios: bool = False):
    from api.models import NivaEvalScenario, NivaEvalSuite

    write_scenarios_json()
    suite, _ = NivaEvalSuite.objects.get_or_create(
        slug=SUITE_SLUG,
        defaults={
            "name": SUITE_NAME,
            "version": SUITE_VERSION,
            "description": "Sprint 1 Intelligence Lab golden set (100 scenarios).",
        },
    )
    suite.name = SUITE_NAME
    suite.version = SUITE_VERSION
    suite.is_active = True

    scenarios = load_scenario_dicts()
    if refresh_scenarios or suite.scenarios.count() != len(scenarios):
        suite.scenarios.all().delete()
        bulk = []
        for sc in scenarios:
            bulk.append(
                NivaEvalScenario(
                    suite=suite,
                    scenario_id=str(sc.get("id") or ""),
                    category=str(sc.get("category") or "general")[:40],
                    title=str(sc.get("title") or sc.get("id") or "")[:255],
                    input_text=str(sc.get("input") or ""),
                    history=sc.get("history") or [],
                    fixtures=sc.get("fixtures") or {},
                    expect=sc.get("expect") or {},
                    weight=float(sc.get("weight") or 1.0),
                    tags=sc.get("tags") or [],
                    is_active=True,
                )
            )
        NivaEvalScenario.objects.bulk_create(bulk, batch_size=100)
    suite.scenario_count = suite.scenarios.filter(is_active=True).count()
    suite.save()
    return suite


def ensure_suite(slug: str | None = None, *, refresh_scenarios: bool = False):
    """Resolve v2 or v3 eval suite by slug (default: v3 companion suite)."""
    wanted = (slug or V3_SUITE_SLUG).strip()
    if wanted == V3_SUITE_SLUG or wanted in ("v3", "niva-v3"):
        return ensure_v3_suite(refresh_scenarios=refresh_scenarios)
    if wanted == SUITE_SLUG or wanted in ("v2", "intel", "default"):
        return ensure_default_suite(refresh_scenarios=refresh_scenarios)
    from api.models import NivaEvalSuite

    existing = NivaEvalSuite.objects.filter(slug=wanted).first()
    if existing:
        return existing
    return ensure_v3_suite(refresh_scenarios=refresh_scenarios)


def _apply_fixtures(user, fixtures: dict[str, Any]) -> None:
    if not fixtures or not user:
        return
    from api.models import AssistantMemory, Task

    for mem in fixtures.get("memories") or []:
        AssistantMemory.objects.create(
            user=user,
            title=str(mem.get("title") or "Fact")[:255],
            content=str(mem.get("content") or "")[:4000],
            category=str(mem.get("category") or "profile"),
            key=str(mem.get("key") or "")[:150],
            tags=mem.get("tags") or [],
            importance=int(mem.get("importance") or 5),
        )
    for task in fixtures.get("tasks") or []:
        Task.objects.create(
            user=user,
            title=str(task.get("title") or "Task")[:255],
            status=str(task.get("status") or "TODO"),
            priority=str(task.get("priority") or "MEDIUM"),
            category=str(task.get("category") or "PERSONAL"),
        )


def _run_one(
    scenario,
    *,
    mode: str,
    user=None,
) -> dict[str, Any]:
    expect = scenario.expect or {}
    history = scenario.history or []
    text = scenario.input_text or ""
    t0 = time.perf_counter()

    intent = route_intent(text, history=history)
    actual_intent = intent.get("primary_intent") or ""
    actual_tools = list(intent.get("tools_required") or [])
    reply = ""
    response_type = ""
    sources: list = []
    success = True

    if mode == "full":
        from api.niva.services.orchestrator import process_message

        # Skip live web calls for research scenarios unless explicitly allowed
        if actual_intent.startswith("research") and not expect.get("live_research"):
            reply = ""
            response_type = "research" if "news" in actual_intent else "research"
            success = True
        else:
            try:
                with transaction.atomic():
                    _apply_fixtures(user, scenario.fixtures or {})
                    result = process_message(
                        text,
                        user=user,
                        history=history,
                    )
                    reply = str(result.get("reply") or result.get("response") or "")
                    response_type = str(result.get("response_type") or "")
                    sources = result.get("sources") or []
                    success = bool(result.get("success", True))
                    # Prefer orchestrator intent if present
                    if result.get("intent"):
                        actual_intent = str(result.get("intent"))
                    emit_trace(
                        request_id=new_request_id(),
                        user=user,
                        source="eval",
                        message=text,
                        intent=intent,
                        result=result,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )
                    transaction.set_rollback(True)
            except Exception as exc:
                success = False
                reply = ""
                return {
                    "scenario_id": scenario.scenario_id,
                    "category": scenario.category,
                    "weight": float(scenario.weight or 1.0),
                    "passed": False,
                    "score": 0.0,
                    "metrics": {},
                    "diffs": [f"full-run error: {type(exc).__name__}: {exc}"],
                    "critical_fail": True,
                    "actual": {"error": str(exc)[:300]},
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                }

    latency_ms = int((time.perf_counter() - t0) * 1000)
    scored = score_scenario(
        expect=expect,
        actual_intent=actual_intent,
        actual_tools=actual_tools,
        reply=reply,
        response_type=response_type,
        sources=sources,
        latency_ms=latency_ms,
        mode=mode,
    )
    if not success:
        scored["passed"] = False
        scored["diffs"] = list(scored.get("diffs") or []) + ["orchestrator success=false"]

    return {
        "scenario_id": scenario.scenario_id,
        "category": scenario.category,
        "weight": float(scenario.weight or 1.0),
        "passed": scored["passed"],
        "score": scored["score"],
        "metrics": scored["metrics"],
        "diffs": scored["diffs"],
        "critical_fail": scored["critical_fail"],
        "actual": {
            "intent": actual_intent,
            "tools": actual_tools,
            "response_type": response_type,
            "reply_preview": (reply or "")[:240],
            "confidence": intent.get("confidence"),
        },
        "latency_ms": latency_ms,
        "scenario_obj": scenario,
    }


def run_suite(
    *,
    suite=None,
    mode: str = "intent",
    label: str = "",
    created_by=None,
    user=None,
    limit: int | None = None,
    refresh_scenarios: bool = False,
) -> dict[str, Any]:
    from api.models import NivaEvalResult, NivaEvalRun, NivaMetricSnapshot

    if suite is None:
        suite = ensure_suite(V3_SUITE_SLUG, refresh_scenarios=refresh_scenarios)
    elif refresh_scenarios:
        ensure_suite(getattr(suite, "slug", None) or V3_SUITE_SLUG, refresh_scenarios=True)
        suite.refresh_from_db()

    mode = "full" if mode == "full" else "intent"
    run = NivaEvalRun.objects.create(
        suite=suite,
        label=label or f"{suite.slug} {mode}",
        mode=mode,
        status="running",
        started_at=timezone.now(),
        created_by=created_by,
        meta={},
    )

    qs = suite.scenarios.filter(is_active=True).order_by("scenario_id")
    if limit:
        qs = qs[: int(limit)]

    results: list[dict[str, Any]] = []
    try:
        for sc in qs:
            results.append(_run_one(sc, mode=mode, user=user or created_by))

        # Persist
        bulk = []
        for r in results:
            bulk.append(
                NivaEvalResult(
                    run=run,
                    scenario=r.get("scenario_obj"),
                    scenario_key=r["scenario_id"],
                    category=r.get("category") or "",
                    passed=bool(r["passed"]),
                    score=float(r["score"]),
                    weight=float(r["weight"]),
                    metrics=r.get("metrics") or {},
                    actual=r.get("actual") or {},
                    diffs=r.get("diffs") or [],
                    critical_fail=bool(r.get("critical_fail")),
                    latency_ms=r.get("latency_ms"),
                )
            )
        NivaEvalResult.objects.bulk_create(bulk, batch_size=100)

        total_w = sum(r["weight"] for r in results) or 1.0
        overall = sum(r["score"] * r["weight"] for r in results) / total_w
        passed_n = sum(1 for r in results if r["passed"])
        critical = sum(1 for r in results if r.get("critical_fail"))
        by_cat: dict[str, dict[str, float]] = {}
        for r in results:
            cat = r.get("category") or "other"
            bucket = by_cat.setdefault(cat, {"n": 0, "pass": 0, "score_sum": 0.0})
            bucket["n"] += 1
            bucket["pass"] += 1 if r["passed"] else 0
            bucket["score_sum"] += r["score"]

        category_scores = {
            k: {
                "count": int(v["n"]),
                "passed": int(v["pass"]),
                "score": round(v["score_sum"] / v["n"], 4) if v["n"] else 0.0,
            }
            for k, v in by_cat.items()
        }

        gate_ok = overall >= 0.85 and critical == 0
        aggregate = {
            "overall_score": round(overall, 4),
            "passed": passed_n,
            "failed": len(results) - passed_n,
            "total": len(results),
            "critical_fails": critical,
            "gate_ok": gate_ok,
            "by_category": category_scores,
            "mode": mode,
        }
        run.aggregate = aggregate
        run.status = "completed"
        run.finished_at = timezone.now()
        run.save()

        NivaMetricSnapshot.objects.create(
            suite=suite,
            run=run,
            metric="suite_overall_score",
            value=float(aggregate["overall_score"]),
            payload=aggregate,
        )
        return {"success": True, "run_id": run.id, "aggregate": aggregate}
    except Exception as exc:
        run.status = "failed"
        run.finished_at = timezone.now()
        run.aggregate = {"error": str(exc)[:500]}
        run.save(update_fields=["status", "finished_at", "aggregate"])
        return {"success": False, "run_id": run.id, "error": str(exc)}
