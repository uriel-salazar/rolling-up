"""Backend proxy for the Nominatim geocoding service.

The browser never talks to Nominatim directly. Every search goes
through this module, which:

* identifies the application with a proper ``User-Agent``, as the
  Nominatim usage policy requires,
* caches the answers, so a popular search is not requested again on
  every keystroke,
* limits the number of results,
* turns the upstream payload into a small, stable structure.

The frontend debounces its requests as well, and the API view applies a
throttle, so the public service is never flooded.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class NominatimRateLimiter:
    """Keep the whole application below the Nominatim request limit.

    The Nominatim usage policy allows an absolute maximum of one
    request per second **for the whole site**, the traffic of every
    user is added up. A per user throttle is therefore not enough, the
    limit has to be global.

    The limiter serialises the requests and spaces them out, so two
    users searching at the same time result in one request and one
    queued behind it.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_request = 0.0

    def reset(self) -> None:
        """Forget the last request, mostly useful for the tests."""
        with self._lock:
            self._last_request = 0.0

    def acquire(self) -> None:
        """Wait until a request may be sent."""
        max_per_second = settings.NOMINATIM_MAX_REQUESTS_PER_SECOND
        if max_per_second <= 0:
            return

        interval = 1.0 / max_per_second

        with self._lock:
            now = time.monotonic()
            wait_for = self._last_request + interval - now
            if wait_for > 0:
                logger.debug(
                    "Waiting %ss before the next Nominatim request.", round(wait_for, 2)
                )
                time.sleep(wait_for)
            self._last_request = time.monotonic()


_rate_limiter = NominatimRateLimiter()



class GeocodingError(Exception):
    """The geocoding service could not be reached or answered badly."""


class GeocodingUnavailable(GeocodingError):
    """The geocoding service is not available at the moment."""


class QueryTooShort(GeocodingError):
    """The query is too short to produce meaningful results."""


def search_locations(query: str) -> List[Dict[str, Any]]:
    """Look up a place with Nominatim.

    Args:
        query: The free form text typed by the user.

    Returns:
        A list of results, each one a dictionary with the keys
        ``label``, ``latitude``, ``longitude``, ``category``,
        ``osm_type`` and ``osm_id``.

    Raises:
        QueryTooShort: The query is shorter than the configured minimum.
        GeocodingUnavailable: The service could not be reached.
    """
    cleaned = (query or "").strip()

    if len(cleaned) < settings.GEOCODE_MIN_QUERY_LENGTH:
        raise QueryTooShort(
            f"The search needs at least {settings.GEOCODE_MIN_QUERY_LENGTH} characters."
        )

    cache_key = _cache_key(cleaned)
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug("Geocoding cache hit for %r", cleaned)
        return cached

    results = _request_nominatim(cleaned)
    cache.set(cache_key, results, settings.GEOCODE_CACHE_SECONDS)
    return results


def _cache_key(query: str) -> str:
    """Return the cache key of a query.

    The query is hashed, so the key stays short and only holds
    characters every cache backend accepts.
    """
    digest = hashlib.sha256(query.lower().encode("utf-8")).hexdigest()
    return f"geocode:v1:{digest}"


def _request_nominatim(query: str) -> List[Dict[str, Any]]:
    """Perform the actual request against Nominatim.

    The global rate limiter is used here, right before the request, so
    the answers that come from the cache never wait for it.
    """
    _rate_limiter.acquire()

    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": settings.GEOCODE_MAX_RESULTS,
        "accept-language": settings.GEOCODE_LANGUAGE,
    }
    headers = {"User-Agent": settings.NOMINATIM_USER_AGENT}

    try:
        response = requests.get(
            settings.NOMINATIM_API_URL,
            params=params,
            headers=headers,
            timeout=settings.NOMINATIM_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("The geocoding service could not be reached: %s", exc)
        raise GeocodingUnavailable(
            "The geocoding service could not be reached."
        ) from exc

    if response.status_code == 429:
        logger.warning("The geocoding service is rate limiting us.")
        raise GeocodingUnavailable(
            "The geocoding service is busy, please try again in a moment."
        )

    if not response.ok:
        logger.warning(
            "The geocoding service answered with HTTP %s.", response.status_code
        )
        raise GeocodingUnavailable(
            f"The geocoding service answered with HTTP {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise GeocodingUnavailable(
            "The geocoding service returned an answer that is not valid JSON."
        ) from exc

    if not isinstance(payload, list):
        raise GeocodingUnavailable(
            "The geocoding service returned an unexpected answer."
        )

    return [result for result in (_normalize(item) for item in payload) if result]


def _normalize(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn one raw Nominatim result into the structure the API returns."""
    try:
        latitude = float(item["lat"])
        longitude = float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None

    label = item.get("display_name") or ""
    parts = [part for part in label.split(",") if part.strip()]

    return {
        "label": label,
        "short_label": parts[0].strip() if parts else label,
        "latitude": latitude,
        "longitude": longitude,
        "category": item.get("category") or item.get("class") or "",
        "type": item.get("type") or "",
        "osm_id": item.get("osm_id"),
        "osm_type": item.get("osm_type") or "",
    }
