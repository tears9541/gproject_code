from __future__ import annotations

from django.core.management.base import BaseCommand

from myApp.models import CommentInfo


class Command(BaseCommand):
    help = "Normalize gender field values (m/f -> 男/女) for specified keywords."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keywords",
            nargs="+",
            required=True,
            help="Keywords to update, e.g. --keywords 爱情",
        )

    def handle(self, *args, **options):
        keywords = options["keywords"]

        qs = CommentInfo.objects.filter(keyword__in=keywords)

        updated_m = qs.filter(gender__iexact="m").update(gender="男")
        updated_f = qs.filter(gender__iexact="f").update(gender="女")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated m->男: {updated_m}, f->女: {updated_f} (keywords={keywords})"
            )
        )
