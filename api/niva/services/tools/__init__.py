from .task_tools import task_create, task_list, task_complete, task_update
from .habit_tools import habit_get_today
from .goal_tools import goal_get_active
from .memory_tools import memory_save, memory_search, memory_archive
from .research_tools import web_search, news_search
from .learning_tools import (
    learning_create_plan,
    learning_get_progress,
    learning_generate_practice,
    learning_record_session,
)
from .admin_tools import users_list, system_internals_reply
from .activity_tools import get_activity
from .finance_tools import (
    add_transaction,
    list_transactions,
    spending_summary,
    compare_periods,
    top_expenses,
    budget_status,
    finance_insights,
)
from .doubt_tools import doubt_explain, save_doubt_learning

TOOL_HANDLERS = {
    "task_create": task_create,
    "task_list": task_list,
    "task_complete": task_complete,
    "task_update": task_update,
    "habit_get_today": habit_get_today,
    "goal_get_active": goal_get_active,
    "memory_save": memory_save,
    "memory_search": memory_search,
    "memory_archive": memory_archive,
    "web_search": web_search,
    "news_search": news_search,
    "learning_create_plan": learning_create_plan,
    "learning_get_progress": learning_get_progress,
    "learning_generate_practice": learning_generate_practice,
    "learning_record_session": learning_record_session,
    "users_list": users_list,
    "system_internals": system_internals_reply,
    "get_activity": get_activity,
    "add_transaction": add_transaction,
    "list_transactions": list_transactions,
    "spending_summary": spending_summary,
    "compare_periods": compare_periods,
    "top_expenses": top_expenses,
    "budget_status": budget_status,
    "finance_insights": finance_insights,
    "doubt_explain": doubt_explain,
    "save_doubt_learning": save_doubt_learning,
}
