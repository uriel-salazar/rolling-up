"""Tests for the live, non-persistent OpenStreetMap discovery API."""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from skate.models import Spots
from skate.osm.discovery import discover_nearby, discover_viewport
from skate.osm.exceptions import OverpassRequestError

from .helpers import node_element, overpass_payload, relation_element, way_element

TAGS = {"leisure": "skatepark", "name": "Skatepark"}


class DiscoveryTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.elements = [
            node_element(1, 41.3851, 2.1734, TAGS),
            way_element(2, 41.3900, 2.1800, {"leisure": "skatepark", "name": "Way park"}),
            relation_element(
                3, 41.4000, 2.1900, {"leisure": "skatepark", "name": "Relation park"}
            ),
        ]

    def get_nearby(self, **params):
        values = {"lat": 41.3851, "lon": 2.1734, "radius": 10000}
        values.update(params)
        return self.client.get("/api/spots/nearby/", values)

    def get_viewport(self, **params):
        values = {"south": 41.30, "west": 2.10, "north": 41.45, "east": 2.25}
        values.update(params)
        return self.client.get("/api/spots/viewport/", values)


class NearbyEndpointTests(DiscoveryTestCase):
    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_nodes_ways_and_relations_are_normalised(self, mock_fetch):
        mock_fetch.return_value = self.elements

        response = self.get_nearby()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["source"], "openstreetmap")
        self.assertIn("OpenStreetMap", response.data["attribution"])
        types = {item["osm_type"] for item in response.data["results"]}
        self.assertEqual(types, {"node", "way", "relation"})
        self.assertEqual(response.data["results"][0]["source"], "osm")
        self.assertTrue(response.data["results"][0]["external"])
        self.assertTrue(response.data["results"][0]["id"].startswith("osm:"))

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_the_query_is_bounded_and_only_uses_skateparks(self, mock_fetch):
        mock_fetch.return_value = []

        self.get_nearby(radius=12000)

        query = mock_fetch.call_args[0][0]
        self.assertIn('nwr["leisure"="skatepark"]', query)
        self.assertIn("around:12000", query)
        self.assertNotIn("sport", query)

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_duplicate_osm_objects_are_removed(self, mock_fetch):
        mock_fetch.return_value = self.elements + [self.elements[0]]

        response = self.get_nearby()

        self.assertEqual(response.data["count"], 3)

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_an_unnamed_skatepark_is_kept(self, mock_fetch):
        mock_fetch.return_value = [
            node_element(9, 41.3851, 2.1734, {"leisure": "skatepark"})
        ]

        response = self.get_nearby()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Unnamed skatepark", response.data["results"][0]["name_spot"])

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_the_results_are_not_saved_to_the_database(self, mock_fetch):
        mock_fetch.return_value = self.elements

        before = Spots.objects.count()
        self.get_nearby()

        self.assertEqual(Spots.objects.count(), before)

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_an_osm_image_is_reused_without_being_downloaded(self, mock_fetch):
        mock_fetch.return_value = [
            way_element(
                7,
                41.3851,
                2.1734,
                {
                    "leisure": "skatepark",
                    "name": "Photo park",
                    "image": "https://example.org/park.jpg",
                    "image:license": "CC-BY-4.0",
                    "image:attribution": "A mapper",
                },
            )
        ]

        response = self.get_nearby()
        result = response.data["results"][0]

        self.assertEqual(result["image_url"], "https://example.org/park.jpg")
        self.assertEqual(result["image_license"], "CC-BY-4.0")
        self.assertEqual(result["image_source"], "osm")

    def test_invalid_coordinates_are_rejected(self):
        response = self.get_nearby(lat=200)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["results"], [])

    def test_an_invalid_radius_is_rejected(self):
        self.assertEqual(self.get_nearby(radius=500000).status_code, 400)
        self.assertEqual(self.get_nearby(radius=0.5).status_code, 400)

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_the_answer_is_cached(self, mock_fetch):
        mock_fetch.return_value = self.elements

        first = self.get_nearby()
        second = self.get_nearby()

        self.assertFalse(first.data["cached"])
        self.assertTrue(second.data["cached"])
        self.assertEqual(mock_fetch.call_count, 1)

    @override_settings(OVERPASS_DISCOVERY_CACHE_SECONDS=0)
    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_a_stale_cache_is_used_when_overpass_fails(self, mock_fetch):
        mock_fetch.return_value = self.elements
        first = discover_nearby(41.3851, 2.1734, radius=10000)

        mock_fetch.side_effect = OverpassRequestError("overpass down")
        second = discover_nearby(41.3851, 2.1734, radius=10000)

        self.assertFalse(first["stale"])
        self.assertTrue(second["stale"])
        self.assertEqual(second["count"], 3)

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_an_overpass_failure_without_cache_is_a_503(self, mock_fetch):
        mock_fetch.side_effect = OverpassRequestError("overpass down")

        response = self.get_nearby()

        self.assertEqual(response.status_code, 503)

    @override_settings(OVERPASS_DISCOVERY_MAX_RESULTS=2)
    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_the_number_of_results_is_limited(self, mock_fetch):
        mock_fetch.return_value = self.elements

        response = self.get_nearby()

        self.assertEqual(response.data["count"], 2)


class ViewportEndpointTests(DiscoveryTestCase):
    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_the_viewport_query_uses_the_bounding_box(self, mock_fetch):
        mock_fetch.return_value = self.elements

        response = self.get_viewport()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["area"]["type"], "viewport")
        query = mock_fetch.call_args[0][0]
        self.assertIn("41.300000,2.100000,41.450000,2.250000", query)
        self.assertIn('nwr["leisure"="skatepark"]', query)

    def test_reversed_bounds_are_rejected(self):
        response = self.get_viewport(south=42, north=41)

        self.assertEqual(response.status_code, 400)

    @override_settings(OVERPASS_DISCOVERY_MAX_VIEWPORT_SPAN=0.5)
    def test_a_giant_viewport_is_rejected(self):
        response = self.get_viewport(south=0, west=0, north=20, east=20)

        self.assertEqual(response.status_code, 400)

    @patch("skate.osm.discovery.OverpassClient.fetch_elements")
    def test_nearby_and_viewport_deduplicate_by_osm_identity(self, mock_fetch):
        mock_fetch.return_value = self.elements

        viewport = discover_viewport(41.30, 2.10, 41.45, 2.25)
        nearby = discover_nearby(41.3851, 2.1734, radius=10000)

        ids = [item["id"] for item in viewport["results"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {item["id"] for item in nearby["results"]})
