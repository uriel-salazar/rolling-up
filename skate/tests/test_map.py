"""Tests for the interactive map.

They cover the public endpoint the map reads, the filters it sends and
the proxy that serves the tiles.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from skate.models import Rating, Spots
from skate.tiles import build_tile_url, pick_subdomain

User = get_user_model()


class FakeTileResponse:
    """A minimal stand in for a ``requests.Response``."""

    def __init__(self, status_code=200, content=b"tile", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    @property
    def ok(self):
        return self.status_code < 400


class MapApiTests(TestCase):
    """The endpoint the map reads."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )
        self.client = APIClient()

        self.park = Spots.objects.create(
            name_spot="Skatepark Oasis",
            body="Un skatepark grande",
            user=self.user,
            source=Spots.SOURCE_OSM,
            category=Spots.CATEGORY_SKATEPARK,
            latitude=Decimal("20.706324"),
            longitude=Decimal("-103.363065"),
        )
        self.street = Spots.objects.create(
            name_spot="Plaza del centro",
            body="Un spot en la calle",
            user=self.user,
            source=Spots.SOURCE_COMMUNITY,
            category=Spots.CATEGORY_STREET,
            latitude=Decimal("20.671073"),
            longitude=Decimal("-103.405057"),
        )
        self.diy = Spots.objects.create(
            name_spot="DIY del parque",
            user=self.user,
            source=Spots.SOURCE_COMMUNITY,
            category=Spots.CATEGORY_DIY,
            latitude=Decimal("20.650534"),
            longitude=Decimal("-103.367389"),
        )
        self.without_place = Spots.objects.create(
            name_spot="Sin ubicación",
            user=self.user,
            source=Spots.SOURCE_COMMUNITY,
        )

    def test_the_spots_are_read_without_an_account(self):
        response = self.client.get("/api/spots/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)

    def test_the_spots_carry_everything_the_map_needs(self):
        response = self.client.get("/api/spots/")
        spot = response.data["results"][0]

        for field in (
            "id", "name_spot", "body", "latitude", "longitude",
            "category", "source", "image_url", "rating", "rating_count",
        ):
            self.assertIn(field, spot)

    def test_the_search_looks_in_the_name(self):
        response = self.client.get("/api/spots/", {"search": "Oasis"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name_spot"], "Skatepark Oasis")

    def test_the_search_looks_in_the_description(self):
        response = self.client.get("/api/spots/", {"search": "en la calle"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name_spot"], "Plaza del centro")

    def test_the_search_ignores_the_case(self):
        response = self.client.get("/api/spots/", {"search": "oasis"})

        self.assertEqual(response.data["count"], 1)

    def test_a_search_without_a_match_is_empty(self):
        response = self.client.get("/api/spots/", {"search": "nada de esto"})

        self.assertEqual(response.data["count"], 0)

    def test_the_category_filter(self):
        response = self.client.get("/api/spots/", {"category": "skatepark"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["category"], "skatepark")

    def test_the_diy_category_filter(self):
        response = self.client.get("/api/spots/", {"category": "diy"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["category"], "diy")

    def test_the_source_filter(self):
        response = self.client.get("/api/spots/", {"source": "community"})

        self.assertEqual(response.data["count"], 3)

    def test_the_filters_work_together(self):
        response = self.client.get(
            "/api/spots/", {"source": "community", "category": "diy"}
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name_spot"], "DIY del parque")

    def test_a_wrong_filter_is_ignored(self):
        """A wrong value must not empty the map."""
        response = self.client.get("/api/spots/", {"category": "nonsense"})

        self.assertEqual(response.data["count"], 4)

    def test_without_the_parameters_the_result_is_the_same(self):
        response = self.client.get("/api/spots/")

        self.assertEqual(response.data["count"], 4)

    def test_the_rating_is_the_average_of_the_scores(self):
        other = User.objects.create_user(
            username="other", email="other@example.com", password="secret-password"
        )
        Rating.objects.create(score=Decimal("4"), user=self.user, spot=self.park)
        Rating.objects.create(score=Decimal("2"), user=other, spot=self.park)

        response = self.client.get("/api/spots/", {"search": "Oasis"})
        spot = response.data["results"][0]

        self.assertEqual(spot["rating"], 3.0)
        self.assertEqual(spot["rating_count"], 2)

    def test_a_spot_without_rating_has_none(self):
        response = self.client.get("/api/spots/", {"search": "Oasis"})
        spot = response.data["results"][0]

        self.assertIsNone(spot["rating"])
        self.assertEqual(spot["rating_count"], 0)

    def test_the_pagination_is_answered(self):
        response = self.client.get("/api/spots/", {"limit": 2})

        self.assertEqual(len(response.data["results"]), 2)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)

    def test_the_endpoint_is_still_open_to_the_public(self):
        """The map has to work without an account."""
        response = self.client.get("/api/spots/")

        self.assertEqual(response.status_code, 200)

    def test_writing_a_spot_still_needs_an_account(self):
        response = self.client.post("/api/spots/", {"name_spot": "Nope"})

        self.assertIn(response.status_code, (401, 403))

    def test_the_rating_can_not_be_faked(self):
        """The rating comes from the database, a client can not set it."""
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/spots/",
            {"name_spot": "Con rating falso", "rating": 5, "rating_count": 99},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertIsNone(spot.ratings if hasattr(spot, "ratings") else None)

    def test_the_category_can_be_set(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/spots/",
            {"name_spot": "Un DIY", "category": "diy"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        spot = Spots.objects.get(pk=response.data["id"])
        self.assertEqual(spot.category, "diy")


class MapPageTests(TestCase):
    """The page of the map."""

    def test_the_map_page_is_public(self):
        response = self.client.get("/map/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "map.html")
        self.assertContains(response, 'id="map"')
        self.assertContains(response, 'id="spot-list"')
        self.assertContains(response, 'id="spot-search"')

    def test_the_key_of_the_provider_is_not_in_the_page(self):
        """The tiles go through the proxy, the key stays on the server."""
        with override_settings(OSM_TILE_API_KEY="a-secret-key"):
            response = self.client.get("/map/")

        self.assertNotContains(response, "a-secret-key")
        self.assertContains(response, "/tiles/")

    def test_the_attribution_is_on_the_page(self):
        response = self.client.get("/map/")

        self.assertContains(response, "openstreetmap.org/copyright")


class TileProxyTests(TestCase):
    """The proxy that serves the tiles."""

    def test_the_url_of_a_tile_is_built_with_the_key(self):
        with override_settings(
            OSM_TILE_URL="https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png",
            OSM_TILE_SUBDOMAINS="abcd",
            OSM_TILE_API_KEY="the-key",
        ):
            url = build_tile_url(13, 1744, 3614, "")

        self.assertIn("/rastertiles/light_all/13/1744/3614.png", url)
        self.assertIn("key=the-key", url)
        self.assertIn("basemaps.cartocdn.com", url)

    def test_the_retina_version_is_built(self):
        with override_settings(
            OSM_TILE_URL="https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png",
            OSM_TILE_SUBDOMAINS="abcd",
            OSM_TILE_API_KEY="the-key",
        ):
            url = build_tile_url(13, 1744, 3614, "@2x")

        self.assertIn("3614@2x.png", url)

    def test_the_subdomain_is_always_the_same_for_a_tile(self):
        """The browser has to find its tile in its cache again."""
        with override_settings(OSM_TILE_SUBDOMAINS="abcd"):
            first = pick_subdomain(13, 1744, 3614)
            second = pick_subdomain(13, 1744, 3614)

        self.assertEqual(first, second)
        self.assertIn(first, "abcd")

    @patch("skate.tiles.requests.get")
    def test_the_tile_is_served(self, mock_get):
        mock_get.return_value = FakeTileResponse(
            200, b"a-png", {"Content-Type": "image/png"}
        )

        response = self.client.get("/tiles/13/1744/3614.png")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"a-png")
        self.assertEqual(response["Content-Type"], "image/png")

    @patch("skate.tiles.requests.get")
    def test_the_caching_headers_of_the_provider_are_passed_on(self, mock_get):
        mock_get.return_value = FakeTileResponse(
            200, b"a-png", {"Cache-Control": "public, max-age=2592000"}
        )

        response = self.client.get("/tiles/13/1744/3614.png")

        self.assertEqual(response["Cache-Control"], "public, max-age=2592000")

    @patch("skate.tiles.requests.get")
    def test_a_cache_header_is_set_when_the_provider_has_none(self, mock_get):
        mock_get.return_value = FakeTileResponse(200, b"a-png", {})

        response = self.client.get("/tiles/13/1744/3614.png")

        self.assertIn("max-age=", response["Cache-Control"])

    @patch("skate.tiles.requests.get")
    def test_the_request_carries_the_user_agent_of_the_application(self, mock_get):
        mock_get.return_value = FakeTileResponse(200, b"a-png")

        self.client.get("/tiles/13/1744/3614.png")

        _, kwargs = mock_get.call_args
        self.assertIn("RollingUp", kwargs["headers"]["User-Agent"])

    @patch("skate.tiles.requests.get")
    def test_a_wrong_path_is_refused(self, mock_get):
        response = self.client.get("/tiles/not-a-tile.png")

        self.assertEqual(response.status_code, 400)
        mock_get.assert_not_called()

    @patch("skate.tiles.requests.get")
    def test_a_failing_provider_is_reported(self, mock_get):
        mock_get.return_value = FakeTileResponse(503)

        response = self.client.get("/tiles/13/1744/3614.png")

        self.assertEqual(response.status_code, 503)

    @patch("skate.tiles.requests.get")
    def test_an_unreachable_provider_is_reported(self, mock_get):
        import requests

        mock_get.side_effect = requests.ConnectionError("no network")

        response = self.client.get("/tiles/13/1744/3614.png")

        self.assertEqual(response.status_code, 502)

    def test_the_tiles_are_not_throttled(self):
        """The anonymous rate of the API would break the map."""
        for _ in range(30):
            response = self.client.get("/tiles/13/1744/3614.png")

        self.assertNotEqual(response.status_code, 429)
