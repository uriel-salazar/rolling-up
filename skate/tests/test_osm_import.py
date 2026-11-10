"""Tests for the database import and for the management command.

The Overpass API is always mocked: the test suite never depends on a
live connection.
"""

from __future__ import annotations

import logging
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from skate.models import Spots
from skate.osm.importer import get_or_create_service_user, import_spots
from skate.osm.parser import parse_element

from .helpers import FakeResponse, overpass_payload

User = get_user_model()

SKATEPARK_TAGS = {"leisure": "skatepark", "name": "Paseo San Ignacio Skatepark"}

# The fallback to the geocoded bounding box is logged as a warning.
logging.getLogger("skate.osm.service").setLevel(logging.CRITICAL)


class ImporterTestCase(TestCase):
    """Base class providing the fixtures used by the import tests."""

    def setUp(self):
        self.community_user = User.objects.create_user(
            username="skater", email="skater@example.com", password="secret-password"
        )
        self.community_spot = Spots.objects.create(
            name_spot="las cañadas",
            body="my own description",
            user=self.community_user,
            source=Spots.SOURCE_COMMUNITY,
        )

    def make_spot(self, osm_id=460637542, osm_type="way", name="Skatepark"):
        element = {
            "type": osm_type,
            "id": osm_id,
            "center": {"lat": 20.6710727, "lon": -103.4050567},
            "tags": {"leisure": "skatepark", "name": name},
        }
        spot, _ = parse_element(element)
        return spot


