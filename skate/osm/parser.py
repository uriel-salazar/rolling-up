"""Normalise raw Overpass elements into importable skatepark records.

This module is intentionally free of any Django model dependency: it
turns raw Overpass JSON into plain dictionaries that the importer can
persist. That keeps the parsing rules easy to test in isolation.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import OverpassRequestError

logger = logging.getLogger(__name__)

# Tag filters sent to Overpass.
SKATEPARK_TAG_FILTERS = [{"key": "leisure", "value": "skatepark"}]
SKATEBOARD_TAG_FILTERS = [{"key": "sport", "value": "skateboard"}]
ALL_TAG_FILTERS = SKATEPARK_TAG_FILTERS + SKATEBOARD_TAG_FILTERS

# ``leisure`` values that describe a place where skateboarding may
# happen. Used to decide whether a ``sport=skateboard`` object really is
# a skatepark and not, say, a single half pipe inside a sports centre.
SKATEPARK_FRIENDLY_LEISURE = frozenset(
    {
        "skatepark",
        "sports_centre",
        "sports_center",
        "park",
        "recreation_ground",
    }
)

# Keywords used to recognise a skatepark by name or description.
SKATEPARK_KEYWORDS = re.compile(
    r"skate\s*-?\s*park|skatepark|skate\s*plaza|skate\s*bowl|skate\s*park|patinaje|skate",
    re.IGNORECASE,
)

# Maximum length of the model fields the OSM data is written into.
MAX_NAME_LENGTH = 200
MAX_BODY_LENGTH = 1000

OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_LICENSE = "ODbL-1.0"

# The kinds of spot. They match the choices of the ``category`` field of
# the spot model.
CATEGORY_SKATEPARK = "skatepark"
CATEGORY_STREET = "street"


class ParsedSpot:
    """A single skatepark ready to be written to the database."""

    __slots__ = (
        "osm_id",
        "osm_type",
        "name",
        "description",
        "latitude",
        "longitude",
        "category",
        "metadata",
    )

    def __init__(
        self,
        osm_id: int,
        osm_type: str,
        name: str,
        description: Optional[str],
        latitude: float,
        longitude: float,
        category: str,
        metadata: Dict[str, Any],
    ) -> None:
        self.osm_id = osm_id
        self.osm_type = osm_type
        self.name = name
        self.description = description
        self.latitude = latitude
        self.longitude = longitude
        self.category = category
        self.metadata = metadata

    def as_dict(self) -> Dict[str, Any]:
        """Return the spot as a plain dictionary."""
        return {
            "osm_id": self.osm_id,
            "osm_type": self.osm_type,
            "name": self.name,
            "description": self.description,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "category": self.category,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ParsedSpot {self.osm_type}/{self.osm_id} {self.name!r}>"


def parse_elements(elements: List[Dict[str, Any]]) -> Tuple[List[ParsedSpot], List[str]]:
    """Parse a list of Overpass elements.

    Args:
        elements: The raw elements returned by the Overpass API.

    Returns:
        A two-tuple ``(spots, skipped)`` where ``spots`` holds the
        skateparks that can be imported and ``skipped`` holds one
        human readable reason per element that was discarded.
    """
    spots: List[ParsedSpot] = []
    skipped: List[str] = []

    for element in elements:
        spot, reason = parse_element(element)
        if spot is None:
            skipped.append(reason)
        else:
            spots.append(spot)

    return spots, skipped


def parse_element(element: Dict[str, Any]) -> Tuple[Optional[ParsedSpot], str]:
    """Parse a single Overpass element.

    Args:
        element: A raw Overpass element.

    Returns:
        A two-tuple ``(spot, reason)``. ``spot`` is ``None`` when the
        element cannot be imported and ``reason`` then explains why.
    """
    osm_type = element.get("type")
    osm_id = element.get("id")

    if osm_type not in {"node", "way", "relation"}:
        return None, f"Unsupported OSM object type: {osm_type!r}"

    if not isinstance(osm_id, int):
        return None, f"Missing or invalid OSM id for {osm_type}: {osm_id!r}"

    tags = element.get("tags") or {}
    if not isinstance(tags, dict):
        return None, f"Invalid tags for {osm_type} {osm_id}"

    if not is_skatepark(tags):
        return None, f"{osm_type} {osm_id} is not tagged as a skatepark"

    coordinates = extract_coordinates(element)
    if coordinates is None:
        return None, f"{osm_type} {osm_id} has no usable coordinates"
    latitude, longitude = coordinates

    name = build_name(tags, osm_type, osm_id)
    description = extract_description(tags)
    category = detect_category(tags)

    metadata = {
        "tags": dict(tags),
        "access": tags.get("access"),
        "surface": tags.get("surface"),
        "lit": tags.get("lit"),
        "operator": tags.get("operator"),
        "website": extract_website(tags),
        "description": description,
        "category": category,
        "attribution": OSM_ATTRIBUTION,
        "license": OSM_LICENSE,
    }

    return (
        ParsedSpot(
            osm_id=osm_id,
            osm_type=osm_type,
            name=name,
            description=description,
            latitude=latitude,
            longitude=longitude,
            category=category,
            metadata=metadata,
        ),
        "",
    )


def detect_category(tags: Dict[str, Any]) -> str:
    """Return the kind of skatepark the OpenStreetMap tags describe.

    A place tagged ``leisure=skatepark`` is a skatepark. A place that
    calls itself a skatepark in its name or in its description is one
    too, which happens with the ways that are mapped as a pitch or as a
    sports centre. Everything else that is tagged for skateboarding is
    a street spot.

    The values match the choices of the ``category`` field of the spot.
    """
    leisure = (tags.get("leisure") or "").strip().lower()

    if leisure == "skatepark":
        return CATEGORY_SKATEPARK

    for key in ("name", "description", "note"):
        value = tags.get(key)
        if value and SKATEPARK_KEYWORDS.search(str(value)):
            return CATEGORY_SKATEPARK

    return CATEGORY_STREET


def is_skatepark(tags: Dict[str, Any]) -> bool:
    """Decide whether the given OSM tags describe a skatepark.

    Objects tagged ``leisure=skatepark`` are always accepted. Objects
    tagged ``sport=skateboard`` are only accepted when they also look
    like a skatepark, so that unrelated objects (a single ramp, a
    playground, a basketball court) are not imported.
    """
    leisure = (tags.get("leisure") or "").strip().lower()
    sport = (tags.get("sport") or "").strip().lower()

    if leisure == "skatepark":
        return True

    if sport != "skateboard":
        return False

    if leisure in SKATEPARK_FRIENDLY_LEISURE:
        return True

    # No ``leisure`` tag: fall back to the name and description so a
    # genuinely named skatepark is not lost.
    for key in ("name", "description", "note", "operator"):
        value = tags.get(key)
        if value and SKATEPARK_KEYWORDS.search(str(value)):
            return True

    return False


def extract_coordinates(
    element: Dict[str, Any]
) -> Optional[Tuple[float, float]]:
    """Extract a ``(latitude, longitude)`` pair from an Overpass element.

    Nodes carry ``lat``/``lon`` directly. Ways and relations are queried
    with ``out center``, so their centroid is available under ``center``.
    """
    latitude = element.get("lat")
    longitude = element.get("lon")

    if latitude is None or longitude is None:
        center = element.get("center")
        if isinstance(center, dict):
            latitude = center.get("lat")
            longitude = center.get("lon")

    if latitude is None or longitude is None:
        return None

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return None

    if not (-90.0 <= latitude <= 90.0):
        return None
    if not (-180.0 <= longitude <= 180.0):
        return None

    return latitude, longitude


def build_name(tags: Dict[str, Any], osm_type: str, osm_id: int) -> str:
    """Return the display name of a skatepark.

    Objects without a ``name`` tag are given a clearly labelled
    placeholder instead of an invented name.
    """
    raw_name = tags.get("name")
    if raw_name:
        name = str(raw_name).strip()
        if name:
            return name[:MAX_NAME_LENGTH]

    return f"Unnamed skatepark ({osm_type} {osm_id})"[:MAX_NAME_LENGTH]


def extract_description(tags: Dict[str, Any]) -> Optional[str]:
    """Return the best available description for a skatepark."""
    for key in ("description", "note"):
        value = tags.get(key)
        if value:
            description = str(value).strip()
            if description:
                return description[:MAX_BODY_LENGTH]
    return None


def extract_website(tags: Dict[str, Any]) -> Optional[str]:
    """Return the website of a skatepark when one is tagged."""
    for key in ("website", "contact:website", "url", "contact:url"):
        value = tags.get(key)
        if value:
            website = str(value).strip()
            if website:
                return website
    return None


def ensure_elements(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the elements of a raw Overpass payload."""
    if not isinstance(payload, dict) or "elements" not in payload:
        raise OverpassRequestError("The Overpass payload has no 'elements' key.")
    elements = payload["elements"]
    if not isinstance(elements, list):
        raise OverpassRequestError("The Overpass payload has an invalid 'elements'.")
    return [element for element in elements if isinstance(element, dict)]
