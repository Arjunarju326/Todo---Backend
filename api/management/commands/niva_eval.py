from django.core.management.base import BaseCommand

from api.niva.services.lab.runner import ensure_suite, run_suite
from api.niva.services.lab.v3_scenarios import SUITE_SLUG as V3_SUITE_SLUG


class Command(BaseCommand):
    help = "Run Niva eval suites (v3 companion 100 by default; pass --suite for v2)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--suite",
            default=V3_SUITE_SLUG,
            help=f"Suite slug (default: {V3_SUITE_SLUG})",
        )
        parser.add_argument(
            "--mode",
            choices=["intent", "full"],
            default="intent",
            help="intent = router-only scoring; full = orchestrator with DB rollback",
        )
        parser.add_argument("--label", default="", help="Optional run label")
        parser.add_argument("--limit", type=int, default=None, help="Limit scenarios")
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Reload scenarios from generator/JSON before running",
        )
        parser.add_argument(
            "--seed-only",
            action="store_true",
            help="Only ensure suite/scenarios exist; do not run",
        )

    def handle(self, *args, **options):
        suite = ensure_suite(
            options["suite"], refresh_scenarios=bool(options["refresh"])
        )
        self.stdout.write(
            f"Suite {suite.slug}@{suite.version} scenarios={suite.scenario_count}"
        )
        if options["seed_only"]:
            return
        out = run_suite(
            suite=suite,
            mode=options["mode"],
            label=options["label"] or "",
            limit=options["limit"],
            refresh_scenarios=False,
        )
        if not out.get("success"):
            self.stderr.write(self.style.ERROR(str(out)))
            raise SystemExit(1)
        agg = out.get("aggregate") or {}
        self.stdout.write(
            self.style.SUCCESS(
                f"run_id={out.get('run_id')} score={agg.get('overall_score')} "
                f"passed={agg.get('passed')}/{agg.get('total')} "
                f"gate_ok={agg.get('gate_ok')} critical={agg.get('critical_fails')}"
            )
        )
        by_cat = agg.get("by_category") or {}
        for cat, info in sorted(by_cat.items()):
            self.stdout.write(
                f"  {cat}: score={info.get('score')} "
                f"passed={info.get('passed')}/{info.get('count')}"
            )
