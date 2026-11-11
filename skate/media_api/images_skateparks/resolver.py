"""Resolve the photograph that belongs to a skate spot.

Only three sources are accepted, in this order:

1. a picture uploaded by a user (the existing ``image_url`` field),
2. the first photograph of the matching Google Places record,
3. an image explicitly tagged on the OpenStreetMap object.

A picture is never chosen at random and a spot without a usable picture
returns ``None`` so the existing placeholder stays in place.
"""

from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone
from typing import Any, Dict, Optional
from urllib.parse import quote

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def resolve_spot_image(spot: Any, request: Any = None) -> Optional[Dict[str, Any]]:
    """Return ``{url, attribution, license, license_url, source}`` or None."""
    local = _local_image(spot, request)
    if local is not None:
        return local

    google = _google_image(spot)
    if google is not None:
        return google

    return _osm_image(spot)


def resolve_spot_address(spot: Any) -> str:
    """Return the address of a spot, from Google or from OSM tags."""
    google_address = _google_address(spot)
    if google_address:
        return google_address

    metadata = getattr(spot, "osm_metadata", None) or {}
    tags = metadata.get("tags") if isinstance(metadata, dict) else None
    if not isinstance(tags, dict):
        return ""

    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:suburb"),
        tags.get("addr:neighbourhood"),
        tags.get("addr:city"),
    ]
    return ", ".join(str(part) for part in parts if part)


def _local_image(spot: Any, request: Any = None) -> Optional[Dict[str, Any]]:
    image_field = getattr(spot, "image_url", None)
    if not image_field:
        return None

    try:
        url = image_field.url
    except (AttributeError, ValueError):
        return None

    if not url:
        return None

    if request is not None and not str(url).lower().startswith(("http://", "https://")):
        try:
            url = request.build_absolute_uri(url)
        except Exception:  # pragma: no cover - defensive
            pass

    return {
        "url": url,
        "attribution": None,
        "license": None,
        "license_url": None,
        "source": "community",
    }


def _google_image(spot: Any) -> Optional[Dict[str, Any]]:
    metadata = getattr(spot, "google_metadata", None)
    if not isinstance(metadata, dict):
        return None

    if not google_data_is_fresh(metadata):
        return None

    photos = metadata.get("photos")
    if not isinstance(photos, list):
        return None

    for photo in photos:
        if not isinstance(photo, dict):
            continue
        name = photo.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        name = name.strip()
        return {
            "url": "/api/places/photo/" + quote(name, safe="/"),
            "attribution": photo.get("attribution") or metadata.get("attribution"),
            "attribution_url": photo.get("attribution_url"),
            "license": metadata.get("license"),
            "license_url": None,
            "source": "google",
            "photo_name": name,
        }

    return None


def _google_address(spot: Any) -> str:
    metadata = getattr(spot, "google_metadata", None)
    if not isinstance(metadata, dict):
        return ""
    if not google_data_is_fresh(metadata):
        return ""
    address = metadata.get("formatted_address")
    return str(address).strip() if address else ""


def _osm_image(spot: Any) -> Optional[Dict[str, Any]]:
    metadata = getattr(spot, "osm_metadata", None)
    if not isinstance(metadata, dict):
        return None

    image = metadata.get("image")
    if not isinstance(image, dict):
        return None

    if image.get("usable") is False:
        return None

    url = image.get("url")
    if not isinstance(url, str) or not url.strip():
        return None

    return {
        "url": url.strip(),
        "attribution": image.get("attribution"),
        "attribution_url": image.get("attribution_url"),
        "license": image.get("license"),
        "license_url": image.get("license_url"),
        "source": "osm",
    }


def google_data_is_fresh(metadata: Dict[str, Any]) -> bool:
    """Apply the Google caching limit to the stored provider data."""
    expires_at = metadata.get("expires_at")
    if not expires_at:
        return True

    if isinstance(expires_at, datetime):
        expires = expires_at
    else:
        expires = parse_datetime(str(expires_at))

    if expires is None:
        return True

    if timezone.is_naive(expires):
        expires = expires.replace(tzinfo=datetime_timezone.utc)

    return expires > timezone.now()
