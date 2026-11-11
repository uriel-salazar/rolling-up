"""Persist the skateparks parsed from OpenStreetMap into the database.

The importer only ever touches records it owns: a row is updated when
its ``osm_type`` / ``osm_id`` pair matches. Community submitted spots
are never read for writing and are never modified. User generated data
(photos, ratings, edited descriptions) is preserved as well.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings
from django.db import transaction

from ..models import Spots, User
from .parser import ParsedSpot

logger = logging.getLogger(__name__)

# The coordinates are stored in DecimalField columns with six decimal
# places. The incoming values are floats, so they are quantised the same
# way before being stored. Without this a value read back from the
# database would never compare equal to the float it came from and
# every re-import would be reported as an update.
COORDINATE_QUANTUM = Decimal("0.000001")


def to_decimal(value: Optional[float]) -> Optional[Decimal]:
    """Quantise a coordinate to the precision used by the model."""
    if value is None:
        return None
    return Decimal(str(value)).quantize(COORDINATE_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass
class ImportSummary:
    """Counters describing what an import run did."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: List[str] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.created + self.updated + self.unchanged

    def as_dict(self) -> Dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": len(self.skipped),
        }


def get_or_create_service_user() -> User:
    """Return the service account that owns the imported skateparks.

    The ``Spots.user`` relation is mandatory, so imported records need
    an owner. A dedicated account with an unusable password is used: it
    cannot be logged into and therefore cannot be used to edit the
    records through the API.
    """
    username = settings.OSM_SERVICE_USER
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": f"{username}@rollingup.invalid",
            "is_active": True,
            "is_staff": False,
        },
    )

    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        logger.info("Created the OSM service account '%s'.", username)

    return user


def import_spots(
    spots: Iterable[ParsedSpot],
    dry_run: bool = False,
) -> ImportSummary:
    """Write the parsed skateparks to the database.

    Args:
        spots: The skateparks to import.
        dry_run: When true nothing is written to the database.

    Returns:
        An :class:`ImportSummary` describing the run.
    """
    summary = ImportSummary()
    spots = list(spots)

    if dry_run:
        return _plan_import(spots, summary)

    service_user = get_or_create_service_user()

    with transaction.atomic():
        for spot in spots:
            try:
                outcome = _save_spot(spot, service_user)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Could not import OSM %s %s: %s", spot.osm_type, spot.osm_id, exc
                )
                summary.skipped.append(
                    f"{spot.osm_type} {spot.osm_id} could not be saved: {exc}"
                )
                continue

            if outcome == "created":
                summary.created += 1
            elif outcome == "updated":
                summary.updated += 1
            else:
                summary.unchanged += 1

    return summary


def _plan_import(spots: List[ParsedSpot], summary: ImportSummary) -> ImportSummary:
    """Report what an import would do without touching the database."""
    existing = {
        (row.osm_type, row.osm_id)
        for row in Spots.objects.filter(
            osm_id__isnull=False,
            osm_type__in={spot.osm_type for spot in spots},
        )
    }

    for spot in spots:
        key = (spot.osm_type, spot.osm_id)
        if key in existing:
            summary.updated += 1
        else:
            summary.created += 1

    return summary


def _save_spot(spot: ParsedSpot, service_user: User) -> str:
    """Create or refresh a single skatepark.

    Returns:
        ``"created"``, ``"updated"`` or ``"unchanged"``.
    """
    defaults = {
        "name_spot": spot.name,
        "body": spot.description,
        "latitude": to_decimal(spot.latitude),
        "longitude": to_decimal(spot.longitude),
        "category": spot.category,
        "osm_metadata": spot.metadata,
        "source": Spots.SOURCE_OSM,
    }

    existing = Spots.objects.filter(
        osm_type=spot.osm_type, osm_id=spot.osm_id
    ).first()

    if existing is None:
        Spots.objects.create(
            osm_type=spot.osm_type,
            osm_id=spot.osm_id,
            user=service_user,
            **defaults,
        )
        logger.info(
            "Imported OSM %s %s as '%s'.", spot.osm_type, spot.osm_id, spot.name
        )
        return "created"

    return _refresh_spot(existing, spot, defaults)


def _refresh_spot(
    existing: Spots, spot: ParsedSpot, defaults: Dict[str, Any]
) -> str:
    """Update the OSM derived fields of an existing record.

    The description is only overwritten when it still matches the
    description that was originally imported, so a description edited
    by a user is never lost. The photo is never touched.
    """
    changed_fields = []

    if existing.name_spot != defaults["name_spot"]:
        existing.name_spot = defaults["name_spot"]
        changed_fields.append("name_spot")

    if _body_should_be_updated(existing, spot.description):
        new_body = defaults["body"]
        if existing.body != new_body:
            existing.body = new_body
            changed_fields.append("body")

    if existing.latitude != defaults["latitude"]:
        existing.latitude = defaults["latitude"]
        changed_fields.append("latitude")

    if existing.longitude != defaults["longitude"]:
        existing.longitude = defaults["longitude"]
        changed_fields.append("longitude")

    if existing.category != defaults["category"]:
        existing.category = defaults["category"]
        changed_fields.append("category")

    if existing.osm_metadata != defaults["osm_metadata"]:
        existing.osm_metadata = defaults["osm_metadata"]
        changed_fields.append("osm_metadata")

    if existing.source != defaults["source"]:
        existing.source = defaults["source"]
        changed_fields.append("source")

    if not changed_fields:
        return "unchanged"

    existing.save(update_fields=changed_fields)
    logger.info(
        "Updated OSM %s %s (%s).",
        spot.osm_type,
        spot.osm_id,
        ", ".join(changed_fields),
    )
    return "updated"


def _body_should_be_updated(existing: Spots, new_description: Optional[str]) -> bool:
    """Decide whether the stored description may be overwritten.

    The stored body is only replaced when it still holds the description
    that came from OpenStreetMap. A body edited by a user is preserved.
    """
    if new_description is None:
        # Nothing new to write: keep whatever is stored.
        return False

    if existing.body is None:
        return True

    previous = (existing.osm_metadata or {}).get("description")
    if previous is None:
        # The record has no tracked OSM description, so the current body
        # was most likely written by a user: keep it.
        return False

    return existing.body == previous


def get_osm_spots() -> Any:
    """Return the query set with every imported skatepark."""
    return Spots.objects.filter(source=Spots.SOURCE_OSM)


def get_community_spots() -> Any:
    """Return the query set with every community submitted skatepark."""
    return Spots.objects.filter(source=Spots.SOURCE_COMMUNITY)
