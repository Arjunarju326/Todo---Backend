from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from api.niva.services.rag.indexer import index_free_text


class Command(BaseCommand):
    help = (
        "Reindex free-text RAG chunks (memories, notes, journals, summaries, learning notes). "
        "Does not embed raw transactions or task tables."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Only reindex one user (default: all users with data)",
        )
        parser.add_argument(
            "--no-embed",
            action="store_true",
            help="Skip embedding API calls (text chunks only / reuse existing)",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        force = not options["no_embed"]
        uid = options.get("user_id")
        if uid:
            users = list(User.objects.filter(pk=uid))
        else:
            users = list(User.objects.all()[:200])
        total = {}
        for u in users:
            counts = index_free_text(u, force_embed=force)
            self.stdout.write(f"user={u.id} {counts}")
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
        self.stdout.write(self.style.SUCCESS(f"done {total}"))
