"""High level discovery service for Google Places (New)."""

from __future__ import annotations

import logging
from typing import List, Optional

from django.conf import settings

from .client import GooglePlacesClient
from .parser import ParsedPlace, parse_places

logger = logging.getLogger(__name__)


def discover_skateparks(
    latitude: float,
    longitude: float,
    radius: Optional[int] = None,
    max_results: Optional[int] = None,
    client: Optional[GooglePlacesClient] = None,
) -> List[ParsedPlace]:
    """Return the actual skateparks around a point.

    The search is restricted to ``includedTypes: ["skateboard_park"]``,
    so plazas, generic parks, courts and other skateboarding places are
    not returned.
    """
    client = client or GooglePlacesClient()

    raw_places = client.search_all(
        latitude,
        longitude,
        radius=radius
        if radius is not None
        else settings.GOOGLE_PLACES_SEARCH_RADIUS,
        max_results=max_results,
    )

    places = parse_places(raw_places)
    logger.info(
        "Google Places returned %s skatepark(s) around %s,%s.",
        len(places),
        latitude,
        longitude,
    )
    return places
