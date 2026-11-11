"""Tests for the Google Places integration and the image resolver."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from skate.google_places.client import GooglePlacesClient
from skate.google_places.importer import import_places
from skate.google_places.parser import parse_place
from skate.media_api.images_skateparks.resolver import resolve_spot_image
from skate.models import Spots
from skate.serializers import SpotSerializer

User = get_user_model()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content
        self.headers = headers or {}
        self.text = ""

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload


def google_place(place_id="ChIJ-skate-1", name="Skatepark Oasis",
                 latitude=20.706324, longitude=-103.363065):
    return {
        "id": place_id,
        "displayName": {"text": name, "languageCode": "es"},
        "formattedAddress": "Av. Skate 123, Guadalajara",
        "location": {"latitude": latitude, "longitude": longitude},
        "rating": 4.5,
        "userRatingCount": 25,
        "businessStatus": "OPERATIONAL",
        "photos": [
            {
                "name": f"places/{place_id}/photos/photo-ref",
                "widthPx": 1200,
                "heightPx": 800,
                "authorAttributions": [
                    {"displayName": "Skater", "uri": "https://maps.google.com/skater"}
                ],
            }
        ],
    }


class ClientTests(SimpleTestCase):
    @override_settings(GOOGLE_PLACES_API_KEY="the-key")
    @patch("requests.Session.post")
    def test_nearby_search_is_restricted_to_skateboard_parks(self, mock_post):
        mock_post.return_value = FakeResponse(200, {"places": []})

        client = GooglePlacesClient()
        client.search_nearby(20.7, -103.3, radius=1000)

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["includedTypes"], ["skateboard_park"])
        self.assertEqual(kwargs["json"]["locationRestriction"]["circle"]["radius"], 1000)
        self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "the-key")
        self.assertIn("places.id", kwargs["headers"]["X-Goog-FieldMask"])
        self.assertIn("places.photos", kwargs["headers"]["X-Goog-FieldMask"])

    @override_settings(GOOGLE_PLACES_API_KEY="the-key")
    @patch("requests.Session.get")
    def test_photo_is_fetched_with_the_key_on_the_server(self, mock_get):
        mock_get.return_value = FakeResponse(
            200, content=b"jpeg", headers={"Content-Type": "image/jpeg"}
        )

        client = GooglePlacesClient()
        photo = client.fetch_photo("places/abc/photos/ref", max_width=800)

        self.assertEqual(photo["content"], b"jpeg")
        self.assertEqual(photo["content_type"], "image/jpeg")
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["key"], "the-key")
        self.assertEqual(kwargs["params"]["maxWidthPx"], 800)


class ParserTests(SimpleTestCase):
    def test_place_is_normalised(self):
        place = parse_place(google_place())

        self.assertEqual(place.place_id, "ChIJ-skate-1")
        self.assertEqual(place.name, "Skatepark Oasis")
        self.assertEqual(place.address, "Av. Skate 123, Guadalajara")
        self.assertEqual(place.rating, 4.5)
        self.assertEqual(place.photos[0]["attribution"], "Skater")
        self.assertIn("expires_at", place.metadata)

    def test_non_operational_place_is_skipped(self):
        data = google_place()
        data["businessStatus"] = "CLOSED_PERMANENTLY"

        self.assertIsNone(parse_place(data))


class ImporterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )

    def test_import_creates_a_google_spot(self):
        summary = import_places([parse_place(google_place())])

        self.assertEqual(summary.created, 1)
        spot = Spots.objects.get(google_place_id="ChIJ-skate-1")
        self.assertEqual(spot.source, Spots.SOURCE_GOOGLE)
        self.assertEqual(spot.category, Spots.CATEGORY_SKATEPARK)

    def test_import_deduplicates_against_an_osm_spot(self):
        existing = Spots.objects.create(
            name_spot="Skatepark Oasis",
            user=self.user,
            source=Spots.SOURCE_OSM,
            category=Spots.CATEGORY_SKATEPARK,
            latitude=Decimal("20.706324"),
            longitude=Decimal("-103.363065"),
        )

        summary = import_places([parse_place(google_place())])

        existing.refresh_from_db()
        self.assertEqual(summary.created, 0)
        self.assertEqual(existing.google_place_id, "ChIJ-skate-1")
        self.assertEqual(Spots.objects.count(), 1)

    def test_osm_import_merges_a_google_spot(self):
        from skate.osm.importer import import_spots
        from skate.osm.parser import parse_element

        import_places([parse_place(google_place())])

        element = {
            "type": "node",
            "id": 99,
            "lat": 20.706324,
            "lon": -103.363065,
            "tags": {"leisure": "skatepark", "name": "Skatepark Oasis"},
        }
        spot, _ = parse_element(element)
        summary = import_spots([spot])

        merged = Spots.objects.get(google_place_id="ChIJ-skate-1")
        self.assertEqual(summary.created, 0)
        self.assertEqual(merged.osm_id, 99)
        self.assertEqual(Spots.objects.count(), 1)


class ImageResolverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )

    def test_google_photo_is_used_when_available(self):
        place = parse_place(google_place())
        spot = Spots.objects.create(
            name_spot="Skatepark Oasis", user=self.user,
            source=Spots.SOURCE_GOOGLE,
            google_place_id=place.place_id,
            google_metadata=place.metadata,
        )

        image = resolve_spot_image(spot)

        self.assertEqual(image["source"], "google")
        self.assertIn("/api/places/photo/places/", image["url"])
        self.assertEqual(image["attribution"], "Skater")

    def test_licensed_osm_image_is_used(self):
        spot = Spots.objects.create(
            name_spot="Skatepark Oasis", user=self.user,
            source=Spots.SOURCE_OSM,
            osm_metadata={
                "image": {
                    "url": "https://example.org/park.jpg",
                    "attribution": "Mapper",
                    "license": "CC-BY-4.0",
                    "usable": True,
                }
            },
        )

        image = resolve_spot_image(spot)

        self.assertEqual(image["url"], "https://example.org/park.jpg")
        self.assertEqual(image["license"], "CC-BY-4.0")

    def test_uploaded_image_has_priority(self):
        spot = Spots.objects.create(
            name_spot="Skatepark Oasis", user=self.user,
            source=Spots.SOURCE_GOOGLE,
            google_place_id="abc",
            google_metadata=parse_place(google_place()).metadata,
        )
        spot.image_url = "spots/park.jpg"
        spot.save()

        image = resolve_spot_image(spot)

        self.assertEqual(image["source"], "community")

    def test_spot_without_images_keeps_the_placeholder(self):
        spot = Spots.objects.create(
            name_spot="Skatepark Oasis", user=self.user,
            source=Spots.SOURCE_OSM,
        )

        self.assertIsNone(resolve_spot_image(spot))

    def test_serializer_keeps_the_image_url_contract(self):
        place = parse_place(google_place())
        spot = Spots.objects.create(
            name_spot="Skatepark Oasis", user=self.user,
            source=Spots.SOURCE_GOOGLE,
            google_place_id=place.place_id,
            google_metadata=place.metadata,
        )

        data = SpotSerializer(spot).data

        self.assertIn("/api/places/photo/places/", data["image_url"])
        self.assertEqual(data["image_source"], "google")
        self.assertEqual(data["address"], "Av. Skate 123, Guadalajara")

    def test_stale_metadata_is_not_exposed(self):
        place = parse_place(google_place())
        metadata = dict(place.metadata)
        metadata["expires_at"] = (
            timezone.now() - timedelta(days=1)
        ).isoformat()
        spot = Spots.objects.create(
            name_spot="Old place", user=self.user,
            source=Spots.SOURCE_GOOGLE,
            google_place_id=place.place_id,
            google_metadata=metadata,
        )

        data = SpotSerializer(spot).data

        self.assertIsNone(data["google_metadata"])
        self.assertIsNone(data["image_url"])

class PhotoProxyTests(TestCase):
    @override_settings(GOOGLE_PLACES_API_KEY="")
    def test_without_a_key_the_proxy_is_unavailable(self):
        response = self.client.get("/api/places/photo/places/abc/photos/ref")

        self.assertEqual(response.status_code, 503)

    def test_a_wrong_reference_is_refused(self):
        response = self.client.get("/api/places/photo/not-a-photo")

        self.assertEqual(response.status_code, 400)

    @override_settings(GOOGLE_PLACES_API_KEY="the-key")
    @patch("skate.google_places.views.GooglePlacesClient.fetch_photo")
    def test_the_photo_is_served(self, mock_fetch):
        mock_fetch.return_value = {
            "content": b"jpeg", "content_type": "image/jpeg"
        }

        response = self.client.get("/api/places/photo/places/abc/photos/ref")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"jpeg")
        self.assertIn("max-age=", response["Cache-Control"])
        self.assertNotIn("the-key", response.content.decode("latin-1"))


class PurgeCommandTests(TestCase):
    def test_expired_metadata_is_deleted(self):
        from skate.models import User as UserModel

        user = UserModel.objects.create_user(
            username="purger", email="purger@example.com", password="secret-password"
        )
        place = parse_place(google_place())
        metadata = dict(place.metadata)
        metadata["expires_at"] = (
            timezone.now() - timedelta(seconds=1)
        ).isoformat()
        spot = Spots.objects.create(
            name_spot="Old place", user=user,
            source=Spots.SOURCE_GOOGLE,
            google_place_id=place.place_id,
            google_metadata=metadata,
        )

        call_command("purge_google_places_cache", stdout=StringIO())

        spot.refresh_from_db()
        self.assertIsNone(spot.google_metadata)
