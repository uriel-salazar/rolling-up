"""Tests for the rating of the spots.

They cover the endpoint that saves the stars, the list of the ratings
of a spot, the edit and the delete of the rating of a rider, and the
answer that the page uses to draw the average.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from skate.models import Rating, Spots

User = get_user_model()


class RatingApiTests(TestCase):
    """The endpoints the interface uses to rate a spot."""

    def setUp(self):
        self.rider = User.objects.create_user(
            username="rider", email="rider@example.com", password="secret-password"
        )
        self.other = User.objects.create_user(
            username="other", email="other@example.com", password="secret-password"
        )
        self.client = APIClient()

        self.spot = Spots.objects.create(
            name_spot="Skatepark Oasis",
            body="Un skatepark grande",
            user=self.rider,
            source=Spots.SOURCE_COMMUNITY,
            category=Spots.CATEGORY_SKATEPARK,
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.rider)

    def rate(self, **payload):
        return self.client.post(
            "/api/spots/%d/rate/" % self.spot.id,
            payload,
            format="json",
        )

    # ------------------------------------------------------------------
    # The stars
    # ------------------------------------------------------------------

    def test_a_rider_rates_a_spot(self):
        self.authenticate()

        response = self.rate(score=4, comment="Buen bowl")

        self.assertEqual(response.status_code, 201)
        rating = Rating.objects.get(spot=self.spot, user=self.rider)
        self.assertEqual(rating.score, Decimal("4"))
        self.assertEqual(rating.comment, "Buen bowl")

    def test_the_score_is_between_one_and_five(self):
        self.authenticate()

        self.assertEqual(self.rate(score=0).status_code, 400)
        self.assertEqual(self.rate(score=6).status_code, 400)
        self.assertEqual(self.rate(score=4).status_code, 201)

    def test_the_score_is_a_whole_number(self):
        self.authenticate()

        response = self.rate(score=4.5)

        self.assertEqual(response.status_code, 400)

    def test_the_rider_can_not_rate_without_a_session(self):
        response = self.rate(score=4)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Rating.objects.count(), 0)

    def test_the_rider_rates_the_spot_only_once(self):
        self.authenticate()

        self.rate(score=4)
        response = self.rate(score=2)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Rating.objects.count(), 1)
        self.assertEqual(Rating.objects.get().score, Decimal("2"))

    # ------------------------------------------------------------------
    # The list of the ratings
    # ------------------------------------------------------------------

    def test_the_ratings_of_a_spot_are_read_by_everybody(self):
        self.authenticate()
        self.rate(score=5, comment="Perfecto")
        self.authenticate(self.other)
        self.rate(score=3)

        self.client.force_authenticate(user=None)
        response = self.client.get("/api/spots/%d/ratings/" % self.spot.id)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)

        usernames = [row["user_username"] for row in body["results"]]
        self.assertIn("rider", usernames)
        self.assertIn("other", usernames)

    def test_the_list_only_has_the_ratings_of_that_spot(self):
        other_spot = Spots.objects.create(
            name_spot="Otro spot",
            user=self.rider,
            source=Spots.SOURCE_COMMUNITY,
        )

        self.authenticate()
        self.rate(score=4)
        Rating.objects.create(
            user=self.other, spot=other_spot, score=Decimal("1")
        )

        response = self.client.get("/api/spots/%d/ratings/" % self.spot.id)

        self.assertEqual(response.json()["count"], 1)

    # ------------------------------------------------------------------
    # The edit and the delete
    # ------------------------------------------------------------------

    def test_the_rider_deletes_its_own_rating(self):
        self.authenticate()
        self.rate(score=4)

        rating = Rating.objects.get()
        response = self.client.delete("/api/rating/%d/" % rating.id)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(Rating.objects.count(), 0)

    def test_a_rider_can_not_delete_the_rating_of_another_one(self):
        self.authenticate(self.other)
        self.rate(score=4)

        rating = Rating.objects.get()
        self.authenticate(self.rider)

        response = self.client.delete("/api/rating/%d/" % rating.id)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Rating.objects.count(), 1)

    # ------------------------------------------------------------------
    # The average
    # ------------------------------------------------------------------

    def test_the_spot_answers_with_its_average(self):
        self.authenticate()
        self.rate(score=5)
        self.authenticate(self.other)
        self.rate(score=4)

        response = self.client.get("/api/spots/%d/" % self.spot.id)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["rating"], 4.5)
        self.assertEqual(body["rating_count"], 2)

    def test_the_average_is_not_of_the_spot(self):
        other_spot = Spots.objects.create(
            name_spot="Otro spot",
            user=self.rider,
            source=Spots.SOURCE_COMMUNITY,
        )
        Rating.objects.create(user=self.other, spot=other_spot, score=Decimal("1"))

        self.authenticate()
        self.rate(score=5)

        response = self.client.get("/api/spots/%d/" % self.spot.id)

        self.assertEqual(response.json()["rating"], 5.0)
        self.assertEqual(response.json()["rating_count"], 1)
