"""Normalise raw Overpass elements into importable skatepark records.

This module is intentionally free of any Django model dependency: it
turns raw Overpass JSON into plain dictionaries that the importer can
persist. That keeps the parsing rules easy to test in isolation.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

from .exceptions import OverpassRequestError

logger = logging.getLogger(__name__)

# Tag filters sent to Overpass.
#
# Only objects that are explicitly tagged as a skatepark are requested.
# A ``sport=skateboard`` object can be a single ramp, a plaza or a
# sports centre, so it is not an actual skatepark and is intentionally
# left out of the discovery query.
SKATEPARK_TAG_FILTERS = [{"key": "leisure", "value": "skatepark"}]
ALL_TAG_FILTERS = list(SKATEPARK_TAG_FILTERS)

# Keys used to find a photograph and the information that has to be
# displayed next to it.
IMAGE_TAG_KEYS = ("image", "image:0", "image:1", "image:2")
WIKIMEDIA_TAG_KEYS = ("wikimedia_commons",)
IMAGE_LICENSE_KEYS = (
    "image:license",
    "image:licence",
    "license",
    "licence",
    "image:license:url",
    "image:licence:url",
    "license:url",
    "licence:url",
)
IMAGE_LICENSE_URL_KEYS = (
    "image:license:url",
    "image:licence:url",
    "license:url",
    "licence:url",
)
IMAGE_ATTRIBUTION_KEYS = (
    "image:attribution",
    "image:attribution:url",
    "attribution",
    "artist",
    "photographer",
    "author",
    "image:author",
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
    image = extract_image(tags)

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

    # The photograph is optional. It is kept in its own block so the
    # resolver can use it without having to know the raw tag names.
    if image is not None:
        metadata["image"] = image

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

    Only objects explicitly tagged ``leisure=skatepark`` are accepted.
    A ``sport=skateboard`` tag is not enough: it can describe a single
    ramp, a plaza, a shop or a sports centre, none of which is an
    actual skatepark record.
    """
    leisure = (tags.get("leisure") or "").strip().lower()
    return leisure == "skatepark"


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


def _first_tag(tags: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    """Return the trimmed value of the first tag that has one."""
    for key in keys:
        value = tags.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalise_image_url(value: Optional[str]) -> Optional[str]:
    """Return an http(s) image URL, or ``None`` when it is not usable."""
    if not value:
        return None

    url = value.strip()
    if not url:
        return None

    # Some mappers write several URLs in one tag. The first one is the
    # photograph, the rest are usually categories or mirrors.
    if ";" in url:
        url = url.split(";", 1)[0].strip()

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return url


def _wikimedia_image_url(value: Optional[str]) -> Optional[str]:
    """Turn a ``wikimedia_commons`` tag into a direct file URL."""
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    if text.lower().startswith(("http://", "https://")):
        return _normalise_image_url(text)

    # ``wikimedia_commons`` normally holds ``File:Name.jpg``. A
    # category does not identify a single photograph, so it is ignored.
    if text.lower().startswith("file:"):
        file_name = text.split(":", 1)[1].strip()
        if not file_name:
            return None
        return (
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            + quote(file_name, safe="")
        )

    return None


def extract_image(tags: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the photograph of a skatepark described by OSM tags.

    The function never guesses a picture: it only returns a URL that is
    explicitly referenced by the object. The licence and the
    attribution are kept when the mapper supplied them.
    """
    tag_value = _first_tag(tags, IMAGE_TAG_KEYS)
    url = _normalise_image_url(tag_value)
    from_wikimedia = False

    if url is None:
        url = _wikimedia_image_url(_first_tag(tags, WIKIMEDIA_TAG_KEYS))
        from_wikimedia = url is not None

    if url is None:
        return None

    license_name = _first_tag(tags, IMAGE_LICENSE_KEYS)
    license_url = _first_tag(tags, IMAGE_LICENSE_URL_KEYS)
    attribution = _first_tag(tags, IMAGE_ATTRIBUTION_KEYS)

    if from_wikimedia:
        if not license_name:
            license_name = "See the Wikimedia Commons file page"
        if not attribution:
            attribution = "Wikimedia Commons"

    # A photograph without any licence or credit is not used by the
    # application, even when the URL looks valid. The raw tags are still
    # available in the metadata block.
    usable = bool(license_name or attribution or from_wikimedia)

    return {
        "url": url,
        "attribution": attribution,
        "license": license_name,
        "license_url": license_url,
        "source": "OpenStreetMap",
        "usable": usable,
    }


def ensure_elements(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the elements of a raw Overpass payload."""
    if not isinstance(payload, dict) or "elements" not in payload:
        raise OverpassRequestError("The Overpass payload has no 'elements' key.")
    elements = payload["elements"]
    if not isinstance(elements, list):
        raise OverpassRequestError("The Overpass payload has an invalid 'elements'.")
    return [element for element in elements if isinstance(element, dict)]
