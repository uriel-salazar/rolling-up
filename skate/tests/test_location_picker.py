"""Tests for the interactive location selection feature.

They cover the coordinate validation of the serializer, the API
behaviour when a spot is created, edited or emptied of its location,
and the geocoding proxy. The Nominatim service is always mocked.
"""

from __future__ import annotations

import logging
import re
import time
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import TestCase, override_settings
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


@override_settings(NOMINATIM_MAX_REQUESTS_PER_SECOND=0)
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


class NominatimRateLimiterTests(TestCase):
    """The whole application has to stay below one request per second.

    The Nominatim usage policy applies the limit to the whole site and
    not to every user on its own, so the limit is global.
    """

    def setUp(self):
        from skate.geocode import services

        self.services = services
        self.limiter = services._rate_limiter
        self.limiter.reset()

    def tearDown(self):
        self.limiter.reset()

    def test_two_requests_are_spaced_out(self):
        with override_settings(NOMINATIM_MAX_REQUESTS_PER_SECOND=20):
            started = time.monotonic()
            self.limiter.acquire()
            self.limiter.acquire()
            elapsed = time.monotonic() - started

        # At 20 requests per second the second one waits 50 milliseconds.
        self.assertGreaterEqual(elapsed, 0.04)

    def test_the_limit_can_be_switched_off(self):
        with override_settings(NOMINATIM_MAX_REQUESTS_PER_SECOND=0):
            started = time.monotonic()
            self.limiter.acquire()
            self.limiter.acquire()
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.01)

    def test_the_default_rate_is_one_request_per_second(self):
        self.assertEqual(settings.NOMINATIM_MAX_REQUESTS_PER_SECOND, 1.0)


class TileUsagePolicyTests(TestCase):
    """The map follows the tile usage policy of the OpenStreetMap servers.

    https://operations.osmfoundation.org/policies/tiles/
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )
        self.client = APIClient()

    def test_the_tile_url_is_the_one_the_policy_asks_for(self):
        """The standard OpenStreetMap tiles are the default."""
        self.assertEqual(
            settings.OSM_TILE_URL,
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        )

    def test_the_tile_url_has_no_subdomain_shortcut(self):
        """The policy asks for exactly the url above, without {s}."""
        self.assertNotIn("{s}", settings.OSM_TILE_URL)
        self.assertEqual(settings.OSM_TILE_SUBDOMAINS, "")

    def test_the_map_uses_the_configured_tile_url(self):
        response = self.client.get("/spots/new/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, settings.OSM_TILE_URL)

    def test_the_carto_basemaps_can_be_used_instead(self):
        """The provider is a setting, so it can be changed at any time."""
        with override_settings(
            OSM_TILE_URL="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
            OSM_TILE_SUBDOMAINS="abcd",
        ):
            response = self.client.get("/spots/new/")

        html = response.content.decode()

        self.assertIn("basemaps.cartocdn.com", html)
        self.assertIn('data-tile-subdomains="abcd"', html)
        # CARTO asks for the credit of both projects.
        self.assertIn("carto.com/attribution", html)

    def test_the_attribution_is_shown_on_the_map(self):
        response = self.client.get("/spots/new/")

        self.assertContains(response, "OpenStreetMap")
        self.assertContains(response, "openstreetmap.org/copyright")

    def test_the_map_offers_a_link_to_report_a_problem(self):
        response = self.client.get("/spots/new/")

        self.assertContains(response, "openstreetmap.org/fixthemap")

    def test_the_map_publishes_a_contact_address(self):
        response = self.client.get("/spots/new/")

        self.assertContains(response, settings.OSM_CONTACT_EMAIL)

    def test_the_attribution_is_one_well_formed_attribute(self):
        """The links inside the attribution must not cut the attribute."""
        response = self.client.get("/spots/new/")
        html = response.content.decode()

        match = re.search(r'data-tile-attribution="([^"]*)"', html)

        self.assertIsNotNone(match)
        self.assertIn('contributors', match.group(1))
        self.assertIn('openstreetmap.org/copyright', match.group(1))
        self.assertIn('fixthemap', match.group(1))

    def test_the_browser_sends_a_referer_to_the_tile_servers(self):
        """Django must not drop the Referer on the cross origin requests."""
        self.assertEqual(
            settings.SECURE_REFERRER_POLICY, "strict-origin-when-cross-origin"
        )

    def test_the_referer_policy_reaches_the_response(self):
        response = self.client.get("/spots/new/")

        self.assertEqual(
            response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin"
        )


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
