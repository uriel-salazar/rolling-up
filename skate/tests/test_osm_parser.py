"""Tests for the OpenStreetMap element normalisation."""

from __future__ import annotations

from django.test import SimpleTestCase

from skate.osm.parser import (
    ALL_TAG_FILTERS,
    extract_coordinates,
    extract_description,
    extract_image,
    extract_website,
    is_skatepark,
    parse_element,
    parse_elements,
)

from .helpers import node_element, relation_element, way_element


class ParseElementTests(SimpleTestCase):
    """The parser turns raw Overpass elements into importable records."""

    def test_parses_a_node(self):
        element = node_element(
            1234,
            20.671072,
            -103.405056,
            {"leisure": "skatepark", "name": "Parque de las Americas"},
        )

        spot, reason = parse_element(element)

        self.assertIsNotNone(spot)
        self.assertEqual(reason, "")
        self.assertEqual(spot.osm_type, "node")
        self.assertEqual(spot.osm_id, 1234)
        self.assertEqual(spot.name, "Parque de las Americas")
        self.assertEqual(float(spot.latitude), 20.671072)
        self.assertEqual(float(spot.longitude), -103.405056)

    def test_parses_a_way_using_its_centre(self):
        element = way_element(
            460637542,
            20.6710727,
            -103.4050567,
            {"leisure": "skatepark", "name": "Paseo San Ignacio Skatepark"},
        )

        spot, reason = parse_element(element)

        self.assertIsNotNone(spot)
        self.assertEqual(reason, "")
        self.assertEqual(spot.osm_type, "way")
        self.assertEqual(spot.osm_id, 460637542)
        self.assertEqual(float(spot.latitude), 20.6710727)
        self.assertEqual(float(spot.longitude), -103.4050567)

    def test_parses_a_relation_using_its_centre(self):
        element = relation_element(
            9999,
            20.700000,
            -103.350000,
            {"leisure": "skatepark", "name": "Skatepark Centro"},
        )

        spot, reason = parse_element(element)

        self.assertIsNotNone(spot)
        self.assertEqual(reason, "")
        self.assertEqual(spot.osm_type, "relation")
        self.assertEqual(float(spot.latitude), 20.700000)

    def test_node_without_tags_is_skipped(self):
        spot, reason = parse_element(node_element(1, 20.0, -103.0))

        self.assertIsNone(spot)
        self.assertIn("not tagged as a skatepark", reason)

    def test_missing_name_uses_a_labelled_placeholder(self):
        element = way_element(42, 20.0, -103.0, {"leisure": "skatepark"})

        spot, reason = parse_element(element)

        self.assertIsNotNone(spot)
        self.assertEqual(reason, "")
        self.assertEqual(spot.name, "Unnamed skatepark (way 42)")

    def test_missing_optional_tags_are_stored_as_none(self):
        element = node_element(7, 20.0, -103.0, {"leisure": "skatepark"})

        spot, _ = parse_element(element)

        self.assertIsNone(spot.description)
        self.assertIsNone(spot.metadata["access"])
        self.assertIsNone(spot.metadata["surface"])
        self.assertIsNone(spot.metadata["lit"])
        self.assertIsNone(spot.metadata["operator"])
        self.assertIsNone(spot.metadata["website"])

    def test_optional_tags_are_normalised(self):
        element = node_element(
            8,
            20.0,
            -103.0,
            {
                "leisure": "skatepark",
                "name": "La Calesa",
                "description": "Área de patinaje",
                "access": "public",
                "surface": "concrete",
                "lit": "yes",
                "operator": "Municipio de Guadalajara",
                "website": "https://example.org",
            },
        )

        spot, _ = parse_element(element)

        self.assertEqual(spot.description, "Área de patinaje")
        self.assertEqual(spot.metadata["access"], "public")
        self.assertEqual(spot.metadata["surface"], "concrete")
        self.assertEqual(spot.metadata["lit"], "yes")
        self.assertEqual(
            spot.metadata["operator"], "Municipio de Guadalajara"
        )
        self.assertEqual(spot.metadata["website"], "https://example.org")

    def test_only_skatepark_objects_are_requested(self):
        self.assertEqual(
            ALL_TAG_FILTERS, [{"key": "leisure", "value": "skatepark"}]
        )

    def test_a_licensed_image_is_normalised(self):
        tags = {
            "image": "https://example.org/park.jpg",
            "image:license": "CC-BY-4.0",
            "image:license:url": "https://creativecommons.org/licenses/by/4.0/",
            "image:attribution": "A mapper",
        }

        image = extract_image(tags)

        self.assertEqual(image["url"], "https://example.org/park.jpg")
        self.assertEqual(image["license"], "CC-BY-4.0")
        self.assertEqual(image["attribution"], "A mapper")
        self.assertTrue(image["usable"])

    def test_an_image_without_credit_is_not_marked_usable(self):
        image = extract_image({"image": "https://example.org/park.jpg"})

        self.assertFalse(image["usable"])

    def test_a_wikimedia_commons_file_becomes_a_direct_url(self):
        image = extract_image({"wikimedia_commons": "File:Skatepark.jpg"})

        self.assertIn("commons.wikimedia.org", image["url"])
        self.assertIn("Skatepark.jpg", image["url"])
        self.assertTrue(image["usable"])

    def test_metadata_keeps_the_attribution_and_the_license(self):
        element = node_element(9, 20.0, -103.0, {"leisure": "skatepark"})

        spot, _ = parse_element(element)

        self.assertEqual(spot.metadata["attribution"], "© OpenStreetMap contributors")
        self.assertEqual(spot.metadata["license"], "ODbL-1.0")
        self.assertEqual(spot.metadata["tags"]["leisure"], "skatepark")

    def test_element_without_coordinates_is_skipped(self):
        element = {"type": "way", "id": 55, "tags": {"leisure": "skatepark"}}

        spot, reason = parse_element(element)

        self.assertIsNone(spot)
        self.assertIn("no usable coordinates", reason)

    def test_element_with_out_of_range_coordinates_is_skipped(self):
        element = node_element(56, 500.0, -103.0, {"leisure": "skatepark"})

        spot, reason = parse_element(element)

        self.assertIsNone(spot)
        self.assertIn("no usable coordinates", reason)

    def test_element_with_non_numeric_coordinates_is_skipped(self):
        element = {
            "type": "node",
            "id": 57,
            "lat": "not-a-number",
            "lon": -103.0,
            "tags": {"leisure": "skatepark"},
        }

        spot, reason = parse_element(element)

        self.assertIsNone(spot)
        self.assertIn("no usable coordinates", reason)

    def test_element_with_invalid_id_is_skipped(self):
        element = {
            "type": "node",
            "id": "abc",
            "lat": 20.0,
            "lon": -103.0,
            "tags": {"leisure": "skatepark"},
        }

        spot, reason = parse_element(element)

        self.assertIsNone(spot)
        self.assertIn("invalid OSM id", reason)

    def test_element_with_unsupported_type_is_skipped(self):
        element = {
            "type": "area",
            "id": 10,
            "lat": 20.0,
            "lon": -103.0,
            "tags": {"leisure": "skatepark"},
        }

        spot, reason = parse_element(element)

        self.assertIsNone(spot)
        self.assertIn("Unsupported OSM object type", reason)


