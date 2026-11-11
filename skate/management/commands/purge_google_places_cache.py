"""Remove Google Places content that is older than the allowed cache."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from skate.media_api.images_skateparks.resolver import google_data_is_fresh
from skate.models import Spots


class Command(BaseCommand):
    help = (
        "Delete Google Places metadata older than "
        "GOOGLE_PLACES_DATA_TTL_SECONDS, as required by the caching limit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the records without modifying them.",
        )

    def handle(self, *args, **options):
        candidates = Spots.objects.exclude(google_metadata=None)
        expired = []

        for spot in candidates.iterator():
            metadata = spot.google_metadata
            if isinstance(metadata, dict) and not google_data_is_fresh(metadata):
                expired.append(spot)

        for spot in expired:
            if not options["dry_run"]:
                spot.google_metadata = None
                spot.save(update_fields=["google_metadata"])

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {len(expired)} record(s) would be cleaned."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Cleaned {len(expired)} record(s).")
            )
