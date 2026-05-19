from __future__ import annotations

from typing import Iterable, List, Tuple

from django.core.management.base import BaseCommand

from myApp.models import CommentInfo
from myApp.views import _encode_and_predict_sentiment


class Command(BaseCommand):
    help = "Run LSTM sentiment analysis for existing comments and persist results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keywords",
            nargs="+",
            required=True,
            help="Keywords to analyze, e.g. --keywords 爱情 人生",
        )
        parser.add_argument(
            "--only-unknown",
            action="store_true",
            help="Only analyze rows with lstm_result in ('', '未知情感').",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=256,
            help="How many comments to analyze per batch.",
        )

    def _iter_batches(self, items: List[CommentInfo], batch_size: int) -> Iterable[List[CommentInfo]]:
        for i in range(0, len(items), batch_size):
            yield items[i : i + batch_size]

    def handle(self, *args, **options):
        keywords: List[str] = options["keywords"]
        only_unknown: bool = bool(options["only_unknown"])
        batch_size: int = int(options["batch_size"] or 256)

        qs = CommentInfo.objects.filter(keyword__in=keywords)
        if only_unknown:
            qs = qs.filter(lstm_result__in=["", "未知情感"])

        items = list(qs.order_by("id"))
        total = len(items)
        if total == 0:
            self.stdout.write(self.style.WARNING("No matching comments found."))
            return

        self.stdout.write(f"Found {total} comments. Running sentiment analysis...")

        updated = 0
        for batch in self._iter_batches(items, batch_size=batch_size):
            texts = [obj.comment_text for obj in batch]
            labels_scores: List[Tuple[str, float]] = _encode_and_predict_sentiment(texts)
            for obj, (label, score) in zip(batch, labels_scores):
                obj.lstm_result = label
                obj.lstm_score = str(round(float(score), 2))
            CommentInfo.objects.bulk_update(batch, ["lstm_result", "lstm_score"], batch_size=batch_size)
            updated += len(batch)
            self.stdout.write(f"Updated {updated}/{total}")

        self.stdout.write(self.style.SUCCESS("Done."))
