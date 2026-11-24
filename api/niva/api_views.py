"""Niva v2 HTTP API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import (
    NivaCompanionSettings,
    NivaDailyPlan,
    NivaSkillProgress,
    AssistantMemory,
)
from api.niva.services.memory.updater import consolidate_user_memories
from api.niva.services.orchestrator import process_message
from api.niva.services.planning.planner import build_daily_plan, plan_as_reply, review_day
from api.niva.throttles import NivaChatThrottle, NivaSearchThrottle
from api.assistant_service import get_profile


class NivaChatView(APIView):
    throttle_classes = [NivaChatThrottle]

    def post(self, request):
        try:
            message = (
                request.data.get("message")
                or request.data.get("text")
                or request.data.get("content")
                or ""
            )
            history = request.data.get("history") or []
            if not isinstance(history, list):
                history = []
            force_create = bool(
                request.data.get("createTask")
                or request.data.get("forceCreateTask")
                or request.data.get("addAsTask")
            )
            draft = request.data.get("draftTask") or request.data.get("suggestedTask")
            if draft is not None and not isinstance(draft, dict):
                draft = None
            conversation_id = request.data.get("conversation_id")
            try:
                conversation_id = int(conversation_id) if conversation_id else None
            except (TypeError, ValueError):
                conversation_id = None

            result = process_message(
                message,
                user=request.user,
                history=history,
                force_create_task=force_create,
                draft_task=draft,
                conversation_id=conversation_id,
            )
            if not result.get("success"):
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
            code = (
                status.HTTP_201_CREATED
                if result.get("tasksCreated") or result.get("memoriesSaved")
                else status.HTTP_200_OK
            )
            return Response(result, status=code)
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NivaDayPlanView(APIView):
    def get(self, request):
        today = __import__("django.utils.timezone", fromlist=["timezone"]).timezone.localdate()
        plan = NivaDailyPlan.objects.filter(user=request.user, plan_date=today).first()
        if not plan:
            payload = build_daily_plan(request.user)
        else:
            payload = plan.payload or {}
        return Response({"success": True, "plan": payload})

    def post(self, request):
        minutes = request.data.get("available_minutes") or request.data.get("availableMinutes")
        try:
            minutes = int(minutes) if minutes is not None else None
        except (TypeError, ValueError):
            minutes = None
        payload = build_daily_plan(request.user, available_minutes=minutes)
        profile = get_profile(request.user)
        return Response(
            {
                "success": True,
                "plan": payload,
                "reply": plan_as_reply(payload, user_name=profile.get("user_name") or "there"),
                "response_type": "daily_plan",
            }
        )


class NivaDayReviewView(APIView):
    def post(self, request):
        data = review_day(request.user)
        return Response({"success": True, **data, "response_type": "daily_review"})


class NivaMemoriesView(APIView):
    def get(self, request):
        rows = AssistantMemory.objects.filter(
            user=request.user, is_active=True, status="active"
        )[:50]
        return Response(
            {
                "success": True,
                "memories": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "content": m.content,
                        "category": m.category,
                        "key": m.key,
                        "tags": m.tags,
                        "importance": m.importance,
                    }
                    for m in rows
                ],
            }
        )

    def post(self, request):
        action = (request.data.get("action") or "list").lower()
        if action == "consolidate":
            from api.views import is_super_admin

            if not is_super_admin(request.user):
                return Response(
                    {
                        "success": False,
                        "error": "Only the Dayflow superadmin can run memory consolidation.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            stats = consolidate_user_memories(request.user)
            return Response({"success": True, **stats})
        return self.get(request)

    def patch(self, request):
        """Edit a memory (title/content/category/tags) — user-scoped."""
        mem_id = request.data.get("id") or request.data.get("memoryId")
        mem = AssistantMemory.objects.filter(
            id=mem_id, user=request.user, is_active=True
        ).first()
        if not mem:
            return Response(
                {"success": False, "error": "Memory not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = request.data or {}
        if "title" in data and data["title"] is not None:
            mem.title = str(data["title"])[:255]
        if "content" in data and data["content"] is not None:
            mem.content = str(data["content"])[:4000]
        if "category" in data and data["category"]:
            mem.category = str(data["category"])[:30]
        if "tags" in data and isinstance(data["tags"], list):
            mem.tags = [str(t)[:40] for t in data["tags"][:8]]
        if "importance" in data:
            try:
                mem.importance = max(1, min(10, int(data["importance"])))
            except (TypeError, ValueError):
                pass
        mem.save()
        try:
            from api.niva.services.rag.indexer import index_memory_document

            index_memory_document(mem, force_embed=True)
        except Exception:
            pass
        return Response(
            {
                "success": True,
                "memory": {
                    "id": mem.id,
                    "title": mem.title,
                    "content": mem.content,
                    "category": mem.category,
                    "tags": mem.tags,
                    "importance": mem.importance,
                },
            }
        )

    def delete(self, request):
        """Archive a memory (soft) — never deletes other users' data."""
        mem_id = (
            request.data.get("id")
            or request.data.get("memoryId")
            or request.query_params.get("id")
        )
        mem = AssistantMemory.objects.filter(id=mem_id, user=request.user).first()
        if not mem:
            return Response(
                {"success": False, "error": "Memory not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        mem.is_active = False
        mem.status = "archived"
        mem.save(update_fields=["is_active", "status", "updated_at"])
        try:
            from api.niva.services.rag.indexer import index_memory_document

            index_memory_document(mem, force_embed=False)
        except Exception:
            pass
        return Response({"success": True, "archived": mem.id})


class NivaLearningView(APIView):
    def get(self, request):
        skills = NivaSkillProgress.objects.filter(user=request.user)
        return Response(
            {
                "success": True,
                "skills": [
                    {
                        "id": s.id,
                        "skill": s.skill,
                        "level": s.current_level,
                        "target": s.target_level,
                        "roadmap": s.roadmap,
                        "completed": s.completed_topics,
                        "weak": s.weak_topics,
                    }
                    for s in skills
                ],
            }
        )


class NivaSettingsView(APIView):
    def get(self, request):
        from api.niva.services.usage import get_usage_today

        obj, _ = NivaCompanionSettings.objects.get_or_create(user=request.user)
        return Response(
            {
                "success": True,
                "settings": {
                    "responseVerbosity": obj.response_verbosity,
                    "replyLanguage": getattr(obj, "reply_language", None) or "auto",
                    "morningBriefingEnabled": obj.morning_briefing_enabled,
                    "morningBriefingTime": obj.morning_briefing_time.isoformat()
                    if obj.morning_briefing_time
                    else None,
                    "eveningReviewEnabled": obj.evening_review_enabled,
                    "eveningReviewTime": obj.evening_review_time.isoformat()
                    if obj.evening_review_time
                    else None,
                    "weeklyReviewEnabled": obj.weekly_review_enabled,
                    "quietHoursStart": obj.quiet_hours_start.isoformat()
                    if obj.quiet_hours_start
                    else None,
                    "quietHoursEnd": obj.quiet_hours_end.isoformat()
                    if obj.quiet_hours_end
                    else None,
                    "learningReminders": obj.learning_reminders,
                    "webResearchEnabled": obj.web_research_enabled,
                    "proactiveEnabled": obj.proactive_enabled,
                    "spendAlertsEnabled": getattr(obj, "spend_alerts_enabled", False),
                    "overdueNudgeEnabled": getattr(obj, "overdue_nudge_enabled", False),
                    "weeklyReviewWeekday": getattr(obj, "weekly_review_weekday", 6),
                },
                "usageToday": get_usage_today(request.user),
            }
        )

    def patch(self, request):
        obj, _ = NivaCompanionSettings.objects.get_or_create(user=request.user)
        data = request.data or {}
        mapping = {
            "responseVerbosity": "response_verbosity",
            "morningBriefingEnabled": "morning_briefing_enabled",
            "eveningReviewEnabled": "evening_review_enabled",
            "weeklyReviewEnabled": "weekly_review_enabled",
            "learningReminders": "learning_reminders",
            "webResearchEnabled": "web_research_enabled",
            "proactiveEnabled": "proactive_enabled",
            "spendAlertsEnabled": "spend_alerts_enabled",
            "overdueNudgeEnabled": "overdue_nudge_enabled",
            "weeklyReviewWeekday": "weekly_review_weekday",
        }
        for src, dest in mapping.items():
            if src in data:
                setattr(obj, dest, data[src])
        if "replyLanguage" in data or "reply_language" in data:
            raw = data.get("replyLanguage", data.get("reply_language"))
            val = str(raw or "auto").strip().lower()
            if val in ("english",):
                val = "en"
            if val in ("malayalam", "ml"):
                val = "manglish"  # UI offers Manglish; full ML script via auto+ml detect
            if val not in ("auto", "en", "manglish"):
                val = "auto"
            obj.reply_language = val
        obj.save()
        return self.get(request)


class NivaResearchView(APIView):
    throttle_classes = [NivaSearchThrottle]

    def post(self, request):
        from api.niva.services.tools.research_tools import web_search, news_search

        q = (request.data.get("query") or request.data.get("message") or "").strip()
        mode = (request.data.get("mode") or "web").lower()
        intent = {"primary_intent": "research.news" if mode == "news" else "research.web"}
        fn = news_search if mode == "news" else web_search
        result = fn(user=request.user, message=q, intent=intent)
        return Response({"success": bool(result.get("ok")), **result})


class NivaActivityView(APIView):
    """GET /api/niva/activity — recent activity events for the current user."""

    def get(self, request):
        from django.utils import timezone

        from api.niva.services.activity import (
            build_user_facing_summary,
            events_for_period,
            summarize_events,
        )

        period = (
            request.query_params.get("period")
            or request.query_params.get("range")
            or "today"
        )
        kind = request.query_params.get("kind") or None
        try:
            limit = int(request.query_params.get("limit") or 40)
        except (TypeError, ValueError):
            limit = 40
        limit = max(1, min(limit, 100))

        events, label = events_for_period(
            request.user, period=period, kind=kind, limit=limit
        )
        stats = summarize_events(events)
        return Response(
            {
                "success": True,
                "period": label,
                "stats": stats,
                "summary": build_user_facing_summary(events, label),
                "events": [
                    {
                        "id": e.id,
                        "kind": e.kind,
                        "entityType": e.entity_type,
                        "entityId": e.entity_id,
                        "summary": e.summary,
                        "payload": e.payload,
                        "createdAt": timezone.localtime(e.created_at).isoformat(),
                    }
                    for e in events
                ],
            }
        )


class NivaFinanceSummaryView(APIView):
    """GET /api/niva/finance/summary — spending summary from DB aggregates."""

    def get(self, request):
        from api.niva.services.finance import (
            format_summary_reply,
            parse_category_from_message,
            spending_summary,
        )

        period = request.query_params.get("period") or "this_month"
        category = request.query_params.get("category") or None
        group_by = request.query_params.get("group_by") or "category"
        q = request.query_params.get("q") or ""
        if not category and q:
            category = parse_category_from_message(q)
        summary = spending_summary(
            request.user, period=period, group_by=group_by, category=category
        )
        return Response(
            {
                "success": True,
                "summary": summary,
                "reply": format_summary_reply(summary),
            }
        )


class NivaFinanceInsightsView(APIView):
    """GET /api/niva/finance/insights — rule-based insights (no LLM)."""

    def get(self, request):
        from api.niva.services.finance import rule_based_insights

        data = rule_based_insights(request.user)
        return Response({"success": True, **data})


class NivaDoubtView(APIView):
    """POST /api/niva/doubt — explain + conditional search; optional save."""

    throttle_classes = [NivaSearchThrottle]

    def post(self, request):
        from api.niva.services.doubt import run_doubt, save_learning_note

        action = (request.data.get("action") or "explain").strip().lower()
        if action in ("save", "save_learning"):
            payload = request.data.get("learning_payload") or request.data.get("payload")
            if not isinstance(payload, dict):
                payload = None
            result = save_learning_note(
                user=request.user,
                payload=payload,
                source_message=str(request.data.get("message") or ""),
            )
            code = (
                status.HTTP_201_CREATED
                if result.get("ok")
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"success": bool(result.get("ok")), **result}, status=code)

        q = (
            request.data.get("query")
            or request.data.get("message")
            or request.data.get("doubt")
            or ""
        )
        force = bool(
            request.data.get("force_search")
            or request.data.get("search")
            or request.data.get("forceSearch")
        )
        result = run_doubt(str(q), user=request.user, force_search=force)
        return Response(
            {
                "success": bool(result.get("ok")),
                "reply": result.get("user_message"),
                "response": result.get("user_message"),
                "response_type": result.get("response_type") or "doubt_answer",
                **{k: v for k, v in result.items() if k != "user_message"},
            },
            status=status.HTTP_200_OK
            if result.get("ok")
            else status.HTTP_400_BAD_REQUEST,
        )


class NivaWeeklyReviewView(APIView):
    """GET /api/niva/weekly-review — tasks, spending, habits, one suggestion."""

    def get(self, request):
        from api.assistant_service import get_profile
        from api.niva.services.companion import build_weekly_review

        payload = build_weekly_review(request.user, profile=get_profile(request.user))
        return Response(
            {
                "success": True,
                "reply": payload.get("reply"),
                "response_type": "weekly_review",
                "data": payload.get("data") or {},
            }
        )
