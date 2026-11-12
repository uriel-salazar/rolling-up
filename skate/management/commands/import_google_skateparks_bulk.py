"""Bulk import Google Places skateparks across a set of cities."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

DEFAULT_CITIES = [
    "Mexico City, Mexico",
    "Guadalajara, Jalisco, Mexico",
    "Monterrey, Nuevo León, Mexico",
    "Puebla, Puebla, Mexico",
    "Tijuana, Baja California, Mexico",
    "León, Guanajuato, Mexico",
    "Querétaro, Querétaro, Mexico",
    "Toluca, Estado de México, Mexico",
    "Mérida, Yucatán, Mexico",
    "Cancún, Quintana Roo, Mexico",
    "Chihuahua, Chihuahua, Mexico",
    "San Luis Potosí, San Luis Potosí, Mexico",
]


class Command(BaseCommand):
    help = (
        "Import Google Places skateparks for a list of cities, or the default "
        "set of major Mexican metro areas."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--cities",
            nargs="+",
            default=[],
            help=(
                "Specific cities to import, for example: "
                "--cities \"Mexico City, Mexico\" \"Guadalajara, Jalisco, Mexico\""
            ),
        )
        parser.add_argument(
            "--radius",
            type=int,
            default=10000,
            help="Search radius in metres for each city (default: 10000).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the search without writing to the database.",
        )

    def handle(self, *args, **options):
        cities = options["cities"] or DEFAULT_CITIES

        for city in cities:
            self.stdout.write(self.style.HTTP_INFO(f"\n=== {city} ==="))
            call_command(
                "import_google_skateparks",
                location=city,
                radius=options["radius"],
                dry_run=options["dry_run"],
            )
