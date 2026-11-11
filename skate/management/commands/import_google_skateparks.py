"""Import skateparks from Google Places API (New)."""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from skate.google_places.exceptions import GooglePlacesError
from skate.google_places.importer import import_places
from skate.google_places.service import discover_skateparks
from skate.osm.areas import geocode_area
from skate.osm.exceptions import LocationResolutionError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Discover actual skateparks with the Google Places API (New) and "
        "merge them into the existing spots. Nearby Search is restricted "
        "to includedTypes ['skateboard_park']."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--lat",
            type=float,
            default=None,
            help="Latitude of the centre of the search.",
        )
        parser.add_argument(
            "--lng",
            type=float,
            default=None,
            help="Longitude of the centre of the search.",
        )
        parser.add_argument(
            "--location",
            type=str,
            default=None,
            help=(
                "Place to search around, given as 'City, State, Country'. "
                "It is geocoded with Nominatim when --lat/--lng are not given."
            ),
        )
        parser.add_argument(
            "--radius",
            type=int,
            default=settings.GOOGLE_PLACES_SEARCH_RADIUS,
            help="Radius of the search in metres (maximum 50000).",
        )
        parser.add_argument(
            "--max-results",
            type=int,
            default=settings.GOOGLE_PLACES_MAX_RESULTS,
            help="Number of results asked for on every page (1 to 20).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Retrieve and process the skateparks without writing anything.",
        )

    def handle(self, *args, **options):
        if not settings.GOOGLE_PLACES_API_KEY:
            raise CommandError(
                "GOOGLE_PLACES_API_KEY is not configured. Set it in the "
                "environment before importing Google Places skateparks."
            )

        latitude, longitude = self._resolve_center(options)

        self.stdout.write(
            self.style.HTTP_INFO(
                f"Searching Google Places skateparks around "
                f"{latitude}, {longitude} ({options['radius']} m)"
            )
        )

        try:
            places = discover_skateparks(
                latitude,
                longitude,
                radius=options["radius"],
                max_results=options["max_results"],
            )
        except GooglePlacesError as exc:
            raise CommandError(f"Could not retrieve the skateparks: {exc}") from exc

        self.stdout.write(f"{len(places)} skatepark(s) found.")

        if options["dry_run"]:
            summary = import_places(places, dry_run=True)
            self.stdout.write(
                self.style.WARNING("Dry run: the database was not modified.")
            )
        else:
            summary = import_places(places, dry_run=False)

        self._report(summary, places)

    def _resolve_center(self, options):
        latitude = options.get("lat")
        longitude = options.get("lng")

        if latitude is not None and longitude is not None:
            return float(latitude), float(longitude)

        if latitude is not None or longitude is not None:
            raise CommandError("--lat and --lng must be given together.")

        if options.get("location"):
            try:
                area = geocode_area(
                    requests.Session(), options["location"]
                )
            except LocationResolutionError as exc:
                raise CommandError(str(exc)) from exc

            return (
                (area.south + area.north) / 2.0,
                (area.west + area.east) / 2.0,
            )

        # The same default as the map: the centre of Guadalajara.
        return (
            float(settings.MAP_DEFAULT_CENTER[0]),
            float(settings.MAP_DEFAULT_CENTER[1]),
        )

    def _report(self, summary, places):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import finished:"))
        self.stdout.write(f"  created:  {summary.created}")
        self.stdout.write(f"  updated:  {summary.updated}")
        self.stdout.write(f"  unchanged: {summary.unchanged}")
        self.stdout.write(f"  skipped:  {len(summary.skipped)}")

        for reason in summary.skipped:
            self.stdout.write(self.style.WARNING(f"  skipped: {reason}"))

        for place in places:
            self.stdout.write(
                f"  - {place.place_id} {place.name} "
                f"({place.latitude}, {place.longitude})"
            )
