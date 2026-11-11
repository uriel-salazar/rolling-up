"""Tests for the Google OAuth login flow."""

from __future__ import annotations

import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from jwt.algorithms import RSAAlgorithm

from skate import google_auth

User = get_user_model()

GOOGLE_SETTINGS = {
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback/",
}


class LoginConfigurationTests(TestCase):
    def setUp(self):
        self.client = Client()

    @override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
    def test_login_requires_credentials(self):
        response = self.client.get("/auth/google/login/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=google_not_configured", response["Location"])

    @override_settings(**GOOGLE_SETTINGS)
    def test_login_stores_state_and_redirects_to_google(self):
        response = self.client.get("/auth/google/login/")
        self.assertEqual(response.status_code, 302)

        location = response["Location"]
        self.assertTrue(location.startswith(google_auth.GOOGLE_AUTH_URL))

        params = parse_qs(urlparse(location).query)
        state = params["state"][0]
        self.assertTrue(state)
        self.assertEqual(params["client_id"], ["test-client-id"])
        self.assertEqual(
            params["redirect_uri"],
            ["http://localhost:8000/auth/google/callback/"],
        )
        self.assertEqual(self.client.session["google_oauth_state"], state)


class CallbackTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _login_state(self):
        response = self.client.get("/auth/google/login/")
        return parse_qs(urlparse(response["Location"]).query)["state"][0]

    @override_settings(**GOOGLE_SETTINGS)
    def test_callback_rejects_missing_or_wrong_state(self):
        response = self.client.get("/auth/google/callback/?code=abc")
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=google_state_invalid", response["Location"])

        response = self.client.get("/auth/google/callback/?code=abc&state=wrong")
        self.assertIn("error=google_state_invalid", response["Location"])

    @override_settings(**GOOGLE_SETTINGS)
    def test_callback_requires_code(self):
        session = self.client.session
        session["google_oauth_state"] = "expected-state"
        session.save()

        response = self.client.get("/auth/google/callback/?state=expected-state")
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=google_no_code", response["Location"])

    @override_settings(**GOOGLE_SETTINGS)
    def test_callback_reports_google_error(self):
        response = self.client.get("/auth/google/callback/?error=access_denied")
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=google_access_denied", response["Location"])

    @override_settings(**GOOGLE_SETTINGS)
    @patch("skate.google_auth.authenticate_with_google")
    def test_callback_issues_jwt_for_the_local_user(self, mock_authenticate):
        user = User.objects.create_user(
            username="googler", email="googler@example.com", password=None
        )
        mock_authenticate.return_value = user
        state = self._login_state()

        response = self.client.get(
            f"/auth/google/callback/?code=the-code&state={state}"
        )

        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        # The tokens travel in the fragment of the url: the fragment is
        # never sent to the server, so the tokens do not end up in the
        # logs of the server nor in the history of the browser.
        self.assertIn("/profile/#access=", location)
        self.assertIn("&refresh=", location)
        self.assertNotIn("?access=", location)
        mock_authenticate.assert_called_once_with("the-code")

    @override_settings(**GOOGLE_SETTINGS)
    @patch("skate.google_auth.authenticate_with_google")
    def test_callback_reports_verification_error(self, mock_authenticate):
        mock_authenticate.side_effect = google_auth.GoogleAuthError(
            "google_email_not_verified"
        )
        state = self._login_state()

        response = self.client.get(
            f"/auth/google/callback/?code=the-code&state={state}"
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=google_email_not_verified", response["Location"])

    @override_settings(**GOOGLE_SETTINGS)
    @patch("skate.google_auth.authenticate_with_google")
    def test_callback_reports_network_error(self, mock_authenticate):
        mock_authenticate.side_effect = requests.ConnectionError("down")
        state = self._login_state()

        response = self.client.get(
            f"/auth/google/callback/?code=the-code&state={state}"
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=google_network_error", response["Location"])


class FindOrCreateUserTests(TestCase):
    def test_creates_user_with_unusable_password(self):
        user, created = google_auth.find_or_create_user("new.user@example.com")

        self.assertTrue(created)
        self.assertEqual(user.email, "new.user@example.com")
        self.assertEqual(user.username, "new.user")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_reuses_existing_user_by_email(self):
        existing = User.objects.create_user(
            username="existing", email="same@example.com", password="secret123"
        )

        user, created = google_auth.find_or_create_user("same@example.com")

        self.assertFalse(created)
        self.assertEqual(user.pk, existing.pk)
        self.assertTrue(user.has_usable_password())

    def test_truncates_a_long_username(self):
        user, _created = google_auth.find_or_create_user("a" * 40 + "@example.com")
        self.assertEqual(len(user.username), 25)

    def test_avoids_username_collisions(self):
        User.objects.create_user(
            username="taken", email="taken@example.com", password=None
        )

        user, _created = google_auth.find_or_create_user("taken@example.org")

        self.assertEqual(user.username, "taken_1")

    def test_sanitizes_invalid_characters(self):
        user, _created = google_auth.find_or_create_user("john doe@example.com")
        self.assertEqual(user.username, "john_doe")


class VerifyIdTokenTests(SimpleTestCase):
    def _keys(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
        jwk.update({"kid": "test-kid", "alg": "RS256", "use": "sig"})
        return private_key, {"keys": [jwk]}

    def _token(self, private_key, claims, kid="test-kid"):
        headers = {"kid": kid} if kid else {}
        return jwt.encode(claims, private_key, algorithm="RS256", headers=headers)

    @override_settings(GOOGLE_CLIENT_ID="test-client-id")
    def test_verifies_a_valid_token(self):
        private_key, jwks = self._keys()
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "test-client-id",
            "sub": "1234567890",
            "email": "user@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._token(private_key, claims)

        with patch("skate.google_auth._fetch_certs", return_value=jwks):
            verified = google_auth.verify_id_token(token)

        self.assertEqual(verified["email"], "user@example.com")
        self.assertEqual(verified["sub"], "1234567890")

    @override_settings(GOOGLE_CLIENT_ID="test-client-id")
    def test_rejects_a_token_for_another_audience(self):
        private_key, jwks = self._keys()
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "another-client",
            "sub": "1234567890",
            "email": "user@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._token(private_key, claims)

        with patch("skate.google_auth._fetch_certs", return_value=jwks):
            with self.assertRaises(google_auth.GoogleAuthError) as context:
                google_auth.verify_id_token(token)

        self.assertEqual(context.exception.code, "google_id_token_invalid")

    @override_settings(GOOGLE_CLIENT_ID="test-client-id")
    def test_rejects_an_expired_token(self):
        private_key, jwks = self._keys()
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "test-client-id",
            "sub": "1234567890",
            "email": "user@example.com",
            "email_verified": True,
            "iat": now - 7200,
            "exp": now - 3600,
        }
        token = self._token(private_key, claims)

        with patch("skate.google_auth._fetch_certs", return_value=jwks):
            with self.assertRaises(google_auth.GoogleAuthError) as context:
                google_auth.verify_id_token(token)

        self.assertEqual(context.exception.code, "google_id_token_invalid")

    @override_settings(GOOGLE_CLIENT_ID="test-client-id")
    def test_rejects_an_unverified_email(self):
        private_key, jwks = self._keys()
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "test-client-id",
            "sub": "1234567890",
            "email": "user@example.com",
            "email_verified": False,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._token(private_key, claims)

        with patch("skate.google_auth._fetch_certs", return_value=jwks):
            with self.assertRaises(google_auth.GoogleAuthError) as context:
                google_auth.verify_id_token(token)

        self.assertEqual(context.exception.code, "google_email_not_verified")

    @override_settings(GOOGLE_CLIENT_ID="test-client-id")
    def test_rejects_a_token_without_kid(self):
        private_key, jwks = self._keys()
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "test-client-id",
            "sub": "1234567890",
            "email": "user@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._token(private_key, claims, kid=None)

        with patch("skate.google_auth._fetch_certs", return_value=jwks):
            with self.assertRaises(google_auth.GoogleAuthError) as context:
                google_auth.verify_id_token(token)

        self.assertEqual(context.exception.code, "google_id_token_invalid")


class StateTests(SimpleTestCase):
    def test_validate_state(self):
        self.assertTrue(google_auth.validate_state("abc", "abc"))
        self.assertFalse(google_auth.validate_state("abc", "def"))
        self.assertFalse(google_auth.validate_state(None, "abc"))
        self.assertFalse(google_auth.validate_state("abc", None))
        self.assertFalse(google_auth.validate_state("", ""))
