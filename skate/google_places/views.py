"""Proxy for the photographs of the Google Places API (New)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .client import GooglePlacesClient, is_valid_photo_name
from .exceptions import (
    GooglePhotoError,
    GooglePlacesError,
    GooglePlacesNotConfigured,
)

logger = logging.getLogger(__name__)


class GooglePlacePhotoView(APIView):
    """Serve one Google Places photograph without exposing the key.

    The photo reference is the one stored in ``google_metadata``. The
    bytes are fetched on demand and are never written to the media
    storage of the application. Only the browser cache is allowed, for
    a bounded amount of time.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, photo_name=None):
        photo_name = photo_name or request.query_params.get('name', '')

        if not is_valid_photo_name(photo_name):
            return HttpResponse(
                'The photo reference is not valid.', status=400
            )

        if not settings.GOOGLE_PLACES_API_KEY:
            return HttpResponse(
                'The photo provider is not configured.', status=503
            )

        client = GooglePlacesClient()
        try:
            photo = client.fetch_photo(
                photo_name,
                max_width=settings.GOOGLE_PLACES_PHOTO_MAX_WIDTH,
            )
        except GooglePlacesNotConfigured:
            return HttpResponse(
                'The photo provider is not configured.', status=503
            )
        except GooglePhotoError as exc:
            logger.warning("Could not proxy a Google photo: %s", exc)
            return HttpResponse(str(exc), status=502)
        except GooglePlacesError as exc:  # pragma: no cover - defensive
            logger.warning("Could not proxy a Google photo: %s", exc)
            return HttpResponse(str(exc), status=502)

        response = HttpResponse(
            photo['content'], content_type=photo['content_type']
        )
        response['Cache-Control'] = (
            'public, max-age='
            + str(int(settings.GOOGLE_PLACES_PHOTO_CACHE_SECONDS))
        )
        response['X-Photo-Source'] = 'google-places'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
