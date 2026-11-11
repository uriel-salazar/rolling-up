"""Shared helpers for the OpenStreetMap test suite."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class FakeResponse:
    """A minimal stand-in for a ``requests.Response`` object."""

    def __init__(
        self,
        status_code: int = 200,
        payload: Optional[Dict[str, Any]] = None,
        text: str = "",
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or ""
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Dict[str, Any]:
        if self._payload is None:
            raise ValueError("No JSON object could be decoded.")
        return self._payload


def overpass_payload(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrap a list of elements in a realistic Overpass response."""
    return {
        "version": 0.6,
        "generator": "Overpass API 0.7.62",
        "osm3s": {
            "timestamp_osm_base": "2026-11-10T00:00:00Z",
            "copyright": (
                "The data included in this document is from "
                "www.openstreetmap.org. The data is made available under ODbL."
            ),
        },
        "elements": elements,
    }


def node_element(
    osm_id: int,
    latitude: float,
    longitude: float,
    tags: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a raw Overpass node element."""
    element: Dict[str, Any] = {
        "type": "node",
        "id": osm_id,
        "lat": latitude,
        "lon": longitude,
    }
    if tags is not None:
        element["tags"] = tags
    return element


def way_element(
    osm_id: int,
    latitude: float,
    longitude: float,
    tags: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a raw Overpass way element with a centre."""
    element: Dict[str, Any] = {
        "type": "way",
        "id": osm_id,
        "center": {"lat": latitude, "lon": longitude},
        "nodes": [1, 2, 3],
    }
    if tags is not None:
        element["tags"] = tags
    return element


def relation_element(
    osm_id: int,
    latitude: float,
    longitude: float,
    tags: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a raw Overpass relation element with a centre."""
    element: Dict[str, Any] = {
        "type": "relation",
        "id": osm_id,
        "center": {"lat": latitude, "lon": longitude},
        "members": [{"type": "way", "ref": 1, "role": "outer"}],
    }
    if tags is not None:
        element["tags"] = tags
    return element


def connection_error() -> requests.ConnectionError:
    """Return the exception used to simulate a network failure."""
    return requests.ConnectionError("Connection refused")
