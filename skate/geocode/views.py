"""API endpoint that searches for a location by name."""

from __future__ import annotations

import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    GeocodeErrorSerializer,
    GeocodeSearchResponseSerializer,
)
from .services import (
    GeocodingUnavailable,
    QueryTooShort,
    search_locations,
)
from .throttles import GeocodeRateThrottle

logger = logging.getLogger(__name__)


class GeocodeSearchView(APIView):
    """Search for a place with Nominatim.

    The endpoint is a thin proxy around the geocoding service. It
    applies a throttle, caches the answers and returns a small, stable
    structure so the frontend does not have to know anything about
    Nominatim.
    """

    permission_classes = [AllowAny]
    throttle_classes = [GeocodeRateThrottle]

    @extend_schema(
        operation_id="geocode_search",
        summary="Search a location by name",
        description=(
            'Looks a place up with OpenStreetMap. Useful to find a '
            'skatepark, a street, an address or a neighbourhood. The '
            'search needs at least three characters.'
        ),
        parameters=[
            OpenApiParameter(
                name='q',
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description='The text to search for.',
            ),
        ],
        responses={
            200: GeocodeSearchResponseSerializer,
            400: GeocodeErrorSerializer,
            503: GeocodeErrorSerializer,
        },
    )
    def get(self, request):
        query = request.query_params.get('q', '')

        try:
            results = search_locations(query)
        except QueryTooShort as exc:
            return Response(
                {'detail': str(exc), 'results': []},
                status=400,
            )
        except GeocodingUnavailable as exc:
            logger.warning("Geocoding request failed: %s", exc)
            return Response(
                {
                    'detail': (
                        'The location search is unavailable right now. '
                        'You can still pick a spot on the map.'
                    ),
                    'results': [],
                },
                status=503,
            )

        return Response(
            {
                'query': query.strip(),
                'count': len(results),
                'results': results,
            }
        )
