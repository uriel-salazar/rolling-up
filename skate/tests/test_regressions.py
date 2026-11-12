"""Tests for the bugs found during the audit.

They cover the answers that used to be an error of the server, the
pages that showed nothing because the template asked for variables
that did not exist and the contract between the interface and the API.

The tests are grouped by the area they protect, so a failure points at
the part of the application that broke.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from skate.models import Rating, Spots

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

User = get_user_model()


def a_png():
    """Return a small valid PNG, ready to be uploaded."""
    # A 1x1 transparent PNG.
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
        b"\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nID"
        b"ATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00"
        b"\x00IEND\xaeB`\x82"
    )


class RegistrationTests(TestCase):
    """The account of a visitor."""

    def setUp(self):
        self.client = APIClient()

    def test_a_duplicate_email_is_refused(self):
        """A duplicate address is a 400 and not an error of the server."""
        first = self.client.post(
            "/api/users/",
            {
                "username": "rider",
                "email": "rider@example.com",
                "password": "secret-password",
            },
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)

        second = self.client.post(
            "/api/users/",
            {
                "username": "other",
                "email": "rider@example.com",
                "password": "secret-password",
            },
            format="json",
        )

        self.assertEqual(second.status_code, 400)
        self.assertIn("email", second.data)
        self.assertEqual(User.objects.filter(email="rider@example.com").count(), 1)

    def test_a_duplicate_username_is_refused(self):
        User.objects.create_user(
            username="rider", email="rider@example.com", password="secret-password"
        )

        response = self.client.post(
            "/api/users/",
            {
                "username": "rider",
                "email": "other@example.com",
                "password": "secret-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)


class TokenTests(TestCase):
    """The login of a visitor."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="rider", email="rider@example.com", password="secret-password"
        )
        self.client = APIClient()

    def test_the_login_with_the_username(self):
        response = self.client.post(
            "/api/token/",
            {"username": "rider", "password": "secret-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_the_login_with_the_email(self):
        """The form asks for "usuario o correo", so both work."""
        response = self.client.post(
            "/api/token/",
            {"username": "rider@example.com", "password": "secret-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_the_login_with_the_email_is_not_case_sensitive(self):
        response = self.client.post(
            "/api/token/",
            {"username": "RIDER@example.com", "password": "secret-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_an_unknown_email_is_refused(self):
        response = self.client.post(
            "/api/token/",
            {"username": "nobody@example.com", "password": "secret-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)


class RatingApiRegressionTests(TestCase):
    """The rating of a spot."""

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
            user=self.rider,
            source=Spots.SOURCE_COMMUNITY,
            category=Spots.CATEGORY_SKATEPARK,
        )
        self.other_spot = Spots.objects.create(
            name_spot="Otro spot",
            user=self.rider,
            source=Spots.SOURCE_COMMUNITY,
        )

    def test_the_collection_without_a_spot_is_refused(self):
        """The collection of the router needs the spot of the rating."""
        self.client.force_authenticate(self.rider)

        response = self.client.post("/api/rating/", {"score": 4}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Rating.objects.count(), 0)

    def test_the_collection_with_the_spot_works(self):
        self.client.force_authenticate(self.rider)

        response = self.client.post(
            "/api/rating/", {"score": 4, "spot": self.spot.id}, format="json"
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Rating.objects.get().spot, self.spot)

    def test_a_rating_can_not_be_moved_to_another_spot(self):
        """The spot of a rating is fixed."""
        self.client.force_authenticate(self.rider)
        self.client.post(
            "/api/rating/", {"score": 4, "spot": self.spot.id}, format="json"
        )
        rating = Rating.objects.get()

        response = self.client.patch(
            "/api/rating/%d/" % rating.id, {"spot": self.other_spot.id}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        rating.refresh_from_db()
        self.assertEqual(rating.spot, self.spot)

    def test_a_rating_still_can_be_edited_by_its_rider(self):
        self.client.force_authenticate(self.rider)
        self.client.post(
            "/api/rating/", {"score": 4, "spot": self.spot.id}, format="json"
        )
        rating = Rating.objects.get()

        response = self.client.patch(
            "/api/rating/%d/" % rating.id, {"score": 5}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        rating.refresh_from_db()
        self.assertEqual(rating.score, Decimal("5"))


class SpotPhotoApiTests(TestCase):
    """The additional photographs of a spot."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="rider", email="rider@example.com", password="secret-password"
        )
        self.client = APIClient()
        self.spot = Spots.objects.create(
            name_spot="Skatepark Oasis",
            user=self.user,
            source=Spots.SOURCE_COMMUNITY,
        )

    def upload(self, **fields):
        data = {"image": SimpleUploadedFile("photo.png", a_png(), "image/png")}
        data.update(fields)
        return self.client.post(
            "/api/spots/%d/photos/" % self.spot.id, data, format="multipart"
        )

    def test_a_photo_is_uploaded_without_sending_the_spot(self):
        """The interface sends the picture and the caption, not the spot."""
        self.client.force_authenticate(self.user)

        response = self.upload(caption="Un bowl")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["spot"], self.spot.id)
        self.assertEqual(response.data["caption"], "Un bowl")

    def test_a_photo_without_a_file_is_refused(self):
        """A photograph without a file is a 400 and not an error."""
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/spots/%d/photos/" % self.spot.id, {}, format="multipart"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)

    def test_a_photo_of_a_spot_of_somebody_else_is_not_possible(self):
        """The spot of the url is the spot of the photograph."""
        other = User.objects.create_user(
            username="other", email="other@example.com", password="secret-password"
        )
        self.client.force_authenticate(other)

        response = self.upload(spot=self.spot.id)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["spot"], self.spot.id)

    def test_the_photo_of_the_answer_has_the_url_of_the_file(self):
        """The interface reads the field "image" of the answer."""
        self.client.force_authenticate(self.user)

        response = self.upload()

        self.assertEqual(response.status_code, 201)
        self.assertIn("image", response.data)
        self.assertTrue(response.data["image"])


class SpotDetailPageTests(TestCase):
    """The page of a spot."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="rider", email="rider@example.com", password="secret-password"
        )
        self.client = APIClient()
        self.spot = Spots.objects.create(
            name_spot="Skatepark Oasis",
            body="Un skatepark grande",
            user=self.user,
            source=Spots.SOURCE_COMMUNITY,
            category=Spots.CATEGORY_SKATEPARK,
        )

    def test_the_page_is_public(self):
        response = self.client.get("/spots/%d/" % self.spot.id)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "spot_detail.html")

    def test_the_description_of_the_spot_is_shown(self):
        response = self.client.get("/spots/%d/" % self.spot.id)

        self.assertContains(response, "Un skatepark grande")

    def test_the_form_of_the_photo_is_always_in_the_page(self):
        """The session lives in the browser, so the form is always there."""
        response = self.client.get("/spots/%d/" % self.spot.id)

        self.assertContains(response, 'id="photo-upload-form"')
        self.assertContains(response, 'id="photo-login-note"')

    def test_the_photos_of_the_spot_are_shown(self):
        from skate.models import SpotPhoto

        SpotPhoto.objects.create(
            spot=self.spot,
            image=SimpleUploadedFile("photo.png", a_png(), "image/png"),
            caption="El bowl",
            uploaded_by=self.user,
        )

        response = self.client.get("/spots/%d/" % self.spot.id)

        self.assertContains(response, "El bowl")
        self.assertContains(response, "photo-delete")

    def test_the_button_of_the_delete_names_the_uploader(self):
        """The interface compares the owner of the photo with the session."""
        from skate.models import SpotPhoto

        SpotPhoto.objects.create(
            spot=self.spot,
            image=SimpleUploadedFile("photo.png", a_png(), "image/png"),
            caption="El bowl",
            uploaded_by=self.user,
        )

        response = self.client.get("/spots/%d/" % self.spot.id)

        self.assertContains(response, 'data-uploaded-by="%d"' % self.user.id)

    def test_the_page_can_be_shown_inside_a_frame_of_the_map(self):
        """The map of the home page is shown inside a frame.

        The link "Ver detalle" of the map opens the page of the spot
        inside that frame, so the browser has to allow it. With the
        default of Django the page is blocked and the visitor sees an
        error instead of the spot.
        """
        response = self.client.get("/spots/%d/" % self.spot.id)

        self.assertEqual(
            response.headers.get("X-Frame-Options"),
            "SAMEORIGIN",
            "The page of the spot has to allow the frames of the same "
            "site, the map of the home page is shown inside one.",
        )


class SessionNavigationTests(TestCase):
    """The bar of the page.

    The application signs the visitors in with a token in the browser,
    so the server does not know who is reading the page. Both parts of
    the bar are in the page and the script shows the right one.
    """

    def setUp(self):
        self.client = APIClient()

    def test_the_bar_has_both_parts(self):
        response = self.client.get("/feed/")

        self.assertContains(response, 'data-session="in"')
        self.assertContains(response, 'data-session="out"')

    def test_the_script_of_the_session_is_loaded(self):
        for path in ("/feed/", "/map/", "/profile/", "/register/", "/spots/new/"):
            response = self.client.get(path)
            self.assertContains(response, "session.js", msg_prefix=path)

    def test_the_pages_that_need_the_script_load_it(self):
        response = self.client.get("/feed/")

        self.assertContains(response, "session.js")


class FeedMoreButtonTests(TestCase):
    """The button that opens the whole feed.

    The landing page shows a few spots inside a frame, and the button
    "Ver más" opens the whole feed. The button is in the page and the
    script shows it when there are more spots than the ones on screen.
    """

    def setUp(self):
        self.client = APIClient()

    def test_the_button_is_in_the_page(self):
        response = self.client.get("/feed/")

        self.assertContains(response, 'id="feed-more"')
        self.assertContains(response, "Ver más")

    def test_the_button_opens_the_whole_feed(self):
        response = self.client.get("/feed/")

        self.assertContains(response, 'href="/feed/"')
        # The feed is embedded in a frame of the landing page, so the
        # button has to open the whole page and not the frame.
        self.assertContains(response, 'target="_top"')

    def test_the_button_starts_hidden(self):
        """The script shows it only when it has to be shown."""
        response = self.client.get("/feed/")

        self.assertContains(response, 'class="feed-more" id="feed-more" hidden')


class FeedNavbarTests(TestCase):
    """The button that adds a spot, in the bar of the feed.

    The page of the form is public and it asks the visitor to log in
    when they send it, so the button is always there and its hover can
    be seen.
    """

    def setUp(self):
        self.client = APIClient()

    def test_the_button_to_add_a_spot_is_always_there(self):
        response = self.client.get("/feed/")

        self.assertContains(response, 'href="/spots/new/"')
        self.assertContains(response, "Añadir Spot")

    def test_the_bar_of_the_page_is_the_shared_one(self):
        """Every page of the application uses the same bar."""
        response = self.client.get("/feed/")

        self.assertContains(response, 'class="navbar section-content"')

    def test_the_stylesheet_has_the_hover_of_the_button(self):
        """The button has to react when the pointer is on it."""
        stylesheets = [
            (PROJECT_ROOT / "skate" / "static" / name).read_text(encoding="utf-8")
            for name in ("styles.css", "feed.css")
        ]

        self.assertTrue(
            any(".nav-link:hover" in sheet for sheet in stylesheets),
            "The stylesheet needs a rule for the hover of the button that "
            "adds a spot.",
        )

    def test_the_button_uses_the_font_of_the_application(self):
        """The button of the bar has to use the font of the page."""
        stylesheets = [
            (PROJECT_ROOT / "skate" / "static" / name).read_text(encoding="utf-8")
            for name in ("styles.css", "feed.css")
        ]

        self.assertTrue(
            any(".nav-link" in sheet and "Manrope" in sheet for sheet in stylesheets),
            "The button that adds a spot has to use the font of the "
            "application.",
        )
