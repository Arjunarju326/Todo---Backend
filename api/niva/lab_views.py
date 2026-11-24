"""Staff-only Niva Intelligence Lab HTTP API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import NivaEvalRun, NivaEvalSuite, NivaTrace
from api.niva.services.lab.runner import ensure_default_suite, ensure_suite, run_suite
from api.niva.services.lab.v3_scenarios import SUITE_SLUG as V3_SUITE_SLUG


def _lab_allowed(user) -> bool:
    """Developer Lab: staff/superuser, or the authenticated Dayflow owner session."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    # Personal Dayflow: allow authenticated users (single-tenant companion)
    return True


class _LabPermission(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return _lab_allowed(request.user)


class NivaLabSuitesView(APIView):
    permission_classes = [_LabPermission]

    def get(self, request):
        ensure_default_suite()
        ensure_suite(V3_SUITE_SLUG)
        suites = NivaEvalSuite.objects.filter(is_active=True).order_by("slug")
        return Response(
            {
                "success": True,
                "suites": [
                    {
                        "id": s.id,
                        "slug": s.slug,
                        "name": s.name,
                        "version": s.version,
                        "scenarioCount": s.scenario_count,
                        "description": s.description,
                    }
                    for s in suites
                ],
            }
        )

    def post(self, request):
        """Refresh suite scenarios from bundled JSON/generator."""
        slug = (request.data.get("suite") or V3_SUITE_SLUG).strip()
        suite = ensure_suite(slug, refresh_scenarios=True)
        return Response(
            {
                "success": True,
                "suite": {
                    "id": suite.id,
                    "slug": suite.slug,
                    "scenarioCount": suite.scenario_count,
                },
            }
        )


class NivaLabRunsView(APIView):
    permission_classes = [_LabPermission]

    def get(self, request):
        limit = request.query_params.get("limit") or 20
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 20
        runs = NivaEvalRun.objects.select_related("suite").order_by("-created_at")[:limit]
        return Response(
            {
                "success": True,
                "runs": [
                    {
                        "id": r.id,
                        "suite": r.suite.slug,
                        "label": r.label,
                        "mode": r.mode,
                        "status": r.status,
                        "aggregate": r.aggregate,
                        "startedAt": r.started_at.isoformat() if r.started_at else None,
                        "finishedAt": r.finished_at.isoformat() if r.finished_at else None,
                        "createdAt": r.created_at.isoformat(),
                    }
                    for r in runs
                ],
            }
        )

    def post(self, request):
        mode = (request.data.get("mode") or "intent").lower()
        label = (request.data.get("label") or "").strip()[:160]
        limit = request.data.get("limit")
        refresh = bool(request.data.get("refresh"))
        slug = (request.data.get("suite") or V3_SUITE_SLUG).strip()
        suite = ensure_suite(slug, refresh_scenarios=refresh)
        try:
            limit_n = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            limit_n = None
        out = run_suite(
            suite=suite,
            mode=mode,
            label=label,
            created_by=request.user,
            user=request.user,
            limit=limit_n,
        )
        code = status.HTTP_200_OK if out.get("success") else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response(out, status=code)


class NivaLabRunDetailView(APIView):
    permission_classes = [_LabPermission]

    def get(self, request, run_id: int):
        run = (
            NivaEvalRun.objects.select_related("suite")
            .prefetch_related("results")
            .filter(id=run_id)
            .first()
        )
        if not run:
            return Response(
                {"success": False, "error": "Run not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        fails_only = str(request.query_params.get("fails") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        results = run.results.all()
        if fails_only:
            results = results.filter(passed=False)
        return Response(
            {
                "success": True,
                "run": {
                    "id": run.id,
                    "suite": run.suite.slug,
                    "label": run.label,
                    "mode": run.mode,
                    "status": run.status,
                    "aggregate": run.aggregate,
                    "startedAt": run.started_at.isoformat() if run.started_at else None,
                    "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
                },
                "results": [
                    {
                        "scenarioId": r.scenario_key,
                        "category": r.category,
                        "passed": r.passed,
                        "score": r.score,
                        "weight": r.weight,
                        "metrics": r.metrics,
                        "actual": r.actual,
                        "diffs": r.diffs,
                        "criticalFail": r.critical_fail,
                        "latencyMs": r.latency_ms,
                    }
                    for r in results[:200]
                ],
            }
        )


class NivaLabTracesView(APIView):
    permission_classes = [_LabPermission]

    def get(self, request):
        limit = request.query_params.get("limit") or 50
        try:
            limit = max(1, min(200, int(limit)))
        except (TypeError, ValueError):
            limit = 50
        source = (request.query_params.get("source") or "").strip()
        qs = NivaTrace.objects.all().order_by("-created_at")
        if source in ("prod", "eval"):
            qs = qs.filter(source=source)
        rows = qs[:limit]
        return Response(
            {
                "success": True,
                "traces": [
                    {
                        "id": t.id,
                        "requestId": t.request_id,
                        "source": t.source,
                        "intent": t.primary_intent,
                        "confidence": t.intent_confidence,
                        "tools": t.tools,
                        "responseType": t.response_type,
                        "latencyMs": t.latency_ms,
                        "success": t.success,
                        "preview": t.message_preview,
                        "createdAt": t.created_at.isoformat(),
                    }
                    for t in rows
                ],
            }
        )


class NivaLabMetricsView(APIView):
    permission_classes = [_LabPermission]

    def get(self, request):
        from api.models import NivaMetricSnapshot

        snaps = NivaMetricSnapshot.objects.select_related("run", "suite").order_by(
            "-captured_at"
        )[:30]
        return Response(
            {
                "success": True,
                "metrics": [
                    {
                        "metric": s.metric,
                        "value": s.value,
                        "suite": s.suite.slug if s.suite_id else None,
                        "runId": s.run_id,
                        "capturedAt": s.captured_at.isoformat(),
                        "payload": s.payload,
                    }
                    for s in snaps
                ],
            }
        )
