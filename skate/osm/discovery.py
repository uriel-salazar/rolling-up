"""Live skatepark discovery through Overpass, without database writes.

The map and the feed need to show skateparks anywhere in the world. The
existing importer is intentionally not used here: a discovery request
only reads Overpass and returns normalized dictionaries, so external
results stay separate from the registered Rolling Up spots.

The service validates every geographic query, caches successful answers
and keeps a stale copy so a temporary Overpass outage does not empty the
map or the feed.
"""

from __future__ import annotations

import hashlib
import logging
import time
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.conf import settings
from django.core.cache import cache

from ..dedupe import distance_meters
from ..media_api.images_skateparks.resolver import (
    resolve_spot_address,
    resolve_spot_image,
)
from .client import OverpassClient, build_overpass_query
from .exceptions import OverpassError
from .parser import ParsedSpot, parse_elements

logger = logging.getLogger(__name__)

DISCOVERY_TAGS = [{"key": "leisure", "value": "skatepark"}]
OSM_ATTRIBUTION = "© OpenStreetMap contributors"


class DiscoveryError(Exception):
    """Base class for a live discovery error."""


class InvalidDiscoveryQuery(DiscoveryError):
    """The coordinates, radius or bounding box are not valid."""


class DiscoveryUnavailable(DiscoveryError):
    """Overpass could not be reached and no cached answer exists."""


def discover_nearby(
    latitude: float,
    longitude: float,
    radius: Optional[float] = None,
    limit: Optional[int] = None,
    client: Optional[OverpassClient] = None,
) -> Dict[str, Any]:
    """Discover skateparks around a point, without saving them."""
    latitude, longitude = _validated_point(latitude, longitude)
    radius = _validated_radius(radius)

    area = {
        "type": "radius",
        "latitude": latitude,
        "longitude": longitude,
        "radius": radius,
    }
    query = build_overpass_query(
        f"around:{radius:.0f},{latitude:.6f},{longitude:.6f}",
        DISCOVERY_TAGS,
    )
    key = _cache_key("nearby", latitude, longitude, radius, limit)

    return _discover(
        query=query,
        cache_key=key,
        center=(latitude, longitude),
        area=area,
        limit=limit,
        client=client,
    )


def discover_viewport(
    south: float,
    west: float,
    north: float,
    east: float,
    limit: Optional[int] = None,
    client: Optional[OverpassClient] = None,
) -> Dict[str, Any]:
    """Discover skateparks inside a viewport, without saving them."""
    south, west, north, east = _validated_viewport(south, west, north, east)

    center = ((south + north) / 2.0, (west + east) / 2.0)
    area = {
        "type": "viewport",
        "south": south,
        "west": west,
        "north": north,
        "east": east,
    }
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    query = build_overpass_query(bbox, DISCOVERY_TAGS)
    key = _cache_key("viewport", south, west, north, east, limit)

    return _discover(
        query=query,
        cache_key=key,
        center=center,
        area=area,
        limit=limit,
        client=client,
    )


def _discover(
    query: str,
    cache_key: str,
    center: Tuple[float, float],
    area: Dict[str, Any],
    limit: Optional[int],
    client: Optional[OverpassClient],
) -> Dict[str, Any]:
    now = time.time()
    cached = cache.get(cache_key)

    if _is_fresh(cached, now):
        return _payload(cached["results"], area, cached=True, stale=False)

    client = client or OverpassClient()

    try:
        elements = client.fetch_elements(query)
    except OverpassError as exc:
        if cached:
            logger.warning(
                "Overpass failed (%s); returning the cached discovery.", exc
            )
            return _payload(
                cached["results"], area, cached=True, stale=True
            )
        logger.warning("Overpass discovery failed without a cache: %s", exc)
        raise DiscoveryUnavailable(
            "The skatepark discovery service is temporarily unavailable."
        ) from exc

    spots, _skipped = parse_elements(elements)
    results = _normalise_spots(spots, center, limit)
    entry = {"fetched_at": now, "results": results}
    cache.set(cache_key, entry, settings.OVERPASS_DISCOVERY_STALE_SECONDS)

    return _payload(results, area, cached=False, stale=False)


