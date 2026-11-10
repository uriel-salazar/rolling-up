"""Import skateparks from OpenStreetMap into the database."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from skate.osm.exceptions import LocationResolutionError, OverpassError
from skate.osm.importer import import_spots
from skate.osm.service import fetch_skateparks

logger = logging.getLogger(__name__)

DEFAULT_LOCATION = "Guadalajara, Jalisco, Mexico"


class Command(BaseCommand):
    help = (
        "Import skateparks tagged in OpenStreetMap into the database. "
        "The data is retrieved from the official Overpass API."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--location",
            type=str,
            default=DEFAULT_LOCATION,
            help=(
                "Place to import from, given as 'City, State, Country'. "
                f"Defaults to '{DEFAULT_LOCATION}'."
            ),
        )
        parser.add_argument(
            "--bbox",
            type=str,
            default=None,
            help=(
                "Explicit bounding box to import from, in the "
                "'south,west,north,east' format. When given, --location "
                "is only used as a label."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Retrieve and process the data without writing anything "
                "to the database."
            ),
        )

    def handle(self, *args, **options):
        location = options["location"]
        bbox = options["bbox"]
        dry_run = options["dry_run"]

        self.stdout.write(
            self.style.HTTP_INFO(f"Fetching skateparks from OpenStreetMap: {location}")
        )

        try:
            spots, skipped, area_description = fetch_skateparks(
                location=location, bbox=bbox
            )
        except LocationResolutionError as exc:
            raise CommandError(str(exc)) from exc
        except OverpassError as exc:
            raise CommandError(f"Could not retrieve the skateparks: {exc}") from exc

        self.stdout.write(f"Area resolved to: {area_description}")
        self.stdout.write(
            f"{len(spots)} skatepark(s) found, {len(skipped)} object(s) skipped."
        )

        if dry_run:
            summary = import_spots(spots, dry_run=True)
            summary.skipped.extend(skipped)
            self.stdout.write(
                self.style.WARNING("Dry run: the database was not modified.")
            )
            self._report(summary, spots)
            return

        summary = import_spots(spots, dry_run=False)
        summary.skipped.extend(skipped)

        if summary.skipped:
            for reason in summary.skipped:
                self.stdout.write(self.style.WARNING(f"  skipped: {reason}"))

        self._report(summary, spots)

    def _report(self, summary, spots):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import finished:"))
        self.stdout.write(f"  created:  {summary.created}")
        self.stdout.write(f"  updated:  {summary.updated}")
        self.stdout.write(f"  unchanged: {summary.unchanged}")
        self.stdout.write(f"  skipped:  {len(summary.skipped)}")

        for spot in spots:
            self.stdout.write(
                f"  - {spot.osm_type}/{spot.osm_id} {spot.name} "
                f"({spot.latitude}, {spot.longitude})"
            )
