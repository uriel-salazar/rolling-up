"""Persist the skateparks discovered with Google Places (New).

Google content is cached for a bounded amount of time (30 days by
default) and the application never downloads the photographs into its
own storage: the photo proxy asks Google for the bytes on demand. A new
import refreshes the cached fields and the timestamp.

The importer deduplicates the results against the spots that are
already in the database, so an OpenStreetMap skatepark that Google also
knows about does not appear twice. The identifiers of every provider
are kept.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings
from django.db import transaction

from ..dedupe import find_matching_spot as find_nearby_spot
from ..models import Spots
from ..osm.importer import get_or_create_service_user
from .parser import ParsedPlace

logger = logging.getLogger(__name__)

COORDINATE_QUANTUM = Decimal("0.000001")


@dataclass
class ImportSummary:
    """Counters describing what a Google import run did."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": len(self.skipped),
        }


def to_decimal(value: Optional[float]) -> Optional[Decimal]:
    """Quantise a coordinate to the precision of the model column."""
    if value is None:
        return None
    return Decimal(str(value)).quantize(COORDINATE_QUANTUM, rounding=ROUND_HALF_UP)


def import_places(
    places: Iterable[ParsedPlace],
    dry_run: bool = False,
) -> ImportSummary:
    """Create or refresh the skateparks returned by Google Places."""
    summary = ImportSummary()
    places = list(places)

    if dry_run:
        return _plan_import(places, summary)

    service_user = get_or_create_service_user()

    with transaction.atomic():
        for place in places:
            try:
                outcome = _save_place(place, service_user)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Could not import Google place %s: %s", place.place_id, exc
                )
                summary.skipped.append(
                    f"Google place {place.place_id} could not be saved: {exc}"
                )
                continue

            if outcome == "created":
                summary.created += 1
            elif outcome == "updated":
                summary.updated += 1
            else:
                summary.unchanged += 1

    return summary


def _plan_import(places: List[ParsedPlace], summary: ImportSummary) -> ImportSummary:
    for place in places:
        existing = Spots.objects.filter(google_place_id=place.place_id).first()
        if existing is None:
            existing = find_matching_spot(place)

        if existing is None:
            summary.created += 1
        elif _google_fields_changed(existing, place):
            summary.updated += 1
        else:
            summary.unchanged += 1

    return summary


def find_matching_spot(place: ParsedPlace) -> Optional[Spots]:
    """Return the spot that already represents the same skatepark."""
    return find_nearby_spot(
        place.name,
        place.latitude,
        place.longitude,
        float(settings.GOOGLE_PLACES_DEDUPE_RADIUS_METERS),
        Spots.objects.exclude(google_place_id=place.place_id),
    )


def _save_place(place: ParsedPlace, service_user) -> str:
    existing = Spots.objects.filter(google_place_id=place.place_id).first()
    if existing is None:
        existing = find_matching_spot(place)

    if existing is None:
        Spots.objects.create(
            name_spot=place.name,
            body=None,
            latitude=to_decimal(place.latitude),
            longitude=to_decimal(place.longitude),
            category=Spots.CATEGORY_SKATEPARK,
            source=Spots.SOURCE_GOOGLE,
            google_place_id=place.place_id,
            google_metadata=place.metadata,
            user=service_user,
        )
        logger.info("Imported Google place %s as '%s'.", place.place_id, place.name)
        return "created"

    return _refresh_place(existing, place)


def _refresh_place(existing: Spots, place: ParsedPlace) -> str:
    changed_fields = []

    if existing.google_place_id != place.place_id:
        existing.google_place_id = place.place_id
        changed_fields.append("google_place_id")

    if existing.google_metadata != place.metadata:
        existing.google_metadata = place.metadata
        changed_fields.append("google_metadata")

    # The provider data fills only the gaps an OSM or community record
    # may have. A name, a description or a picture written by a user is
    # never overwritten.
    if existing.latitude is None:
        existing.latitude = to_decimal(place.latitude)
        changed_fields.append("latitude")

    if existing.longitude is None:
        existing.longitude = to_decimal(place.longitude)
        changed_fields.append("longitude")

    if (
        existing.source != Spots.SOURCE_COMMUNITY
        and existing.category != Spots.CATEGORY_SKATEPARK
    ):
        existing.category = Spots.CATEGORY_SKATEPARK
        changed_fields.append("category")

    if not changed_fields:
        return "unchanged"

    existing.save(update_fields=changed_fields)
    logger.info(
        "Updated Google place %s on spot %s (%s).",
        place.place_id,
        existing.pk,
        ", ".join(changed_fields),
    )
    return "updated"


def _google_fields_changed(existing: Spots, place: ParsedPlace) -> bool:
    if existing.google_place_id != place.place_id:
        return True
    if existing.google_metadata != place.metadata:
        return True
    if existing.latitude is None or existing.longitude is None:
        return True
    if existing.source == Spots.SOURCE_COMMUNITY:
        return False
    return existing.category != Spots.CATEGORY_SKATEPARK