class ImportSpotsTests(ImporterTestCase):
    """The importer writes the skateparks without touching anything else."""

    def test_creates_a_new_osm_spot(self):
        spot = self.make_spot()

        summary = import_spots([spot])

        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.updated, 0)

        created = Spots.objects.get(osm_type="way", osm_id=460637542)
        self.assertEqual(created.name_spot, "Skatepark")
        self.assertEqual(created.source, Spots.SOURCE_OSM)
        self.assertAlmostEqual(float(created.latitude), 20.6710727, places=6)
        self.assertAlmostEqual(float(created.longitude), -103.4050567, places=6)
        self.assertEqual(created.osm_metadata["license"], "ODbL-1.0")

    def test_the_imported_spot_is_owned_by_the_service_account(self):
        service_user = get_or_create_service_user()

        import_spots([self.make_spot()])

        created = Spots.objects.get(osm_type="way", osm_id=460637542)
        self.assertEqual(created.user, service_user)

    def test_the_service_account_cannot_be_logged_into(self):
        service_user = get_or_create_service_user()

        self.assertFalse(service_user.has_usable_password())

    def test_community_spots_are_never_modified(self):
        original_body = self.community_spot.body
        original_source = self.community_spot.source

        import_spots([self.make_spot()])

        self.community_spot.refresh_from_db()
        self.assertEqual(self.community_spot.body, original_body)
        self.assertEqual(self.community_spot.source, original_source)
        self.assertEqual(self.community_spot.user, self.community_user)

    def test_a_duplicated_osm_object_is_not_created_twice(self):
        spot = self.make_spot()

        import_spots([spot])
        summary = import_spots([spot])

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.unchanged, 1)
        self.assertEqual(
            Spots.objects.filter(osm_type="way", osm_id=460637542).count(), 1
        )

    def test_repeated_imports_update_the_record(self):
        import_spots([self.make_spot(name="Old name")])

        element = {
            "type": "way",
            "id": 460637542,
            "center": {"lat": 20.68, "lon": -103.40},
            "tags": {"leisure": "skatepark", "name": "New name"},
        }
        spot, _ = parse_element(element)

        summary = import_spots([spot])

        self.assertEqual(summary.updated, 1)
        created = Spots.objects.get(osm_type="way", osm_id=460637542)
        self.assertEqual(created.name_spot, "New name")
        self.assertEqual(float(created.latitude), 20.68)

    def test_repeated_imports_without_changes_report_unchanged(self):
        spot = self.make_spot()

        import_spots([spot])
        summary = import_spots([spot])

        self.assertEqual(summary.unchanged, 1)
        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.updated, 0)

    def test_a_user_edited_description_is_preserved(self):
        spot = self.make_spot()
        import_spots([spot])

        created = Spots.objects.get(osm_type="way", osm_id=460637542)
        created.body = "my own description"
        created.save(update_fields=["body"])

        element = {
            "type": "way",
            "id": 460637542,
            "center": {"lat": 20.6710727, "lon": -103.4050567},
            "tags": {
                "leisure": "skatepark",
                "name": "Skatepark",
                "description": "a new OSM description",
            },
        }
        new_spot, _ = parse_element(element)

        import_spots([new_spot])

        created.refresh_from_db()
        self.assertEqual(created.body, "my own description")

    def test_an_osm_description_is_written_when_the_body_is_empty(self):
        spot = self.make_spot()
        import_spots([spot])

        created = Spots.objects.get(osm_type="way", osm_id=460637542)
        created.body = None
        created.save(update_fields=["body"])

        element = {
            "type": "way",
            "id": 460637542,
            "center": {"lat": 20.6710727, "lon": -103.4050567},
            "tags": {
                "leisure": "skatepark",
                "name": "Skatepark",
                "description": "a new OSM description",
            },
        }
        new_spot, _ = parse_element(element)

        import_spots([new_spot])

        created.refresh_from_db()
        self.assertEqual(created.body, "a new OSM description")

    def test_the_photo_of_an_imported_spot_is_never_removed(self):
        spot = self.make_spot()
        import_spots([spot])

        created = Spots.objects.get(osm_type="way", osm_id=460637542)
        created.image_url = "spots/photo.jpg"
        created.save(update_fields=["image_url"])

        import_spots([self.make_spot(name="Another name")])

        created.refresh_from_db()
        self.assertEqual(created.image_url, "spots/photo.jpg")

    def test_a_dry_run_does_not_touch_the_database(self):
        spot = self.make_spot()

        summary = import_spots([spot], dry_run=True)

        self.assertEqual(summary.created, 1)
        self.assertEqual(Spots.objects.filter(osm_id=460637542).count(), 0)
        self.assertFalse(User.objects.filter(username="osm_importer").exists())

    def test_a_dry_run_reports_the_existing_records_as_updates(self):
        import_spots([self.make_spot()])

        summary = import_spots([self.make_spot()], dry_run=True)

        self.assertEqual(summary.updated, 1)
        self.assertEqual(summary.created, 0)

    def test_ratings_are_untouched(self):
        from skate.models import Rating

        spot = self.make_spot()
        import_spots([spot])
        created = Spots.objects.get(osm_type="way", osm_id=460637542)

        Rating.objects.create(
            score="4.5", user=self.community_user, spot=created
        )

        import_spots([self.make_spot(name="Renamed")])

        self.assertEqual(Rating.objects.filter(spot=created).count(), 1)
        self.assertEqual(Rating.objects.get(spot=created).score, 4.5)


