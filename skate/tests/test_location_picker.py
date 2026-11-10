"""Tests for the interactive location selection feature.

They cover the coordinate validation of the serializer, the API
behaviour when a spot is created, edited or emptied of its location,
and the geocoding proxy. The Nominatim service is always mocked.
"""

from __future__ import annotations

import logging
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

import requests

from skate.models import Spots

User = get_user_model()

logging.getLogger("skate.geocode").setLevel(logging.CRITICAL)

NOMINATIM_RESULT = {
    "lat": "20.6626071",
    "lon": "-103.2972617",
    "display_name": "Skatepark San Jacinto, Guadalajara, Jalisco, Mexico",
    "category": "leisure",
    "type": "skatepark",
    "osm_id": 256129315,
    "osm_type": "way",
}


def make_image_file(name="spot.jpg", size=(40, 40), color="blue"):
    """Build a small in memory image for the upload tests."""
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/jpeg")


class CoordinateValidationTests(TestCase):
    """The serializer accepts valid coordinates and rejects the rest."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_spot(self, **payload):
        payload.setdefault("name_spot", "Un spot")
        return self.client.post("/api/spots/", payload, format="multipart")

    def test_a_spot_can_be_created_without_coordinates(self):
        response = self.create_spot()

        self.assertEqual(response.status_code, 201, response.data)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertIsNone(spot.latitude)
        self.assertIsNone(spot.longitude)

    def test_a_spot_can_be_created_with_coordinates(self):
        response = self.create_spot(latitude="20.676700", longitude="-103.347500")

        self.assertEqual(response.status_code, 201, response.data)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertAlmostEqual(float(spot.latitude), 20.6767, places=6)
        self.assertAlmostEqual(float(spot.longitude), -103.3475, places=6)

    def test_null_coordinates_are_accepted(self):
        """A JSON client can send a real null to leave out the location."""
        response = self.client.post(
            "/api/spots/",
            {"name_spot": "Un spot", "latitude": None, "longitude": None},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertIsNone(spot.latitude)
        self.assertIsNone(spot.longitude)

    def test_an_empty_string_is_treated_as_no_location(self):
        response = self.create_spot(latitude="", longitude="")

        self.assertEqual(response.status_code, 201, response.data)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertIsNone(spot.latitude)
        self.assertIsNone(spot.longitude)

    def test_a_latitude_out_of_range_is_rejected(self):
        response = self.create_spot(latitude="91.0", longitude="-103.0")

        self.assertEqual(response.status_code, 400)
        self.assertIn("latitude", response.data)

    def test_a_longitude_out_of_range_is_rejected(self):
        response = self.create_spot(latitude="20.0", longitude="181.0")

        self.assertEqual(response.status_code, 400)
        self.assertIn("longitude", response.data)

    def test_the_boundary_values_are_accepted(self):
        response = self.create_spot(latitude="90", longitude="180")

        self.assertEqual(response.status_code, 201, response.data)

    def test_only_a_latitude_is_rejected(self):
        response = self.create_spot(latitude="20.0")

        self.assertEqual(response.status_code, 400)
        self.assertIn("latitude", response.data)

    def test_only_a_longitude_is_rejected(self):
        response = self.create_spot(longitude="-103.0")

        self.assertEqual(response.status_code, 400)
        self.assertIn("latitude", response.data)

    def test_zero_is_not_used_as_a_default(self):
        response = self.create_spot()

        self.assertEqual(response.status_code, 201)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertIsNone(spot.latitude)
        self.assertIsNone(spot.longitude)


class SpotCoordinateAPITests(TestCase):
    """Creating and editing a spot through the API."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )
        self.other_user = User.objects.create_user(
            username="someone", email="someone@example.com", password="secret-password"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_editing_a_spot_updates_its_coordinates(self):
        spot = Spots.objects.create(
            name_spot="Un spot", user=self.user, latitude=20.0, longitude=-103.0
        )

        response = self.client.patch(
            f"/api/spots/{spot.pk}/",
            {"latitude": "21.500000", "longitude": "-104.500000"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        spot.refresh_from_db()
        self.assertAlmostEqual(float(spot.latitude), 21.5, places=6)
        self.assertAlmostEqual(float(spot.longitude), -104.5, places=6)

    def test_the_coordinates_can_be_removed(self):
        spot = Spots.objects.create(
            name_spot="Un spot", user=self.user, latitude=20.0, longitude=-103.0
        )

        response = self.client.patch(
            f"/api/spots/{spot.pk}/",
            {"latitude": "", "longitude": ""},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        spot.refresh_from_db()
        self.assertIsNone(spot.latitude)
        self.assertIsNone(spot.longitude)

    def test_removing_only_one_coordinate_is_rejected(self):
        spot = Spots.objects.create(
            name_spot="Un spot", user=self.user, latitude=20.0, longitude=-103.0
        )

        response = self.client.patch(
            f"/api/spots/{spot.pk}/", {"latitude": ""}, format="multipart"
        )

        self.assertEqual(response.status_code, 400)
        spot.refresh_from_db()
        self.assertIsNotNone(spot.latitude)

    def test_a_patch_that_keeps_the_coordinates_is_accepted(self):
        spot = Spots.objects.create(
            name_spot="Un spot", user=self.user, latitude=20.0, longitude=-103.0
        )

        response = self.client.patch(
            f"/api/spots/{spot.pk}/", {"name_spot": "Otro nombre"}, format="multipart"
        )

        self.assertEqual(response.status_code, 200, response.data)
        spot.refresh_from_db()
        self.assertEqual(spot.name_spot, "Otro nombre")
        self.assertAlmostEqual(float(spot.latitude), 20.0, places=6)

    def test_an_image_can_be_uploaded_together_with_coordinates(self):
        response = self.client.post(
            "/api/spots/",
            {
                "name_spot": "Con foto y ubicación",
                "latitude": "20.676700",
                "longitude": "-103.347500",
                "image_url": make_image_file(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertTrue(spot.image_url)
        self.assertAlmostEqual(float(spot.latitude), 20.6767, places=6)

    def test_the_spot_listing_still_works(self):
        Spots.objects.create(
            name_spot="Un spot", user=self.user, latitude=20.0, longitude=-103.0
        )

        response = self.client.get("/api/spots/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertIn("latitude", response.data["results"][0])
        self.assertIn("longitude", response.data["results"][0])

    def test_another_user_cannot_edit_the_spot(self):
        spot = Spots.objects.create(
            name_spot="Un spot", user=self.other_user, latitude=20.0, longitude=-103.0
        )

        response = self.client.patch(
            f"/api/spots/{spot.pk}/", {"latitude": "21.0", "longitude": "-104.0"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 403)
        spot.refresh_from_db()
        self.assertAlmostEqual(float(spot.latitude), 20.0, places=6)

    def test_the_spot_can_still_be_deleted(self):
        spot = Spots.objects.create(
            name_spot="Un spot", user=self.user, latitude=20.0, longitude=-103.0
        )

        response = self.client.delete(f"/api/spots/{spot.pk}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Spots.objects.filter(pk=spot.pk).exists())


class SpotFormPageTests(TestCase):
    """The HTML pages of the spot form."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )
        self.client = APIClient()

    def test_the_create_page_is_rendered(self):
        """The page is public, the API is what protects the spots."""
        response = self.client.get("/spots/new/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "spot_form.html")
        self.assertContains(response, 'id="map"')
        self.assertContains(response, 'id="login-notice"')

    def test_the_edit_page_loads_the_existing_coordinates(self):
        spot = Spots.objects.create(
            name_spot="Un spot",
            user=self.user,
            latitude=20.676700,
            longitude=-103.347500,
        )

        response = self.client.get(f"/spots/{spot.pk}/edit/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-latitude="20.676700"')
        self.assertContains(response, 'data-longitude="-103.347500"')
        self.assertContains(response, 'data-spot-id="%s"' % spot.pk)

    def test_the_edit_page_of_another_user_is_refused_for_a_logged_in_user(self):
        """With a Django session the ownership is checked on the page."""
        spot = Spots.objects.create(name_spot="Un spot", user=self.user)
        other = User.objects.create_user(
            username="someone", email="someone@example.com", password="secret-password"
        )
        self.client.force_login(other)

        response = self.client.get(f"/spots/{spot.pk}/edit/")

        self.assertEqual(response.status_code, 403)

    def test_the_edit_page_prefills_the_name_and_the_description(self):
        spot = Spots.objects.create(
            name_spot="Parque de las Americas",
            body="Un skatepark grande",
            user=self.user,
        )

        response = self.client.get(f"/spots/{spot.pk}/edit/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parque de las Americas")
        self.assertContains(response, "Un skatepark grande")

    def test_the_create_page_starts_empty(self):
        response = self.client.get("/spots/new/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value=""')
        self.assertContains(response, 'data-spot-id=""')

    def test_the_form_carries_a_csrf_token(self):
        """The page sends the token so a write also works with a session."""
        response = self.client.get("/spots/new/")

        self.assertContains(response, "csrfmiddlewaretoken")

    def test_the_api_refuses_to_edit_a_spot_of_another_user(self):
        """Without a session the API is the one that refuses the write."""
        spot = Spots.objects.create(
            name_spot="Un spot", user=self.user, latitude=20.0, longitude=-103.0
        )
        other = User.objects.create_user(
            username="someone", email="someone@example.com", password="secret-password"
        )
        self.client.force_authenticate(other)

        response = self.client.patch(
            f"/api/spots/{spot.pk}/",
            {"latitude": "21.0", "longitude": "-104.0"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 403)


class GeocodeSearchTests(TestCase):
    """The Nominatim proxy."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        cache.clear()

    @patch("skate.geocode.services.requests.get")
    def test_a_search_returns_the_results(self, mock_get):
        mock_get.return_value = FakeNominatimResponse([NOMINATIM_RESULT])

        response = self.client.get("/api/geocode/search/", {"q": "skatepark guadalajara"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(result["short_label"], "Skatepark San Jacinto")
        self.assertAlmostEqual(result["latitude"], 20.6626071, places=6)
        self.assertAlmostEqual(result["longitude"], -103.2972617, places=6)

    @patch("skate.geocode.services.requests.get")
    def test_the_request_identifies_the_application(self, mock_get):
        mock_get.return_value = FakeNominatimResponse([NOMINATIM_RESULT])

        self.client.get("/api/geocode/search/", {"q": "skatepark guadalajara"})

        _, kwargs = mock_get.call_args
        self.assertIn("RollingUp", kwargs["headers"]["User-Agent"])

    @patch("skate.geocode.services.requests.get")
    def test_a_short_query_is_rejected_without_calling_nominatim(self, mock_get):
        response = self.client.get("/api/geocode/search/", {"q": "ab"})

        self.assertEqual(response.status_code, 400)
        mock_get.assert_not_called()

    @patch("skate.geocode.services.requests.get")
    def test_the_answers_are_cached(self, mock_get):
        mock_get.return_value = FakeNominatimResponse([NOMINATIM_RESULT])

        self.client.get("/api/geocode/search/", {"q": "skatepark guadalajara"})
        self.client.get("/api/geocode/search/", {"q": "skatepark guadalajara"})

        self.assertEqual(mock_get.call_count, 1)

    @patch("skate.geocode.services.requests.get")
    def test_an_unreachable_service_is_handled(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("no network")

        response = self.client.get("/api/geocode/search/", {"q": "skatepark guadalajara"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["results"], [])

    @patch("skate.geocode.services.requests.get")
    def test_a_search_without_results_is_not_an_error(self, mock_get):
        mock_get.return_value = FakeNominatimResponse([])

        response = self.client.get("/api/geocode/search/", {"q": "nothing here"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_the_search_needs_a_login(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/geocode/search/", {"q": "skatepark"})

        self.assertEqual(response.status_code, 401)

    @patch("skate.geocode.services.requests.get")
    def test_the_search_is_throttled(self, mock_get):
        mock_get.return_value = FakeNominatimResponse([NOMINATIM_RESULT])

        # The default rate is 30/min, the 31st request has to be refused.
        for index in range(30):
            response = self.client.get(
                "/api/geocode/search/", {"q": f"skatepark {index}"}
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/geocode/search/", {"q": "one too many"})

        self.assertEqual(response.status_code, 429)


class FakeNominatimResponse:
    """A minimal stand in for a ``requests.Response``."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload
