"""Tests for the Overpass HTTP client.

Every test mocks the network, the suite never touches the live
Overpass API.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from skate.osm.client import OverpassClient, build_overpass_query
from skate.osm.exceptions import (
    OverpassQueryError,
    OverpassRequestError,
)

from .helpers import FakeResponse, connection_error, overpass_payload

# The client logs every retry, which would only clutter the test output.
logging.getLogger("skate.osm.client").setLevel(logging.CRITICAL)


def build_client(**kwargs):
    """Return a client that never waits between two attempts."""
    kwargs.setdefault("backoff", 0)
    kwargs.setdefault("max_retries", 2)
    return OverpassClient(**kwargs)


class OverpassClientTests(SimpleTestCase):
    """The client talks to Overpass correctly and survives failures."""

    @patch("requests.Session.post")
    def test_returns_the_elements_of_a_successful_response(self, mock_post):
        mock_post.return_value = FakeResponse(
            200, overpass_payload([{"type": "node", "id": 1}])
        )

        client = build_client()
        elements = client.fetch_elements("[out:json];node;out;")

        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]["id"], 1)

    @patch("requests.Session.post")
    def test_sends_the_query_and_a_user_agent(self, mock_post):
        mock_post.return_value = FakeResponse(200, overpass_payload([]))

        client = build_client()
        client.fetch_elements("[out:json];node;out;")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["data"], {"data": "[out:json];node;out;"})
        self.assertIn("RollingUp", kwargs["headers"]["User-Agent"])
        self.assertEqual(kwargs["timeout"], client.timeout)

    @patch("requests.Session.post")
    def test_a_rejected_query_raises_a_query_error(self, mock_post):
        mock_post.return_value = FakeResponse(
            400, text="<strong>Error</strong>: parse error"
        )

        client = build_client()

        with self.assertRaises(OverpassQueryError):
            client.fetch_elements("bad query")

        # A bad query is never retried.
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.Session.post")
    def test_a_connection_error_is_retried_and_then_reported(self, mock_post):
        mock_post.side_effect = connection_error()

        client = build_client()

        with self.assertRaises(OverpassRequestError):
            client.fetch_elements("[out:json];node;out;")

        self.assertEqual(mock_post.call_count, 3)

    @patch("requests.Session.post")
    def test_a_temporary_error_is_retried(self, mock_post):
        mock_post.side_effect = [
            FakeResponse(503),
            FakeResponse(200, overpass_payload([{"type": "node", "id": 1}])),
        ]

        client = build_client()
        elements = client.fetch_elements("[out:json];node;out;")

        self.assertEqual(len(elements), 1)
        self.assertEqual(mock_post.call_count, 2)

    @patch("requests.Session.post")
    def test_a_persistent_server_error_is_reported(self, mock_post):
        mock_post.return_value = FakeResponse(500)

        client = build_client()

        with self.assertRaises(OverpassRequestError):
            client.fetch_elements("[out:json];node;out;")

        self.assertEqual(mock_post.call_count, 3)

    @patch("requests.Session.post")
    def test_a_rate_limit_is_retried_after_the_retry_after_delay(self, mock_post):
        mock_post.side_effect = [
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(200, overpass_payload([])),
        ]

        client = build_client()
        elements = client.fetch_elements("[out:json];node;out;")

        self.assertEqual(elements, [])
        self.assertEqual(mock_post.call_count, 2)

    @patch("requests.Session.post")
    def test_an_invalid_json_answer_is_reported(self, mock_post):
        response = FakeResponse(200)
        response._payload = None

        mock_post.return_value = response

        client = build_client()

        with self.assertRaises(OverpassRequestError):
            client.fetch_elements("[out:json];node;out;")

    @patch("requests.Session.post")
    def test_a_payload_without_elements_is_reported(self, mock_post):
        mock_post.return_value = FakeResponse(200, {"remark": "runtime error"})

        client = build_client()

        with self.assertRaises(OverpassRequestError):
            client.fetch_elements("[out:json];node;out;")


class OverpassQueryBuilderTests(SimpleTestCase):
    """The generated Overpass QL is well formed."""

    def test_builds_a_query_for_every_tag_filter(self):
        query = build_overpass_query(
            "20.6,-103.5,20.8,-103.2",
            [
                {"key": "leisure", "value": "skatepark"},
                {"key": "sport", "value": "skateboard"},
            ],
        )

        self.assertIn("[out:json][timeout:60];", query)
        self.assertIn(
            'nwr["leisure"="skatepark"](20.6,-103.5,20.8,-103.2);', query
        )
        self.assertIn(
            'nwr["sport"="skateboard"](20.6,-103.5,20.8,-103.2);', query
        )
        self.assertTrue(query.endswith("out center tags;"))

    def test_uses_the_area_filter_when_an_area_is_given(self):
        query = build_overpass_query(
            "area.searchArea", [{"key": "leisure", "value": "skatepark"}]
        )

        self.assertIn('nwr["leisure"="skatepark"](area.searchArea);', query)
