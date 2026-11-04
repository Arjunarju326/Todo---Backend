import time
from datetime import datetime, time as dtime
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import connection
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import (
    Task, Transaction, Debt, Bill, Habit,
    LearningGoal, JobApplication, Note, UserSettings
)
from .serializers import (
    TaskSerializer, TransactionSerializer, DebtSerializer, BillSerializer,
    HabitSerializer, LearningGoalSerializer, JobApplicationSerializer,
    NoteSerializer, UserSettingsSerializer
)
from core.settings import DB_HOST, DB_NAME

DEFAULT_USERNAME = "arjun"
DEFAULT_PASSWORD = "dayflow123"
DEFAULT_DISPLAY_NAME = "Arjun"


def get_or_create_settings():
    settings = UserSettings.objects.first()
    if not settings:
        settings = UserSettings.objects.create(
            user_name=DEFAULT_DISPLAY_NAME,
            monthly_income=0,
            monthly_emi_commitment=0,
            savings_target=0,
            currency="₹",
            timezone="Asia/Kolkata"
        )
    return settings


def ensure_default_user():
    user, created = User.objects.get_or_create(
        username=DEFAULT_USERNAME,
        defaults={
            "email": "arjun@dayflow.app",
            "first_name": DEFAULT_DISPLAY_NAME,
            "is_staff": False,
            "is_superuser": False,
        },
    )
    if created:
        user.set_password(DEFAULT_PASSWORD)
        user.save()
    return user


def serialize_user(user):
    settings = get_or_create_settings()
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "displayName": settings.user_name or user.first_name or user.username,
        "currency": settings.currency or "₹",
    }


class AuthLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            ensure_default_user()
            username = (request.data.get("username") or "").strip()
            password = request.data.get("password") or ""
            if not username or not password:
                return Response(
                    {"success": False, "error": "Username and password are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = authenticate(request, username=username, password=password)
            if user is None:
                return Response(
                    {"success": False, "error": "Invalid username or password"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            login(request, user)
            return Response({"success": True, "user": serialize_user(user)})
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AuthLogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"success": True, "message": "Logged out"})


class AuthMeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ensure_default_user()
        if not request.user.is_authenticated:
            return Response(
                {"success": False, "authenticated": False},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            {
                "success": True,
                "authenticated": True,
                "user": serialize_user(request.user),
            }
        )


class AuthRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            username = (request.data.get("username") or "").strip().lower()
            password = request.data.get("password") or ""
            display_name = (request.data.get("displayName") or request.data.get("name") or "").strip()

            if not username or not password:
                return Response(
                    {"success": False, "error": "Username and password are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if len(password) < 6:
                return Response(
                    {"success": False, "error": "Password must be at least 6 characters"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if User.objects.filter(username=username).exists():
                return Response(
                    {"success": False, "error": "Username already taken"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=display_name or username,
            )
            settings = get_or_create_settings()
            if display_name:
                settings.user_name = display_name
                settings.save(update_fields=["user_name"])

            login(request, user)
            return Response(
                {"success": True, "user": serialize_user(user)},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DashboardView(APIView):
    def get(self, request):
        try:
            now = timezone.now()
            start_of_today = timezone.make_aware(datetime.combine(now.date(), dtime.min))
            end_of_today = timezone.make_aware(datetime.combine(now.date(), dtime.max))
            start_of_month = timezone.make_aware(datetime(now.year, now.month, 1))

            settings = get_or_create_settings()

            # Tasks
            all_tasks = Task.objects.all()
            tasks_due_today = [
                t for t in all_tasks
                if t.status != 'DONE' and t.due_date and start_of_today <= t.due_date <= end_of_today
            ]
            overdue_tasks = [
                t for t in all_tasks
                if t.status != 'DONE' and t.due_date and t.due_date < start_of_today
            ]
            upcoming_tasks = [
                t for t in all_tasks
                if t.status != 'DONE' and t.due_date and t.due_date > end_of_today
            ]
            completed_tasks_today = [
                t for t in all_tasks
                if t.status == 'DONE' and t.completed_at and t.completed_at >= start_of_today
            ]
            total_today_tasks = len(tasks_due_today) + len(completed_tasks_today)
            if total_today_tasks > 0:
                task_completion_rate = round((len(completed_tasks_today) / total_today_tasks) * 100)
            elif all_tasks.exists():
                done_count = all_tasks.filter(status='DONE').count()
                task_completion_rate = round((done_count / all_tasks.count()) * 100)
            else:
                task_completion_rate = 100

            # Transactions (This Month)
            month_transactions = Transaction.objects.filter(date__gte=start_of_month)
            total_income = float(month_transactions.filter(type='INCOME').aggregate(Sum('amount'))['amount__sum'] or 0)
            total_expense = float(month_transactions.filter(type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or 0)
            net_balance = total_income - total_expense

            # Debts
            active_debts = Debt.objects.exclude(status='SETTLED')
            money_i_owe = sum(float(d.total_amount - d.paid_amount) for d in active_debts if d.type == 'OWED_BY_ME')
            money_owed_to_me = sum(float(d.total_amount - d.paid_amount) for d in active_debts if d.type == 'OWED_TO_ME')

            upcoming_payments = [
                {
                    "title": f"Payment to {d.person_name}",
                    "amount": float(d.total_amount - d.paid_amount),
                    "dueDate": d.due_date.isoformat() if d.due_date else None,
                    "type": "DEBT",
                }
                for d in active_debts if d.type == 'OWED_BY_ME'
            ]

            # Plan/bill expiry reminders (e.g. 28-day mobile recharge)
            for bill in Bill.objects.filter(is_active=True):
                status_code = bill.reminder_status
                if status_code not in ('ABOUT_TO_EXPIRE', 'EXPIRED'):
                    continue
                upcoming_payments.append({
                    "title": bill.title,
                    "amount": float(bill.amount),
                    "dueDate": bill.expires_on.isoformat(),
                    "type": "BILL",
                    "reminderStatus": status_code,
                    "daysLeft": bill.days_left,
                    "planDays": bill.plan_days,
                })

            # Habits
            today_str = now.strftime('%Y-%m-%d')
            all_habits = Habit.objects.all()
            habits_completed_today = sum(1 for h in all_habits if today_str in (h.completed_dates or []))

            # Learning Goals
            learning_goals = LearningGoal.objects.all()
            active_learning = [g for g in learning_goals if g.status == 'IN_PROGRESS']

            # Daily questions
            daily_questions = {
                "finishToday": {
                    "question": "1. What must I finish today?",
                    "items": [
                        {"id": str(t.id), "title": t.title, "priority": t.priority, "category": t.category}
                        for t in tasks_due_today
                    ],
                    "summary": (
                        f"{len(tasks_due_today)} task{'s' if len(tasks_due_today) > 1 else ''} scheduled for today."
                        if tasks_due_today
                        else "No urgent tasks due today. Great time to get ahead!"
                    ),
                },
                "moneyToPay": {
                    "question": "2. What money do I need to pay, and when?",
                    "items": upcoming_payments,
                    "emiCommitment": float(settings.monthly_emi_commitment),
                    "totalOwed": money_i_owe,
                    "summary": (
                        f"Total liabilities: {settings.currency}{money_i_owe:,.2f}. Monthly EMI: {settings.currency}{float(settings.monthly_emi_commitment):,.2f}."
                        if money_i_owe > 0
                        else f"All debts settled! Planned monthly EMI is {settings.currency}{float(settings.monthly_emi_commitment):,.2f}."
                    ),
                },
                "careerGrowth": {
                    "question": "3. What should I learn or improve today?",
                    "items": [
                        {
                            "title": l.title,
                            "progress": l.progress_percentage,
                            "hours": f"{float(l.logged_hours):g}/{float(l.weekly_target_hours):g} hrs this week",
                        }
                        for l in active_learning
                    ],
                    "summary": (
                        f"{len(active_learning)} learning stream{'s' if len(active_learning) > 1 else ''} in progress."
                        if active_learning
                        else "No active course. Pick a topic in My Growth to keep learning!"
                    ),
                },
                "delayedOrOverspent": {
                    "question": "4. What have I forgotten, delayed, or overspent on?",
                    "overdueTasksCount": len(overdue_tasks),
                    "overdueTasks": [
                        {"id": str(t.id), "title": t.title, "dueDate": t.due_date.isoformat() if t.due_date else None}
                        for t in overdue_tasks[:3]
                    ],
                    "budgetWarning": (
                        f"Expenses ({settings.currency}{total_expense:,.2f}) have exceeded this month's recorded income!"
                        if total_expense > float(settings.monthly_income) and float(settings.monthly_income) > 0
                        else None
                    ),
                    "summary": (
                        f"{len(overdue_tasks)} overdue task{'s' if len(overdue_tasks) > 1 else ''} require attention!"
                        if overdue_tasks
                        else "You're completely on schedule with no overdue tasks!"
                    ),
                },
            }

            return Response({
                "success": True,
                "stats": {
                    "totalTasks": all_tasks.count(),
                    "dueTodayCount": len(tasks_due_today),
                    "overdueCount": len(overdue_tasks),
                    "upcomingCount": len(upcoming_tasks),
                    "completedCount": all_tasks.filter(status='DONE').count(),
                    "taskCompletionRate": task_completion_rate,
                    "totalIncome": total_income,
                    "totalExpense": total_expense,
                    "netBalance": net_balance,
                    "moneyIOwe": money_i_owe,
                    "moneyOwedToMe": money_owed_to_me,
                    "habitsTotal": all_habits.count(),
                    "habitsCompletedToday": habits_completed_today,
                    "activeLearningCount": len(active_learning),
                },
                "dailyQuestions": daily_questions,
                "habits": HabitSerializer(all_habits, many=True).data,
                "notes": NoteSerializer(Note.objects.all()[:5], many=True).data,
                "learningGoals": LearningGoalSerializer(learning_goals, many=True).data,
                "settings": UserSettingsSerializer(settings).data,
                "dbStatus": {
                    "connected": True,
                    "host": DB_HOST,
                    "name": DB_NAME,
                    "engine": "PostgreSQL",
                },
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TasksView(APIView):
    def get(self, request):
        try:
            category = request.GET.get('category')
            priority = request.GET.get('priority')
            stat = request.GET.get('status')
            filt = request.GET.get('filter')

            qs = Task.objects.all()
            if category and category != 'ALL':
                qs = qs.filter(category=category)
            if priority and priority != 'ALL':
                qs = qs.filter(priority=priority)
            if stat and stat != 'ALL':
                qs = qs.filter(status=stat)

            now = timezone.now()
            start_of_today = timezone.make_aware(datetime.combine(now.date(), dtime.min))
            end_of_today = timezone.make_aware(datetime.combine(now.date(), dtime.max))

            if filt == 'today':
                qs = qs.filter(due_date__gte=start_of_today, due_date__lte=end_of_today)
            elif filt == 'overdue':
                qs = qs.filter(due_date__lt=start_of_today).exclude(status='DONE')
            elif filt == 'upcoming':
                qs = qs.filter(due_date__gt=end_of_today).exclude(status='DONE')

            serializer = TaskSerializer(qs, many=True)
            return Response({"success": True, "tasks": serializer.data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            data = request.data
            if not data.get('title'):
                return Response({"success": False, "error": "Title is required"}, status=status.HTTP_400_BAD_REQUEST)

            due_date = data.get('dueDate') or data.get('due_date')
            task = Task.objects.create(
                title=data['title'],
                description=data.get('description', ''),
                category=data.get('category', 'PERSONAL'),
                priority=data.get('priority', 'MEDIUM'),
                status=data.get('status', 'TODO'),
                due_date=due_date if due_date else None,
                is_important=bool(data.get('isImportant', data.get('is_important', False))),
                tags=data.get('tags', []) if isinstance(data.get('tags'), list) else [],
            )
            return Response({"success": True, "task": TaskSerializer(task).data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            data = request.data
            task_id = data.get('id') or data.get('_id')
            if not task_id:
                return Response({"success": False, "error": "Task ID is required"}, status=status.HTTP_400_BAD_REQUEST)

            task = Task.objects.filter(id=task_id).first()
            if not task:
                return Response({"success": False, "error": "Task not found"}, status=status.HTTP_404_NOT_FOUND)

            if 'title' in data:
                task.title = data['title']
            if 'description' in data:
                task.description = data['description']
            if 'category' in data:
                task.category = data['category']
            if 'priority' in data:
                task.priority = data['priority']
            if 'status' in data:
                new_status = data['status']
                if new_status == 'DONE' and not task.completed_at:
                    task.completed_at = timezone.now()
                elif new_status != 'DONE':
                    task.completed_at = None
                task.status = new_status
            if 'dueDate' in data or 'due_date' in data:
                task.due_date = data.get('dueDate') or data.get('due_date')
            if 'isImportant' in data or 'is_important' in data:
                task.is_important = bool(data.get('isImportant', data.get('is_important')))
            if 'tags' in data:
                task.tags = data['tags']

            task.save()
            return Response({"success": True, "task": TaskSerializer(task).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            task_id = request.GET.get('id')
            if not task_id:
                return Response({"success": False, "error": "Task ID is required"}, status=status.HTTP_400_BAD_REQUEST)

            Task.objects.filter(id=task_id).delete()
            return Response({"success": True, "message": "Task deleted successfully"})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FinanceView(APIView):
    def get(self, request):
        try:
            view = request.GET.get('view')
            transactions = Transaction.objects.all() if view != 'debts' else []
            debts = Debt.objects.all() if view != 'transactions' else []
            bills = Bill.objects.all() if view not in ('transactions', 'debts') else []

            return Response({
                "success": True,
                "transactions": TransactionSerializer(transactions, many=True).data if view != 'debts' else [],
                "debts": DebtSerializer(debts, many=True).data if view != 'transactions' else [],
                "bills": BillSerializer(bills, many=True).data if view not in ('transactions', 'debts') else [],
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            data = request.data
            item_type = data.get('itemType')

            if item_type == 'debt':
                person_name = data.get('personName') or data.get('person_name')
                total_amount = data.get('totalAmount') or data.get('total_amount')
                debt_type = data.get('type')
                if not person_name or not total_amount or not debt_type:
                    return Response({"success": False, "error": "Person name, total amount, and type are required"}, status=status.HTTP_400_BAD_REQUEST)

                paid_amount = float(data.get('paidAmount') or data.get('paid_amount', 0))
                total_float = float(total_amount)
                if paid_amount >= total_float:
                    debt_status = 'SETTLED'
                elif paid_amount > 0:
                    debt_status = 'PARTIALLY_PAID'
                else:
                    debt_status = 'PENDING'

                due_date = data.get('dueDate') or data.get('due_date')
                debt = Debt.objects.create(
                    person_name=person_name,
                    type=debt_type,
                    total_amount=total_float,
                    paid_amount=paid_amount,
                    due_date=due_date if due_date else None,
                    status=debt_status,
                    notes=data.get('notes', ''),
                )
                return Response({"success": True, "item": DebtSerializer(debt).data, "itemType": "debt"}, status=status.HTTP_201_CREATED)

            if item_type == 'bill':
                title = data.get('title')
                if not title:
                    return Response({"success": False, "error": "Title is required"}, status=status.HTTP_400_BAD_REQUEST)

                recharge_date = data.get('rechargeDate') or data.get('recharge_date') or timezone.localdate().isoformat()
                bill = Bill.objects.create(
                    title=title,
                    amount=float(data.get('amount') or 0),
                    category=data.get('category', 'MOBILE'),
                    recharge_date=recharge_date,
                    plan_days=int(data.get('planDays') or data.get('plan_days') or 28),
                    remind_days_before=int(data.get('remindDaysBefore') or data.get('remind_days_before') or 3),
                    notes=data.get('notes', ''),
                    is_active=bool(data.get('isActive', data.get('is_active', True))),
                )
                return Response({"success": True, "item": BillSerializer(bill).data, "bill": BillSerializer(bill).data, "itemType": "bill"}, status=status.HTTP_201_CREATED)

            title = data.get('title')
            amount = data.get('amount')
            t_type = data.get('type')
            if not title or amount is None or not t_type:
                return Response({"success": False, "error": "Title, amount, and type are required"}, status=status.HTTP_400_BAD_REQUEST)

            date_val = data.get('date')
            trans = Transaction.objects.create(
                title=title,
                type=t_type,
                amount=float(amount),
                category=data.get('category', 'OTHER'),
                date=date_val if date_val else timezone.now(),
                is_recurring=bool(data.get('isRecurring', data.get('is_recurring', False))),
                notes=data.get('notes', ''),
            )
            return Response({"success": True, "item": TransactionSerializer(trans).data, "itemType": "transaction"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request):
        try:
            data = request.data
            item_type = data.get('itemType')

            if item_type == 'bill':
                bill_id = data.get('billId') or data.get('id')
                bill = Bill.objects.filter(id=bill_id).first()
                if not bill:
                    return Response({"success": False, "error": "Bill not found"}, status=status.HTTP_404_NOT_FOUND)

                # Mark recharged today (or provided date) — restarts the plan cycle
                if data.get('markRecharged') or data.get('mark_recharged'):
                    recharge = data.get('rechargeDate') or data.get('recharge_date')
                    bill.recharge_date = recharge or timezone.localdate()
                else:
                    if 'title' in data:
                        bill.title = data['title']
                    if 'amount' in data:
                        bill.amount = float(data['amount'])
                    if 'category' in data:
                        bill.category = data['category']
                    if 'rechargeDate' in data or 'recharge_date' in data:
                        bill.recharge_date = data.get('rechargeDate') or data.get('recharge_date')
                    if 'planDays' in data or 'plan_days' in data:
                        bill.plan_days = int(data.get('planDays') or data.get('plan_days'))
                    if 'remindDaysBefore' in data or 'remind_days_before' in data:
                        bill.remind_days_before = int(
                            data.get('remindDaysBefore') or data.get('remind_days_before')
                        )
                    if 'notes' in data:
                        bill.notes = data['notes']
                    if 'isActive' in data or 'is_active' in data:
                        bill.is_active = bool(data.get('isActive', data.get('is_active')))

                bill.save()
                return Response({"success": True, "bill": BillSerializer(bill).data})

            debt_id = data.get('debtId') or data.get('id')
            repayment_amount = data.get('repaymentAmount')
            notes = data.get('notes', '')

            if not debt_id or repayment_amount is None:
                return Response({"success": False, "error": "debtId and repaymentAmount are required"}, status=status.HTTP_400_BAD_REQUEST)

            debt = Debt.objects.filter(id=debt_id).first()
            if not debt:
                return Response({"success": False, "error": "Debt not found"}, status=status.HTTP_404_NOT_FOUND)

            added = float(repayment_amount)
            new_paid = float(debt.paid_amount) + added
            debt.paid_amount = new_paid
            if not isinstance(debt.repayments, list):
                debt.repayments = []
            debt.repayments.append({
                "amount": added,
                "date": timezone.now().isoformat(),
                "notes": notes,
            })
            if new_paid >= float(debt.total_amount):
                debt.status = 'SETTLED'
            elif new_paid > 0:
                debt.status = 'PARTIALLY_PAID'

            debt.save()
            return Response({"success": True, "debt": DebtSerializer(debt).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            item_id = request.GET.get('id')
            item_type = request.GET.get('itemType')
            if not item_id:
                return Response({"success": False, "error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)

            if item_type == 'debt':
                Debt.objects.filter(id=item_id).delete()
            elif item_type == 'bill':
                Bill.objects.filter(id=item_id).delete()
            else:
                Transaction.objects.filter(id=item_id).delete()

            return Response({"success": True, "message": "Item deleted successfully"})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GrowthView(APIView):
    def get(self, request):
        try:
            goals = LearningGoal.objects.all()
            jobs = JobApplication.objects.all()
            return Response({
                "success": True,
                "learningGoals": LearningGoalSerializer(goals, many=True).data,
                "jobApplications": JobApplicationSerializer(jobs, many=True).data,
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            data = request.data
            g_type = data.get('type')

            if g_type == 'job':
                company = data.get('company')
                role = data.get('role')
                if not company or not role:
                    return Response({"success": False, "error": "Company and Role are required"}, status=status.HTTP_400_BAD_REQUEST)

                applied_date = data.get('appliedDate') or data.get('applied_date')
                follow_up_date = data.get('followUpDate') or data.get('follow_up_date')

                job = JobApplication.objects.create(
                    company=company,
                    role=role,
                    status=data.get('status', 'APPLIED'),
                    location=data.get('location', 'Remote'),
                    applied_date=applied_date if applied_date else timezone.now(),
                    salary_estimate=data.get('salaryEstimate', data.get('salary_estimate', '')),
                    notes=data.get('notes', ''),
                    follow_up_date=follow_up_date if follow_up_date else None,
                )
                return Response({"success": True, "item": JobApplicationSerializer(job).data, "type": "job"}, status=status.HTTP_201_CREATED)
            else:
                title = data.get('title')
                if not title:
                    return Response({"success": False, "error": "Title is required"}, status=status.HTTP_400_BAD_REQUEST)

                progress = int(data.get('progressPercentage', data.get('progress_percentage', 0)))
                goal = LearningGoal.objects.create(
                    title=title,
                    category=data.get('category', 'OTHER'),
                    platform_or_course=data.get('platformOrCourse', data.get('platform_or_course', '')),
                    progress_percentage=progress,
                    status='COMPLETED' if progress == 100 else data.get('status', 'IN_PROGRESS'),
                    weekly_target_hours=float(data.get('weeklyTargetHours', data.get('weekly_target_hours', 5.0))),
                    logged_hours=float(data.get('loggedHours', data.get('logged_hours', 0.0))),
                    notes=data.get('notes', ''),
                )
                return Response({"success": True, "item": LearningGoalSerializer(goal).data, "type": "learning"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request):
        try:
            data = request.data
            item_id = data.get('id') or data.get('_id')
            g_type = data.get('type')
            if not item_id or not g_type:
                return Response({"success": False, "error": "id and type are required"}, status=status.HTTP_400_BAD_REQUEST)

            if g_type == 'job':
                job = JobApplication.objects.filter(id=item_id).first()
                if not job:
                    return Response({"success": False, "error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
                if 'company' in data: job.company = data['company']
                if 'role' in data: job.role = data['role']
                if 'status' in data: job.status = data['status']
                if 'location' in data: job.location = data['location']
                if 'notes' in data: job.notes = data['notes']
                if 'salaryEstimate' in data or 'salary_estimate' in data:
                    job.salary_estimate = data.get('salaryEstimate', data.get('salary_estimate'))
                if 'followUpDate' in data or 'follow_up_date' in data:
                    job.follow_up_date = data.get('followUpDate') or data.get('follow_up_date')
                job.save()
                return Response({"success": True, "item": JobApplicationSerializer(job).data})
            else:
                goal = LearningGoal.objects.filter(id=item_id).first()
                if not goal:
                    return Response({"success": False, "error": "Goal not found"}, status=status.HTTP_404_NOT_FOUND)
                if 'title' in data: goal.title = data['title']
                if 'category' in data: goal.category = data['category']
                if 'platformOrCourse' in data or 'platform_or_course' in data:
                    goal.platform_or_course = data.get('platformOrCourse', data.get('platform_or_course'))
                if 'progressPercentage' in data or 'progress_percentage' in data:
                    pct = int(data.get('progressPercentage', data.get('progress_percentage')))
                    goal.progress_percentage = pct
                    if pct == 100: goal.status = 'COMPLETED'
                if 'status' in data: goal.status = data['status']
                if 'weeklyTargetHours' in data or 'weekly_target_hours' in data:
                    goal.weekly_target_hours = float(data.get('weeklyTargetHours', data.get('weekly_target_hours')))
                if 'loggedHours' in data or 'logged_hours' in data:
                    goal.logged_hours = float(data.get('loggedHours', data.get('logged_hours')))
                if 'notes' in data: goal.notes = data['notes']
                goal.save()
                return Response({"success": True, "item": LearningGoalSerializer(goal).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            item_id = request.GET.get('id')
            g_type = request.GET.get('type')
            if not item_id:
                return Response({"success": False, "error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)

            if g_type == 'job':
                JobApplication.objects.filter(id=item_id).delete()
            else:
                LearningGoal.objects.filter(id=item_id).delete()
            return Response({"success": True, "message": "Item deleted successfully"})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HabitsView(APIView):
    def get(self, request):
        try:
            habits = Habit.objects.all()
            return Response({"success": True, "habits": HabitSerializer(habits, many=True).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            data = request.data
            name = data.get('name')
            if not name:
                return Response({"success": False, "error": "Habit name is required"}, status=status.HTTP_400_BAD_REQUEST)

            habit = Habit.objects.create(
                name=name,
                category=data.get('category', 'ROUTINE'),
                target_days_per_week=int(data.get('targetDaysPerWeek', data.get('target_days_per_week', 7))),
                streak=0,
                completed_dates=[],
                icon=data.get('icon', 'CheckCircle'),
            )
            return Response({"success": True, "habit": HabitSerializer(habit).data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request):
        try:
            data = request.data
            habit_id = data.get('id') or data.get('_id')
            date_str = data.get('dateStr')
            if not habit_id or not date_str:
                return Response({"success": False, "error": "Habit ID and dateStr are required"}, status=status.HTTP_400_BAD_REQUEST)

            habit = Habit.objects.filter(id=habit_id).first()
            if not habit:
                return Response({"success": False, "error": "Habit not found"}, status=status.HTTP_404_NOT_FOUND)

            dates = list(habit.completed_dates or [])
            if date_str in dates:
                dates.remove(date_str)
                habit.streak = max(0, habit.streak - 1)
            else:
                dates.append(date_str)
                habit.streak += 1

            habit.completed_dates = dates
            habit.save()
            return Response({"success": True, "habit": HabitSerializer(habit).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            habit_id = request.GET.get('id')
            if not habit_id:
                return Response({"success": False, "error": "Habit ID is required"}, status=status.HTTP_400_BAD_REQUEST)

            Habit.objects.filter(id=habit_id).delete()
            return Response({"success": True, "message": "Habit deleted successfully"})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotesView(APIView):
    def get(self, request):
        try:
            notes = Note.objects.all()
            return Response({"success": True, "notes": NoteSerializer(notes, many=True).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            data = request.data
            title = data.get('title')
            if not title:
                return Response({"success": False, "error": "Title is required"}, status=status.HTTP_400_BAD_REQUEST)

            note = Note.objects.create(
                title=title,
                content=data.get('content', ''),
                category=data.get('category', 'GENERAL'),
                is_pinned=bool(data.get('isPinned', data.get('is_pinned', False))),
                tags=data.get('tags', []) if isinstance(data.get('tags'), list) else [],
            )
            return Response({"success": True, "note": NoteSerializer(note).data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request):
        try:
            data = request.data
            note_id = data.get('id') or data.get('_id')
            if not note_id:
                return Response({"success": False, "error": "Note ID is required"}, status=status.HTTP_400_BAD_REQUEST)

            note = Note.objects.filter(id=note_id).first()
            if not note:
                return Response({"success": False, "error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)

            if 'title' in data: note.title = data['title']
            if 'content' in data: note.content = data['content']
            if 'category' in data: note.category = data['category']
            if 'isPinned' in data or 'is_pinned' in data:
                note.is_pinned = bool(data.get('isPinned', data.get('is_pinned')))
            if 'tags' in data: note.tags = data['tags']

            note.save()
            return Response({"success": True, "note": NoteSerializer(note).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            note_id = request.GET.get('id')
            if not note_id:
                return Response({"success": False, "error": "Note ID is required"}, status=status.HTTP_400_BAD_REQUEST)

            Note.objects.filter(id=note_id).delete()
            return Response({"success": True, "message": "Note deleted"})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SettingsView(APIView):
    def get(self, request):
        try:
            settings = get_or_create_settings()
            start_ping = time.time()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            ping_latency = round((time.time() - start_ping) * 1000, 2)

            return Response({
                "success": True,
                "settings": UserSettingsSerializer(settings).data,
                "dbStatus": {
                    "connected": True,
                    "host": DB_HOST,
                    "name": DB_NAME,
                    "engine": "PostgreSQL",
                    "latencyMs": ping_latency,
                },
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            data = request.data
            settings = get_or_create_settings()

            if 'userName' in data or 'user_name' in data:
                settings.user_name = data.get('userName', data.get('user_name'))
            if 'monthlyIncome' in data or 'monthly_income' in data:
                settings.monthly_income = float(data.get('monthlyIncome', data.get('monthly_income')))
            if 'monthlyEmiCommitment' in data or 'monthly_emi_commitment' in data:
                settings.monthly_emi_commitment = float(data.get('monthlyEmiCommitment', data.get('monthly_emi_commitment')))
            if 'savingsTarget' in data or 'savings_target' in data:
                settings.savings_target = float(data.get('savingsTarget', data.get('savings_target')))
            if 'currency' in data:
                settings.currency = data['currency']
            if 'timezone' in data:
                settings.timezone = data['timezone']

            settings.save()
            return Response({"success": True, "settings": UserSettingsSerializer(settings).data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SeedView(APIView):
    def post(self, request):
        try:
            force = request.data.get('force', False)
            if Task.objects.count() > 0 and not force:
                return Response({"success": True, "message": "Data already initialized. Reset not forced."})

            if force:
                Task.objects.all().delete()
                Transaction.objects.all().delete()
                Debt.objects.all().delete()
                Bill.objects.all().delete()
                Habit.objects.all().delete()
                LearningGoal.objects.all().delete()
                JobApplication.objects.all().delete()
                Note.objects.all().delete()

            now = timezone.now()
            today = now
            yesterday = now - timezone.timedelta(days=1)
            tomorrow = now + timezone.timedelta(days=1)
            in_three_days = now + timezone.timedelta(days=3)

            # 1. Auth user + settings
            ensure_default_user()
            UserSettings.objects.update_or_create(
                id=1,
                defaults={
                    "user_name": "Arjun",
                    "monthly_income": 15000,
                    "monthly_emi_commitment": 4500,
                    "savings_target": 1000,
                    "currency": "₹",
                    "timezone": "Asia/Kolkata",
                }
            )

            # 2. Tasks
            Task.objects.bulk_create([
                Task(
                    title="Review monthly EMI payment and verify bank balance",
                    description="Ensure funds are in the account before auto-debit on the 25th",
                    category="FINANCE",
                    priority="HIGH",
                    status="TODO",
                    due_date=today,
                    is_important=True,
                    tags=["EMI", "Banking", "Urgent"],
                ),
                Task(
                    title="Complete Next.js App Router & Django REST API integration",
                    description="Connect Next.js frontend to Python Django + PostgreSQL backend",
                    category="LEARNING",
                    priority="HIGH",
                    status="DONE",
                    due_date=today,
                    completed_at=now,
                    is_important=True,
                    tags=["Coding", "Next.js", "Django", "PostgreSQL"],
                ),
                Task(
                    title="Update resume with latest full-stack project details",
                    description="Highlight PostgreSQL, Python Django, Next.js, and TypeScript development experience",
                    category="WORK",
                    priority="MEDIUM",
                    status="TODO",
                    due_date=tomorrow,
                    is_important=False,
                    tags=["Career", "Resume"],
                ),
                Task(
                    title="Pay monthly broadband & electricity utility bills",
                    description="Check bill due dates on consumer portal",
                    category="FINANCE",
                    priority="MEDIUM",
                    status="TODO",
                    due_date=in_three_days,
                    is_important=False,
                    tags=["Bills", "Monthly"],
                ),
                Task(
                    title="Review Python and Django data modeling practice questions",
                    description="Prepare for upcoming technical screening interviews",
                    category="LEARNING",
                    priority="LOW",
                    status="TODO",
                    due_date=yesterday,
                    is_important=False,
                    tags=["Python", "Study"],
                ),
            ])

            # 3. Transactions
            Transaction.objects.bulk_create([
                Transaction(
                    title="Monthly Salary Credit",
                    type="INCOME",
                    amount=15000,
                    category="SALARY",
                    date=now - timezone.timedelta(days=10),
                    is_recurring=True,
                    notes="Direct bank deposit",
                ),
                Transaction(
                    title="Two-Wheeler Loan EMI",
                    type="EXPENSE",
                    amount=4500,
                    category="EMI",
                    date=now - timezone.timedelta(days=8),
                    is_recurring=True,
                    notes="Auto-debit for bike loan",
                ),
                Transaction(
                    title="Monthly Grocery & Supplies",
                    type="EXPENSE",
                    amount=3200,
                    category="FOOD",
                    date=now - timezone.timedelta(days=5),
                    is_recurring=False,
                    notes="Supermarket essentials",
                ),
                Transaction(
                    title="Broadband Internet Recharge",
                    type="EXPENSE",
                    amount=799,
                    category="UTILITIES",
                    date=now - timezone.timedelta(days=3),
                    is_recurring=True,
                    notes="Fiber optic unlimited plan",
                ),
                Transaction(
                    title="Freelance Technical Writing",
                    type="INCOME",
                    amount=2500,
                    category="FREELANCE",
                    date=now - timezone.timedelta(days=2),
                    is_recurring=False,
                    notes="Article on Python Django REST Framework",
                ),
            ])

            # 4. Debts
            Debt.objects.bulk_create([
                Debt(
                    person_name="Rohan (College Friend)",
                    type="OWED_BY_ME",
                    total_amount=2000,
                    paid_amount=500,
                    due_date=now + timezone.timedelta(days=14),
                    status="PARTIALLY_PAID",
                    notes="Borrowed for laptop charger replacement",
                    repayments=[{
                        "amount": 500,
                        "date": (now - timezone.timedelta(days=4)).isoformat(),
                        "notes": "Paid via UPI",
                    }],
                ),
                Debt(
                    person_name="Kiran",
                    type="OWED_TO_ME",
                    total_amount=1500,
                    paid_amount=0,
                    due_date=now + timezone.timedelta(days=7),
                    status="PENDING",
                    notes="Lent for course subscription",
                    repayments=[],
                ),
            ])

            # 5. Habits
            today_str = now.strftime('%Y-%m-%d')
            Habit.objects.bulk_create([
                Habit(
                    name="Daily 45-min Django & Full-stack Coding",
                    category="STUDY",
                    target_days_per_week=6,
                    streak=5,
                    completed_dates=[
                        (now - timezone.timedelta(days=i)).strftime('%Y-%m-%d')
                        for i in range(1, 6)
                    ] + [today_str],
                    icon="Code",
                ),
                Habit(
                    name="Morning Exercise & Stretching",
                    category="HEALTH",
                    target_days_per_week=5,
                    streak=3,
                    completed_dates=[
                        (now - timezone.timedelta(days=i)).strftime('%Y-%m-%d')
                        for i in range(1, 4)
                    ],
                    icon="Activity",
                ),
                Habit(
                    name="Read Technical Documentation & Tech Blogs",
                    category="CAREER",
                    target_days_per_week=5,
                    streak=4,
                    completed_dates=[
                        (now - timezone.timedelta(days=i)).strftime('%Y-%m-%d')
                        for i in range(1, 5)
                    ] + [today_str],
                    icon="BookOpen",
                ),
            ])

            # 6. Learning Goals
            LearningGoal.objects.bulk_create([
                LearningGoal(
                    title="Master Django REST Framework & PostgreSQL",
                    category="CODING",
                    platform_or_course="Official Docs & Real Project Practice",
                    progress_percentage=65,
                    status="IN_PROGRESS",
                    weekly_target_hours=8.0,
                    logged_hours=5.5,
                    notes="Focusing on query optimization and JWT authentication",
                ),
                LearningGoal(
                    title="Next.js App Router Full-Stack Mastery",
                    category="CODING",
                    platform_or_course="Full Stack Next.js Course",
                    progress_percentage=80,
                    status="IN_PROGRESS",
                    weekly_target_hours=6.0,
                    logged_hours=4.0,
                    notes="App router layouts, server actions, and caching mechanics",
                ),
            ])

            # 7. Job Applications
            JobApplication.objects.bulk_create([
                JobApplication(
                    company="TechSolutions Labs",
                    role="Junior Full Stack Engineer (Python/Django + React)",
                    status="INTERVIEWING",
                    location="Bengaluru (Hybrid)",
                    applied_date=now - timezone.timedelta(days=7),
                    salary_estimate="₹4.5 - 6.0 LPA",
                    notes="Technical interview round scheduled for Thursday",
                    follow_up_date=now + timezone.timedelta(days=2),
                ),
                JobApplication(
                    company="Nexus Innovate",
                    role="Backend Developer (Django & PostgreSQL)",
                    status="APPLIED",
                    location="Remote",
                    applied_date=now - timezone.timedelta(days=3),
                    salary_estimate="₹4.0 - 5.5 LPA",
                    notes="Application submitted via careers portal",
                    follow_up_date=now + timezone.timedelta(days=5),
                ),
            ])

            # 8. Notes
            Note.objects.bulk_create([
                Note(
                    title="Career Plan: 6-Month Goals",
                    content="1. Solidify Django + PostgreSQL backend skillset\n2. Master React & Next.js frontend state and performance\n3. Deploy 2 production-ready showcase apps on cloud\n4. Target Full Stack Developer role at high-growth tech firm",
                    category="CAREER",
                    is_pinned=True,
                    tags=["Career", "Goals", "Roadmap"],
                ),
                Note(
                    title="Finance Rules to Follow",
                    content="1. Always maintain ₹1,000 monthly emergency savings\n2. Pay EMI before the 25th of every month\n3. Never take high-interest consumer credit\n4. Record all expenses on the same day",
                    category="FINANCE",
                    is_pinned=False,
                    tags=["Money", "Budget", "Discipline"],
                ),
            ])

            return Response({
                "success": True,
                "message": "Sample organizer workspace seeded successfully into PostgreSQL (tododb)!"
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

