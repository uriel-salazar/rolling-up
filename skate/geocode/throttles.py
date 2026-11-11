"""Throttling rules used by the geocoding endpoint.

The default rates of the project are meant for the spot API, they are
far too generous for a service that proxies a public geocoder.
"""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle


class GeocodeRateThrottle(UserRateThrottle):
    """Limit how often a single user may search for a location.

    The rate is configured with the ``GEOCODE_THROTTLE_RATE`` setting
    and defaults to ``30/min``. Anonymous requests are throttled by
    IP with the same rate.
    """

    scope = "geocode"