class SkateparkDetectionTests(SimpleTestCase):
    """Only real skateparks are imported."""

    def test_leisure_skatepark_is_accepted(self):
        self.assertTrue(is_skatepark({"leisure": "skatepark"}))

    def test_sport_skateboard_alone_is_rejected(self):
        self.assertFalse(is_skatepark({"sport": "skateboard"}))

    def test_sport_skateboard_inside_a_sports_centre_is_rejected(self):
        self.assertFalse(
            is_skatepark({"sport": "skateboard", "leisure": "sports_centre"})
        )

    def test_sport_skateboard_with_a_skatepark_name_is_rejected(self):
        self.assertFalse(
            is_skatepark({"sport": "skateboard", "name": "Skatepark del Centro"})
        )

    def test_unrelated_object_with_sport_skateboard_is_rejected(self):
        self.assertFalse(
            is_skatepark(
                {
                    "sport": "skateboard",
                    "leisure": "playground",
                    "name": "Parque infantil",
                }
            )
        )

    def test_object_without_relevant_tags_is_rejected(self):
        self.assertFalse(is_skatepark({"amenity": "cafe"}))


class ParseElementsTests(SimpleTestCase):
    """Parsing a whole payload keeps the good records and explains the rest."""

    def test_separates_valid_spots_from_skipped_ones(self):
        elements = [
            node_element(1, 20.0, -103.0, {"leisure": "skatepark"}),
            node_element(2, 20.0, -103.0, {"amenity": "cafe"}),
            way_element(3, 20.1, -103.1, {"leisure": "skatepark"}),
            {"type": "way", "id": 4, "tags": {"leisure": "skatepark"}},
        ]

        spots, skipped = parse_elements(elements)

        self.assertEqual(len(spots), 2)
        self.assertEqual(len(skipped), 2)
        self.assertEqual({spot.osm_id for spot in spots}, {1, 3})


class ExtractionHelperTests(SimpleTestCase):
    """The small helpers behave as expected on their own."""

    def test_extract_coordinates_prefers_the_node_position(self):
        element = node_element(1, 20.0, -103.0)
        element["center"] = {"lat": 99.0, "lon": 99.0}

        self.assertEqual(extract_coordinates(element), (20.0, -103.0))

    def test_extract_coordinates_falls_back_to_the_centre(self):
        element = way_element(1, 20.5, -103.5)

        self.assertEqual(extract_coordinates(element), (20.5, -103.5))

    def test_extract_description_prefers_description_over_note(self):
        tags = {"description": "Main one", "note": "Secondary"}

        self.assertEqual(extract_description(tags), "Main one")

    def test_extract_description_falls_back_to_note(self):
        self.assertEqual(extract_description({"note": "Only note"}), "Only note")

    def test_extract_website_supports_several_keys(self):
        self.assertEqual(
            extract_website({"contact:website": "https://a.test"}), "https://a.test"
        )
        self.assertIsNone(extract_website({}))
