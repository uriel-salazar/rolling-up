"""Normalise raw Google Places (New) results into skatepark records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils import timezone

from .client import iter_photos

CATEGORY_SKATEPARK = "skatepark"
GOOGLE_ATTRIBUTION = "Google Places"
GOOGLE_LICENSE = "Google Maps Platform Terms of Service"

MAX_NAME_LENGTH = 200


@dataclass
class ParsedPlace:
    """A skatepark returned by Google Places."""

    place_id: str
    name: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    photos: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "place_id": self.place_id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "rating": self.rating,
            "user_rating_count": self.user_rating_count,
            "photos": list(self.photos),
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ParsedPlace {self.place_id} {self.name!r}>"


def parse_place(place: Dict[str, Any]) -> Optional[ParsedPlace]:
    """Turn one raw Google place into a :class:`ParsedPlace`.

    Returns ``None`` when the place has no id, no name or no usable
    coordinates. A place whose business status is not operational is
    also ignored, so closed skateparks are not added to the feed.
    """
    if not isinstance(place, dict):
        return None

    place_id = place.get("id")
    if not isinstance(place_id, str) or not place_id.strip():
        return None

    name = _display_name(place)
    if not name:
        return None

    location = place.get("location")
    if not isinstance(location, dict):
        return None

    try:
        latitude = float(location.get("latitude"))
        longitude = float(location.get("longitude"))
    except (TypeError, ValueError):
        return None

    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None

    status = place.get("businessStatus")
    if status and status not in {"OPERATIONAL", "BUSINESS_STATUS_UNSPECIFIED"}:
        return None

    photos = [_normalise_photo(photo) for photo in iter_photos(place)]
    photos = [photo for photo in photos if photo is not None]

    rating = _as_float(place.get("rating"))
    user_rating_count = _as_int(place.get("userRatingCount"))
    address = place.get("formattedAddress")
    if address is not None:
        address = str(address).strip() or None

    now = timezone.now()
    expires_at = now + timedelta(
        seconds=int(settings.GOOGLE_PLACES_DATA_TTL_SECONDS)
    )

    metadata = {
        "provider": "google",
        "place_id": place_id,
        "display_name": name,
        "formatted_address": address,
        "rating": rating,
        "user_rating_count": user_rating_count,
        "location": {"latitude": latitude, "longitude": longitude},
        "photos": photos,
        "attribution": GOOGLE_ATTRIBUTION,
        "license": GOOGLE_LICENSE,
        "google_maps_uri": place.get("googleMapsUri"),
        "website": place.get("websiteUri"),
        "primary_type": place.get("primaryType"),
        "types": place.get("types") if isinstance(place.get("types"), list) else [],
        "fetched_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "cache_ttl_seconds": int(settings.GOOGLE_PLACES_DATA_TTL_SECONDS),
    }

    return ParsedPlace(
        place_id=place_id,
        name=name[:MAX_NAME_LENGTH],
        latitude=latitude,
        longitude=longitude,
        address=address,
        rating=rating,
        user_rating_count=user_rating_count,
        photos=photos,
        metadata=metadata,
    )


def parse_places(places: List[Dict[str, Any]]) -> List[ParsedPlace]:
    """Normalise a list of raw Google places, dropping unusable ones."""
    parsed: List[ParsedPlace] = []
    seen: set[str] = set()

    for place in places:
        item = parse_place(place)
        if item is None or item.place_id in seen:
            continue
        seen.add(item.place_id)
        parsed.append(item)

    return parsed


def _display_name(place: Dict[str, Any]) -> Optional[str]:
    display_name = place.get("displayName")
    if isinstance(display_name, dict):
        text = display_name.get("text")
        if text:
            return str(text).strip() or None
    if isinstance(display_name, str):
        return display_name.strip() or None
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalise_photo(photo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = photo.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    attributions = []
    raw_attributions = photo.get("authorAttributions")
    if isinstance(raw_attributions, list):
        for item in raw_attributions:
            if not isinstance(item, dict):
                continue
            display = item.get("displayName")
            uri = item.get("uri")
            if display or uri:
                attributions.append(
                    {
                        "name": str(display).strip() if display else None,
                        "uri": uri,
                    }
                )

    attribution = ", ".join(
        item["name"] for item in attributions if item.get("name")
    ) or None

    return {
        "name": name.strip(),
        "width": _as_int(photo.get("widthPx")),
        "height": _as_int(photo.get("heightPx")),
        "attribution": attribution,
        "attribution_url": next(
            (item["uri"] for item in attributions if item.get("uri")), None
        ),
        "attributions": attributions,
        "source": "Google Places",
    }
