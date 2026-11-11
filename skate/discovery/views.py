"""Read-only API endpoints for worldwide skatepark discovery."""

from __future__ import annotations

import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from skate.osm.discovery import (
    DiscoveryUnavailable,
    InvalidDiscoveryQuery,
    discover_nearby,
    discover_viewport,
)

from .serializers import DiscoveryResponseSerializer
from .throttles import OverpassDiscoveryThrottle

logger = logging.getLogger(__name__)


class _DiscoveryView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OverpassDiscoveryThrottle]

    def _answer(self, payload):
        return Response(DiscoveryResponseSerializer(payload).data)

    def _error(self, detail, status):
        return Response({"detail": detail, "results": []}, status=status)


class NearbySkateparksView(_DiscoveryView):
    """Return live OSM skateparks around a point."""

    def get(self, request):
        params = request.query_params
        try:
            payload = discover_nearby(
                params.get("lat"),
                params.get("lon", params.get("lng")),
                radius=params.get("radius"),
                limit=params.get("limit"),
            )
        except InvalidDiscoveryQuery as exc:
            return self._error(str(exc), 400)
        except DiscoveryUnavailable as exc:
            logger.warning("Nearby discovery unavailable: %s", exc)
            return self._error(str(exc), 503)

        return self._answer(payload)


class ViewportSkateparksView(_DiscoveryView):
    """Return live OSM skateparks inside a map viewport."""

    def get(self, request):
        params = request.query_params
        try:
            payload = discover_viewport(
                params.get("south"),
                params.get("west"),
                params.get("north"),
                params.get("east"),
                limit=params.get("limit"),
            )
        except InvalidDiscoveryQuery as exc:
            return self._error(str(exc), 400)
        except DiscoveryUnavailable as exc:
            logger.warning("Viewport discovery unavailable: %s", exc)
            return self._error(str(exc), 503)

        return self._answer(payload)
