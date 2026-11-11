"""Thin HTTP client for the Google Places API (New).

Only the two calls the application needs are implemented:

* Nearby Search with ``includedTypes: ["skateboard_park"]``.
* Place Photos, used by the photo proxy so the API key never reaches
  the browser.

The module does not know about Django models. It returns the raw JSON
of Google (normalised by :mod:`skate.google_places.parser`).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional

import requests
from django.conf import settings

from .exceptions import (
    GooglePlacesNotConfigured,
    GooglePlacesRequestError,
    GooglePlacesResponseError,
    GooglePhotoError,
)

logger = logging.getLogger(__name__)

NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/{name}/media"

# The fields the application uses. Sending a field mask is required by
# the Places API (New) and keeps the response small.
NEARBY_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
        "places.photos",
        "places.types",
        "places.primaryType",
        "places.googleMapsUri",
        "places.websiteUri",
        "nextPageToken",
    )
)

# The photo name is ``places/{place_id}/photos/{photo_reference}``. The
# strict pattern keeps the proxy from becoming an open URL fetcher.
PHOTO_NAME_PATTERN = re.compile(
    r"^places/[^/\s]+/photos/[^/\s]+$"
)

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class GooglePlacesClient:
    """Retrieve skateparks and photographs from Google Places (New).

    Args:
        api_key: Google API key. Defaults to ``GOOGLE_PLACES_API_KEY``.
        timeout: Timeout of a single request in seconds.
        session: Optional ``requests.Session``, useful for the tests.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else settings.GOOGLE_PLACES_API_KEY
        )
        self.timeout = (
            timeout if timeout is not None else settings.GOOGLE_PLACES_TIMEOUT
        )
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    # Nearby Search
    # ------------------------------------------------------------------
    def search_nearby(
        self,
        latitude: float,
        longitude: float,
        radius: Optional[int] = None,
        max_results: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a Nearby Search restricted to actual skateparks.

        Args:
            latitude: Centre of the search.
            longitude: Centre of the search.
            radius: Radius in metres.
            max_results: ``maxResultCount``, between 1 and 20.
            page_token: Optional ``nextPageToken`` of a previous call.

        Returns:
            The raw JSON answer of Google.
        """
        self._require_key()

        body: Dict[str, Any] = {
            "includedTypes": ["skateboard_park"],
            "maxResultCount": self._clamp_max_results(max_results),
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                    },
                    "radius": self._clamp_radius(radius),
                }
            },
        }
        if page_token:
            body["pageToken"] = page_token

        return self._request_json(
            NEARBY_SEARCH_URL,
            body=body,
            headers={"X-Goog-FieldMask": NEARBY_FIELD_MASK},
        )

    def search_all(
        self,
        latitude: float,
        longitude: float,
        radius: Optional[int] = None,
        max_results: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Follow the pagination of Nearby Search and return every place."""
        pages = (
            max_pages if max_pages is not None else settings.GOOGLE_PLACES_MAX_PAGES
        )
        places: List[Dict[str, Any]] = []
        token: Optional[str] = None

        for _ in range(max(1, pages)):
            payload = self.search_nearby(
                latitude,
                longitude,
                radius=radius,
                max_results=max_results,
                page_token=token,
            )
            places.extend(self._extract_places(payload))

            token = payload.get("nextPageToken")
            if not token:
                break

        return places

    # ------------------------------------------------------------------
    # Place Photos
    # ------------------------------------------------------------------
    def fetch_photo(
        self,
        photo_name: str,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Retrieve the bytes of a Google Places photograph.

        The key is sent to Google on the server, never to the browser.

        Returns:
            ``{"content": bytes, "content_type": str}``.
        """
        self._require_key()

        if not is_valid_photo_name(photo_name):
            raise GooglePhotoError("The photo reference is not valid.")

        url = PHOTO_MEDIA_URL.format(name=photo_name)
        params: Dict[str, Any] = {"key": self.api_key}
        params["maxWidthPx"] = int(
            max_width
            if max_width is not None
            else settings.GOOGLE_PLACES_PHOTO_MAX_WIDTH
        )
        if max_height:
            params["maxHeightPx"] = int(max_height)

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            logger.warning("The Google photo could not be fetched: %s", exc)
            raise GooglePhotoError(
                "The skatepark photograph could not be retrieved."
            ) from exc

        if not response.ok:
            logger.warning(
                "Google answered HTTP %s for a photo.", response.status_code
            )
            raise GooglePhotoError(
                f"Google answered HTTP {response.status_code} for the photo."
            )

        content_type = response.headers.get("Content-Type", "image/jpeg")
        if not content_type.lower().startswith("image/"):
            raise GooglePhotoError("Google did not return an image.")

        return {
            "content": response.content,
            "content_type": content_type,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _require_key(self) -> None:
        if not self.api_key:
            raise GooglePlacesNotConfigured(
                "GOOGLE_PLACES_API_KEY is not configured."
            )

    def _request_json(
        self,
        url: str,
        body: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """POST a JSON body and return the decoded answer."""
        request_headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "User-Agent": settings.OVERPASS_USER_AGENT,
        }
        request_headers.update(headers)

        try:
            response = self.session.post(
                url,
                json=body,
                headers=request_headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.warning("Google Places could not be reached: %s", exc)
            raise GooglePlacesRequestError(
                "Google Places could not be reached."
            ) from exc

        if response.status_code in RETRYABLE_STATUS_CODES:
            logger.warning(
                "Google Places answered HTTP %s.", response.status_code
            )
            raise GooglePlacesRequestError(
                f"Google Places answered HTTP {response.status_code}."
            )

        if not response.ok:
            raise GooglePlacesResponseError(
                "Google Places rejected the request: "
                f"{self._extract_error_message(response)}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise GooglePlacesResponseError(
                "Google Places returned a response that is not valid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise GooglePlacesResponseError(
                "Google Places returned an unexpected payload."
            )

        return payload

    @staticmethod
    def _extract_places(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        places = payload.get("places", [])
        if not isinstance(places, list):
            raise GooglePlacesResponseError(
                "Google Places returned an unexpected 'places' value."
            )
        return [place for place in places if isinstance(place, dict)]

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if message:
                    return str(message)[:300]

        text = (response.text or "").strip()
        return text[:300] or "unknown error"

    @staticmethod
    def _clamp_radius(value: Optional[int]) -> float:
        wanted = settings.GOOGLE_PLACES_SEARCH_RADIUS if value is None else value
        return float(max(1.0, min(float(wanted), 50000.0)))

    @staticmethod
    def _clamp_max_results(value: Optional[int]) -> int:
        maximum = int(settings.GOOGLE_PLACES_MAX_RESULTS)
        wanted = maximum if value is None else int(value)
        return max(1, min(wanted, 20))


def is_valid_photo_name(photo_name: str) -> bool:
    """Return whether a photo reference has the shape Google sends."""
    return bool(PHOTO_NAME_PATTERN.match(photo_name or ""))


def iter_photos(place: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Yield the photo entries of a raw Google place."""
    photos = place.get("photos")
    if not isinstance(photos, list):
        return ()
    return (photo for photo in photos if isinstance(photo, dict))
