"""Shared helpers to recognise the same skatepark across providers."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Optional

EARTH_RADIUS_METERS = 6371000.0
NON_WORD = re.compile(r"[^0-9a-z]+")

GENERIC_WORDS = {
    "skate", "skatepark", "skateparks", "park", "plaza", "spot",
    "the", "de", "del", "la", "las", "el", "los", "y",
}


def normalise_name(value: Optional[str]) -> str:
    """Return a comparable form of a skatepark name."""
    if not value:
        return ""

    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = NON_WORD.sub(" ", text.casefold())

    words = sorted(word for word in text.split() if word)
    meaningful = [word for word in words if word not in GENERIC_WORDS]

    return " ".join(meaningful or words)


def distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the haversine distance between two points in metres."""
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)

    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(value)))


def find_matching_spot(
    name: Optional[str],
    latitude: float,
    longitude: float,
    radius: float,
    queryset: Any,
) -> Any:
    """Return the closest record that represents the same skatepark.

    A matching name inside the radius is enough. Without a matching
    name only a record that sits almost on the same point is merged, so
    two different skateparks in one park are kept apart.
    """
    latitude = float(latitude)
    longitude = float(longitude)
    radius = float(radius)

    lat_delta = radius / 111320.0
    cos_latitude = max(math.cos(math.radians(latitude)), 0.01)
    lon_delta = radius / (111320.0 * cos_latitude)

    candidates = queryset.filter(
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=latitude - lat_delta,
        latitude__lte=latitude + lat_delta,
        longitude__gte=longitude - lon_delta,
        longitude__lte=longitude + lon_delta,
    )

    wanted_name = normalise_name(name)
    best = None
    best_distance = float("inf")

    for candidate in candidates:
        distance = distance_meters(
            latitude,
            longitude,
            float(candidate.latitude),
            float(candidate.longitude),
        )
        if distance > radius:
            continue

        same_name = wanted_name and wanted_name == normalise_name(
            candidate.name_spot
        )

        if same_name or distance <= min(25.0, radius / 3.0):
            if distance < best_distance:
                best = candidate
                best_distance = distance

    return best
