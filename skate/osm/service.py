"""High level service that ties the Overpass client and the importer together."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import requests

from .areas import Area, build_geocode_area_filter, geocode_area
from .client import OverpassClient, build_overpass_query
from .exceptions import OverpassQueryError
from .parser import ALL_TAG_FILTERS, ParsedSpot, parse_elements

logger = logging.getLogger(__name__)


def fetch_skateparks(
    location: str,
    bbox: Optional[str] = None,
    client: Optional[OverpassClient] = None,
    session: Optional[requests.Session] = None,
) -> Tuple[List[ParsedSpot], List[str], str]:
    """Fetch and normalise the skateparks of a geographic area.

    The Overpass ``geocodeArea`` specialiser is tried first. Some
    Overpass instances reject it, in which case the place is geocoded
    with Nominatim and the query is run against the resulting bounding
    box.

    Args:
        location: A free form place name.
        bbox: An explicit ``south,west,north,east`` bounding box. When
            given, no area resolution is needed at all.
        client: Optional :class:`OverpassClient` instance.
        session: Optional session used for the Nominatim request.

    Returns:
        A three-tuple ``(spots, skipped, area_description)``.
    """
    client = client or OverpassClient()
    session = session or requests.Session()

    if bbox:
        area = Area.from_bbox(location or bbox, bbox)
        query = build_overpass_query(area.bbox, ALL_TAG_FILTERS)
        elements = client.fetch_elements(query)
        spots, skipped = parse_elements(elements)
        return spots, skipped, f"bounding box {area.bbox}"

    geocode_query = build_overpass_query(
        "area.searchArea",
        ALL_TAG_FILTERS,
        prelude=build_geocode_area_filter(location),
    )

    try:
        elements = client.fetch_elements(geocode_query)
    except OverpassQueryError as exc:
        logger.warning(
            "The Overpass instance rejected geocodeArea (%s). "
            "Falling back to a geocoded bounding box.",
            exc,
        )
        area = geocode_area(session, location)
        query = build_overpass_query(area.bbox, ALL_TAG_FILTERS)
        elements = client.fetch_elements(query)
        spots, skipped = parse_elements(elements)
        return spots, skipped, f"{location} (bbox {area.bbox})"

    spots, skipped = parse_elements(elements)
    return spots, skipped, f"{location} (geocodeArea)"
