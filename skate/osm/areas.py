"""Turn a place name into a geographic area usable by Overpass.

Two strategies are supported:

* ``geocodeArea`` -- the native Overpass specialiser. It is the fastest
  option because it does not need an extra request, but it is not
  accepted by every Overpass instance (the official one currently
  rejects it with an HTTP 400 parse error).
* Nominatim -- geocodes the place name to a bounding box, which every
  Overpass instance understands.

The importer tries ``geocodeArea`` first and falls back to Nominatim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings

from .exceptions import LocationResolutionError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Area:
    """A rectangular geographic area."""

    name: str
    south: float
    west: float
    north: float
    east: float

    @property
    def bbox(self) -> str:
        """The bounding box in the ``south,west,north,east`` Overpass order."""
        return f"{self.south},{self.west},{self.north},{self.east}"

    @classmethod
    def from_bbox(cls, name: str, bbox: str) -> "Area":
        """Build an area from a ``south,west,north,east`` string."""
        try:
            south, west, north, east = (float(part) for part in bbox.split(","))
        except ValueError as exc:
            raise LocationResolutionError(
                f"'{bbox}' is not a valid bounding box (south,west,north,east)."
            ) from exc

        if south > north or west > east:
            raise LocationResolutionError(
                f"'{bbox}' is not a valid bounding box (south,west,north,east)."
            )

        return cls(name=name, south=south, west=west, north=north, east=east)


def geocode_area(client, location: str) -> Area:
    """Resolve ``location`` into an :class:`Area` using Nominatim.

    Args:
        client: A ``requests.Session`` used to perform the request.
        location: A free form place name such as
            ``"Guadalajara, Jalisco, Mexico"``.

    Returns:
        The resolved :class:`Area`.

    Raises:
        LocationResolutionError: The place could not be geocoded.
    """
    params = {
        "q": location,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": settings.OVERPASS_USER_AGENT}

    try:
        response = client.get(
            settings.NOMINATIM_API_URL,
            params=params,
            headers=headers,
            timeout=settings.NOMINATIM_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise LocationResolutionError(
            f"Could not reach the geocoding service for '{location}': {exc}"
        ) from exc

    if not response.ok:
        raise LocationResolutionError(
            f"The geocoding service answered HTTP {response.status_code} for '{location}'."
        )

    try:
        results = response.json()
    except ValueError as exc:
        raise LocationResolutionError(
            f"The geocoding service returned a non JSON answer for '{location}'."
        ) from exc

    if not results:
        raise LocationResolutionError(
            f"'{location}' could not be geocoded: no matching place was found."
        )

    bounding_box = results[0].get("boundingbox")
    if not bounding_box or len(bounding_box) != 4:
        raise LocationResolutionError(
            f"'{location}' was geocoded but no bounding box was returned."
        )

    try:
        south, north, west, east = (float(value) for value in bounding_box)
    except (TypeError, ValueError) as exc:
        raise LocationResolutionError(
            f"The bounding box returned for '{location}' is not numeric."
        ) from exc

    logger.info(
        "Resolved '%s' to bbox %s,%s,%s,%s", location, south, west, north, east
    )
    return Area(name=location, south=south, west=west, north=north, east=east)


def build_geocode_area_filter(location: str) -> str:
    """Return the Overpass filter that resolves ``location`` to an area."""
    return f"{{{{geocodeArea:{location}}}}}->.searchArea;"