class ManagementCommandTests(ImporterTestCase):
    """The management command drives the whole import."""

    def call_command(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()
        call_command("import_osm_skateparks", *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue()

    @patch("requests.Session.post")
    def test_imports_the_skateparks_of_a_location(self, mock_post):
        mock_post.return_value = FakeResponse(
            200,
            overpass_payload(
                [
                    {
                        "type": "way",
                        "id": 460637542,
                        "center": {"lat": 20.6710727, "lon": -103.4050567},
                        "tags": SKATEPARK_TAGS,
                    }
                ]
            ),
        )

        output = self.call_command("--location", "Guadalajara, Jalisco, Mexico")

        self.assertIn("created:  1", output)
        self.assertEqual(
            Spots.objects.filter(source=Spots.SOURCE_OSM).count(), 1
        )

    @patch("requests.Session.post")
    def test_defaults_to_guadalajara(self, mock_post):
        mock_post.return_value = FakeResponse(200, overpass_payload([]))

        self.call_command()

        _, kwargs = mock_post.call_args
        query = kwargs["data"]["data"]
        self.assertIn("Guadalajara, Jalisco, Mexico", query)

    @patch("requests.Session.post")
    def test_a_dry_run_leaves_the_database_untouched(self, mock_post):
        mock_post.return_value = FakeResponse(
            200,
            overpass_payload(
                [
                    {
                        "type": "way",
                        "id": 460637542,
                        "center": {"lat": 20.6710727, "lon": -103.4050567},
                        "tags": SKATEPARK_TAGS,
                    }
                ]
            ),
        )

        output = self.call_command("--dry-run")

        self.assertIn("Dry run", output)
        self.assertEqual(Spots.objects.filter(source=Spots.SOURCE_OSM).count(), 0)

    @patch("requests.Session.post")
    def test_reports_the_skipped_objects(self, mock_post):
        mock_post.return_value = FakeResponse(
            200,
            overpass_payload(
                [
                    {
                        "type": "node",
                        "id": 99,
                        "lat": 20.0,
                        "lon": -103.0,
                        "tags": {"amenity": "cafe"},
                    }
                ]
            ),
        )

        output = self.call_command()

        self.assertIn("1 object(s) skipped", output)

    @patch("requests.Session.post")
    def test_reports_an_api_failure(self, mock_post):
        from skate.osm.exceptions import OverpassRequestError

        mock_post.side_effect = OverpassRequestError("Overpass is down")

        with self.assertRaises(CommandError):
            self.call_command()

    @patch("requests.Session.post")
    def test_reports_a_geocoding_failure(self, mock_post):
        from skate.osm.exceptions import OverpassQueryError

        mock_post.return_value = FakeResponse(
            400, text="<strong>Error</strong>: parse error"
        )

        with patch("requests.Session.get") as mock_get:
            mock_get.return_value = FakeResponse(200, [])
            with self.assertRaises(CommandError):
                self.call_command("--location", "Nowhere at all")

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_falls_back_to_a_geocoded_bounding_box(self, mock_post, mock_get):
        """When geocodeArea is refused, Nominatim provides the bbox."""
        mock_post.side_effect = [
            FakeResponse(400, text="<strong>Error</strong>: parse error"),
            FakeResponse(
                200,
                overpass_payload(
                    [
                        {
                            "type": "way",
                            "id": 460637542,
                            "center": {"lat": 20.6710727, "lon": -103.4050567},
                            "tags": SKATEPARK_TAGS,
                        }
                    ]
                ),
            ),
        ]
        mock_get.return_value = FakeResponse(
            200,
            [
                {
                    "boundingbox": [
                        "20.6037373",
                        "20.7526990",
                        "-103.4071049",
                        "-103.2637039",
                    ]
                }
            ],
        )

        output = self.call_command("--location", "Guadalajara, Jalisco, Mexico")

        self.assertIn("created:  1", output)
        self.assertEqual(Spots.objects.filter(source=Spots.SOURCE_OSM).count(), 1)

    @patch("requests.Session.post")
    def test_an_explicit_bbox_skips_the_area_resolution(self, mock_post):
        mock_post.return_value = FakeResponse(200, overpass_payload([]))

        self.call_command("--bbox", "20.60,-103.50,20.75,-103.30")

        _, kwargs = mock_post.call_args
        query = kwargs["data"]["data"]
        self.assertIn("(20.6,-103.5,20.75,-103.3)", query)
        self.assertNotIn("geocodeArea", query)

    @patch("requests.Session.post")
    def test_running_the_command_twice_does_not_duplicate(self, mock_post):
        mock_post.return_value = FakeResponse(
            200,
            overpass_payload(
                [
                    {
                        "type": "way",
                        "id": 460637542,
                        "center": {"lat": 20.6710727, "lon": -103.4050567},
                        "tags": SKATEPARK_TAGS,
                    }
                ]
            ),
        )

        self.call_command()
        output = self.call_command()

        self.assertIn("created:  0", output)
        self.assertEqual(Spots.objects.filter(source=Spots.SOURCE_OSM).count(), 1)
