"""Exceptions raised by the Google Places integration."""

from __future__ import annotations


class GooglePlacesError(Exception):
    """Base class for every Google Places error."""


class GooglePlacesNotConfigured(GooglePlacesError):
    """No API key is configured, so the service can not be used."""


class GooglePlacesRequestError(GooglePlacesError):
    """The request to Google Places failed."""


class GooglePlacesResponseError(GooglePlacesError):
    """Google Places answered with an error or an unusable payload."""


class GooglePhotoError(GooglePlacesError):
    """A photograph could not be retrieved from Google Places."""
