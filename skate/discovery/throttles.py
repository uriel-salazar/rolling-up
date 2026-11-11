"""Throttling for the Overpass-backed discovery endpoints."""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle


class OverpassDiscoveryThrottle(UserRateThrottle):
    """Keep the application below the public Overpass usage limits."""

    scope = "overpass"
