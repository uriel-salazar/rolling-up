"""Exceptions raised by the OpenStreetMap integration."""

from __future__ import annotations


class OSMError(Exception):
    """Base class for every error raised by the OSM integration."""


class OverpassError(OSMError):
    """The Overpass API answered with an error or an unusable payload."""


class OverpassQueryError(OverpassError):
    """The Overpass API rejected the query itself (HTTP 400).

    Raised for malformed Overpass QL. The importer treats this
    specially: it can fall back to a different way of resolving the
    geographic area.
    """


class OverpassRequestError(OverpassError):
    """The request to the Overpass API failed after every retry."""


class AreaResolutionError(OSMError):
    """A place name could not be turned into a geographic area."""


class LocationResolutionError(OSMError):
    """A place name could not be geocoded to a bounding box."""
