"""Google OAuth 2.0 helpers for signing in with Google.

Only what the login flow needs lives here: build the authorization
URL, exchange the code for an ID token, verify that token and find or
create the local user. The views stay thin and the rest of the
application does not change.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from typing import Any, Dict, Tuple
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_SCOPES = "openid email profile"
REQUEST_TIMEOUT = 10
# Google rotates the signing keys, but not every minute. The certificates
# are cached so the login flow does not fetch them on every attempt.
CERT_CACHE_SECONDS = 60 * 60

_CERT_CACHE: Dict[str, Any] = {"fetched_at": 0.0, "keys": None}


class GoogleAuthError(Exception):
    """A login failure with a code the view can show to the user."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def generate_state() -> str:
    """Return a random value for the OAuth ``state`` parameter."""
    return secrets.token_urlsafe(32)


def validate_state(state: str | None, expected: str | None) -> bool:
    """Compare the ``state`` that came back with the one we stored."""
    if not state or not expected:
        return False
    return secrets.compare_digest(str(state), str(expected))


def get_redirect_uri() -> str:
    """Return the callback URL registered in Google Cloud Console."""
    configured = settings.GOOGLE_REDIRECT_URI
    if configured:
        return configured

    host = settings.HOST.rstrip("/") if settings.HOST else "http://localhost:8000"
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return f"{host}/auth/google/callback/"


def build_authorization_url(state: str) -> str:
    """Build the Google consent screen URL."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": get_redirect_uri(),
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> Dict[str, Any]:
    """Exchange the authorization code for Google's tokens."""
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": get_redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        raise GoogleAuthError("google_token_failed")

    tokens = response.json()
    if not tokens.get("id_token"):
        raise GoogleAuthError("google_no_id_token")
    return tokens


def _fetch_certs() -> Dict[str, Any]:
    """Return Google's signing certificates, cached for a while."""
    now = time.monotonic()
    if _CERT_CACHE["keys"] and now - _CERT_CACHE["fetched_at"] < CERT_CACHE_SECONDS:
        return _CERT_CACHE["keys"]

    response = requests.get(GOOGLE_CERTS_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    keys = response.json()
    _CERT_CACHE["fetched_at"] = now
    _CERT_CACHE["keys"] = keys
    return keys


def verify_id_token(id_token: str) -> Dict[str, Any]:
    """Verify the ID token and return its claims.

    The signature, audience, issuer, expiration and required claims are
    checked locally with Google's public certificates. The email has to
    be verified by Google as well.
    """
    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as error:
        raise GoogleAuthError("google_id_token_invalid") from error

    kid = header.get("kid")
    if not kid:
        raise GoogleAuthError("google_id_token_invalid")

    try:
        jwks = jwt.PyJWKSet.from_json(json.dumps(_fetch_certs()))
        key = jwks[kid].key
    except requests.RequestException:
        raise
    except Exception as error:
        raise GoogleAuthError("google_id_token_invalid") from error

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=settings.GOOGLE_CLIENT_ID,
            issuer=list(GOOGLE_ISSUERS),
            options={
                "verify_exp": True,
                "require": ["exp", "iat", "sub", "email"],
            },
        )
    except Exception as error:
        raise GoogleAuthError("google_id_token_invalid") from error

    if not claims.get("email"):
        raise GoogleAuthError("google_no_email")
    if not _email_is_verified(claims):
        raise GoogleAuthError("google_email_not_verified")
    return claims


def _email_is_verified(claims: Dict[str, Any]) -> bool:
    value = claims.get("email_verified")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return False


def _base_username(email: str) -> str:
    """Turn the email local part into a valid username."""
    local = email.split("@", 1)[0]
    local = re.sub(r"[^\w.@+-]", "_", local, flags=re.UNICODE).strip("._")
    return (local or "user")[:25]


def find_or_create_user(email: str) -> Tuple[Any, bool]:
    """Return the local user for a Google account, creating it if needed.

    The account is matched by email, so somebody who registered with a
    password and then signs in with Google keeps the same account and
    its permissions. A new account gets the same default as the normal
    registration: no extra groups or permissions.
    """
    User = get_user_model()
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        username = _base_username(email)
        candidate = username
        counter = 1
        while User.objects.filter(username=candidate).exists():
            suffix = f"_{counter}"
            candidate = f"{username[: 25 - len(suffix)]}{suffix}"
            counter += 1

        user = User.objects.create_user(
            username=candidate,
            email=email,
            password=None,
        )
        return user, True

    return user, False


def authenticate_with_google(code: str) -> Any:
    """Verify the Google code and return the local user."""
    tokens = exchange_code(code)
    claims = verify_id_token(tokens["id_token"])
    user, _created = find_or_create_user(claims["email"])

    if not user.is_active:
        raise GoogleAuthError("google_user_inactive")

    return user
