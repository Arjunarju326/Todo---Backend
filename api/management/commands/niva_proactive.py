from django.core.management.base import BaseCommand

from api.niva.tasks import (
    run_activity_digests,
    run_evening_reviews,
    run_memory_consolidation,
    run_morning_briefings,
    run_overdue_nudges,
    run_spend_alerts,
    run_weekly_reviews,
)


class Command(BaseCommand):
    help = (
        "Run Niva proactive companion jobs (morning, evening, weekly, "
        "overdue/spend nudges, memory consolidate, activity digests)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--job",
            choices=[
                "morning",
                "evening",
                "weekly",
                "overdue",
                "spend",
                "consolidate",
                "digest",
                "all",
            ],
            default="all",
        )

    def handle(self, *args, **options):
        job = options["job"]
        if job in ("morning", "all"):
            self.stdout.write(str(run_morning_briefings()))
        if job in ("evening", "all"):
            self.stdout.write(str(run_evening_reviews()))
        if job in ("weekly", "all"):
            self.stdout.write(str(run_weekly_reviews()))
        if job in ("overdue", "all"):
            self.stdout.write(str(run_overdue_nudges()))
        if job in ("spend", "all"):
            self.stdout.write(str(run_spend_alerts()))
        if job in ("consolidate", "all"):
            self.stdout.write(str(run_memory_consolidation()))
        if job in ("digest", "all"):
            self.stdout.write(str(run_activity_digests()))