def _normalise_spots(
    spots: Iterable[ParsedSpot],
    center: Tuple[float, float],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    maximum = _validated_limit(limit)
    by_osm_id: Dict[str, ParsedSpot] = {}

    for spot in spots:
        # OSM type + id is the stable identity of an external result.
        by_osm_id[f"{spot.osm_type}:{spot.osm_id}"] = spot

    ordered = sorted(
        by_osm_id.values(),
        key=lambda spot: distance_meters(
            center[0], center[1], spot.latitude, spot.longitude
        ),
    )

    return [_normalise_spot(spot) for spot in ordered[:maximum]]


def _normalise_spot(spot: ParsedSpot) -> Dict[str, Any]:
    # The existing image resolver expects attributes, not a Django model.
    # A small value object lets the exact same image rules be reused for
    # external results without writing anything to the database.
    value = SimpleNamespace(
        image_url=None,
        google_metadata=None,
        osm_metadata=spot.metadata,
    )
    image = resolve_spot_image(value) or {}

    return {
        "id": f"osm:{spot.osm_type}:{spot.osm_id}",
        "external": True,
        "name_spot": spot.name,
        "body": spot.description,
        "latitude": round(float(spot.latitude), 6),
        "longitude": round(float(spot.longitude), 6),
        "category": spot.category,
        "source": "osm",
        "osm_id": spot.osm_id,
        "osm_type": spot.osm_type,
        "osm_metadata": spot.metadata,
        "image_url": image.get("url"),
        "image_attribution": image.get("attribution"),
        "image_license": image.get("license"),
        "image_license_url": image.get("license_url"),
        "image_source": image.get("source"),
        "address": resolve_spot_address(value),
        "rating": None,
        "rating_count": 0,
    }


def _payload(
    results: List[Dict[str, Any]],
    area: Dict[str, Any],
    cached: bool,
    stale: bool,
) -> Dict[str, Any]:
    return {
        "source": "openstreetmap",
        "count": len(results),
        "results": list(results),
        "area": area,
        "cached": cached,
        "stale": stale,
        "attribution": OSM_ATTRIBUTION,
    }


def _is_fresh(cached: Optional[Dict[str, Any]], now: float) -> bool:
    if not isinstance(cached, dict) or not isinstance(cached.get("results"), list):
        return False
    fetched_at = cached.get("fetched_at")
    if not isinstance(fetched_at, (int, float)):
        return False
    return now - fetched_at <= settings.OVERPASS_DISCOVERY_CACHE_SECONDS


def _cache_key(*parts: Any) -> str:
    raw = "|".join(
        f"{part:.6f}" if isinstance(part, float) else str(part)
        for part in parts
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"osm:discovery:v1:{digest}"


def _validated_point(latitude: float, longitude: float) -> Tuple[float, float]:
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as exc:
        raise InvalidDiscoveryQuery(
            "Latitude and longitude must be numbers."
        ) from exc

    if not (-90.0 <= latitude <= 90.0):
        raise InvalidDiscoveryQuery("Latitude must be between -90 and 90.")
    if not (-180.0 <= longitude <= 180.0):
        raise InvalidDiscoveryQuery("Longitude must be between -180 and 180.")

    return latitude, longitude


def _validated_radius(radius: Optional[float]) -> float:
    try:
        value = float(
            settings.OVERPASS_DISCOVERY_DEFAULT_RADIUS
            if radius is None
            else radius
        )
    except (TypeError, ValueError) as exc:
        raise InvalidDiscoveryQuery("Radius must be a number.") from exc

    maximum = float(settings.OVERPASS_DISCOVERY_MAX_RADIUS)
    if value < 1 or value > maximum:
        raise InvalidDiscoveryQuery(
            f"Radius must be between 1 and {int(maximum)} metres."
        )
    return value


def _validated_viewport(
    south: float,
    west: float,
    north: float,
    east: float,
) -> Tuple[float, float, float, float]:
    try:
        south = float(south)
        west = float(west)
        north = float(north)
        east = float(east)
    except (TypeError, ValueError) as exc:
        raise InvalidDiscoveryQuery(
            "The bounding box must contain four numbers."
        ) from exc

    if not (-90.0 <= south <= 90.0) or not (-90.0 <= north <= 90.0):
        raise InvalidDiscoveryQuery("The latitude bounds are outside the map.")
    if not (-180.0 <= west <= 180.0) or not (-180.0 <= east <= 180.0):
        raise InvalidDiscoveryQuery("The longitude bounds are outside the map.")
    if south >= north or west >= east:
        raise InvalidDiscoveryQuery(
            "The bounding box must satisfy south < north and west < east."
        )

    span = float(settings.OVERPASS_DISCOVERY_MAX_VIEWPORT_SPAN)
    if (north - south) > span or (east - west) > span:
        raise InvalidDiscoveryQuery(
            "The visible area is too large. Zoom in before discovering spots."
        )

    return south, west, north, east


def _validated_limit(limit: Optional[int]) -> int:
    maximum = int(settings.OVERPASS_DISCOVERY_MAX_RESULTS)
    try:
        wanted = maximum if limit is None else int(limit)
    except (TypeError, ValueError):
        wanted = maximum
    return max(1, min(wanted, maximum))
