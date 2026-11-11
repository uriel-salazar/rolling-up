"""Thin HTTP client for the official Overpass API.

This module only talks to the Overpass API and returns raw JSON. It
knows nothing about Django models, so it can be reused (and tested)
independently from the database import logic.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from django.conf import settings

from .exceptions import OverpassQueryError, OverpassRequestError

logger = logging.getLogger(__name__)

# Status codes that are worth retrying: the server is busy or overloaded.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class OverpassClient:
    """Retrieve raw elements from the Overpass API.

    Args:
        endpoint: Overpass interpreter URL.
        timeout: Total number of seconds allowed for a single request.
        max_retries: How many additional attempts are made when the
            server answers with a temporary error.
        backoff: Base number of seconds used for the exponential
            backoff between two attempts.
        user_agent: Descriptive User-Agent, required by the Overpass
            usage policy.
        session: Optional ``requests.Session``, mostly useful for tests.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        backoff: Optional[float] = None,
        user_agent: Optional[str] = None,
        session: Optional[requests.Session] = None,
        mirrors: Optional[Iterable[str]] = None,
    ) -> None:
        self.endpoint = endpoint or settings.OVERPASS_API_URL
        self.timeout = timeout if timeout is not None else settings.OVERPASS_TIMEOUT
        self.max_retries = (
            max_retries if max_retries is not None else settings.OVERPASS_MAX_RETRIES
        )
        self.backoff = (
            backoff if backoff is not None else settings.OVERPASS_RETRY_BACKOFF
        )
        self.user_agent = user_agent or settings.OVERPASS_USER_AGENT
        self.session = session or requests.Session()

        # The mirrors are the other public instances of the service. They
        # are used when the main one can not be reached, so a network
        # that blocks one of them still gets the answer.
        if mirrors is None:
            self.mirrors = list(settings.OVERPASS_MIRRORS)
        else:
            self.mirrors = list(mirrors)
        self.mirrors = [url for url in self.mirrors if url != self.endpoint]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_elements(self, query: str) -> List[Dict[str, Any]]:
        """Run an Overpass QL query and return the raw elements.

        Args:
            query: The Overpass QL query to execute.

        Returns:
            The list of elements contained in the response.

        Raises:
            OverpassQueryError: The server rejected the query (HTTP 400).
            OverpassRequestError: The request failed for any other reason.
        """
        payload = self._post(query)
        return self._extract_elements(payload)

    def query_skateparks(self, query: str) -> List[Dict[str, Any]]:
        """Alias of :meth:`fetch_elements` kept for readability."""
        return self.fetch_elements(query)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _post(self, query: str) -> Dict[str, Any]:
        """POST the query to Overpass, retrying temporary failures."""
        headers = {"User-Agent": self.user_agent}

        # The instances are tried one after the other: the main one
        # first, then the mirrors, because the answer of any of them is
        # the same. A mirror is only used when the main instance can
        # not be reached at all, so a network that blocks it still gets
        # the answer.
        endpoints = [self.endpoint] + list(self.mirrors)
        last_error: Optional[Exception] = None

        for index, endpoint in enumerate(endpoints):
            is_last = index == len(endpoints) - 1
            try:
                return self._post_to(endpoint, query, headers, is_last)
            except OverpassQueryError:
                # The query itself is wrong: no endpoint can answer it.
                raise
            except OverpassRequestError as exc:
                last_error = exc

                if getattr(exc, "reachable", True):
                    # The instance answered, it is only busy. Another
                    # instance would answer the same way.
                    raise

                if not is_last:
                    logger.warning(
                        "The Overpass API at %s could not be reached (%s). "
                        "Trying the next instance.",
                        endpoint,
                        exc,
                    )
                    continue
                raise

        raise last_error  # pragma: no cover - the loop always raises

    def _post_to(
        self,
        endpoint: str,
        query: str,
        headers: Dict[str, str],
        is_last: bool = True,
    ) -> Dict[str, Any]:
        """POST the query to one instance, retrying temporary failures.

            When another instance is waiting, a connection that does not
            open is not retried: the next instance is tried at once.
        """
        attempt = 0

        while True:
            attempt += 1
            try:
                response = self.session.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if not is_last or attempt > self.max_retries:
                    logger.error(
                        "Overpass request failed after %s attempt(s): %s",
                        attempt,
                        exc,
                    )
                    error = OverpassRequestError(
                        f"Could not reach the Overpass API at {endpoint}: {exc}"
                    )
                    # The instance can not be reached at all, so another
                    # one may answer.
                    error.reachable = False
                    raise error from exc

                delay = self.backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Overpass connection error (attempt %s/%s): %s. Retrying in %ss.",
                    attempt,
                    self.max_retries + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code == 400:
                # The query itself is wrong: retrying would not help.
                raise OverpassQueryError(
                    "The Overpass API rejected the query (HTTP 400): "
                    f"{self._extract_error_message(response)}"
                )

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt > self.max_retries:
                    logger.error(
                        "Overpass returned HTTP %s after %s attempt(s).",
                        response.status_code,
                        attempt,
                    )
                    raise OverpassRequestError(
                        f"The Overpass API kept answering HTTP {response.status_code}."
                    )

                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "Overpass returned HTTP %s (attempt %s/%s). Retrying in %ss.",
                    response.status_code,
                    attempt,
                    self.max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            if not response.ok:
                logger.error(
                    "Overpass returned an unexpected HTTP %s.", response.status_code
                )
                raise OverpassRequestError(
                    f"The Overpass API answered with HTTP {response.status_code}."
                )

            try:
                return response.json()
            except ValueError as exc:
                raise OverpassRequestError(
                    "The Overpass API returned a response that is not valid JSON."
                ) from exc

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        """Return the number of seconds to wait before the next attempt."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except (TypeError, ValueError):
                logger.debug("Ignoring unparsable Retry-After header: %r", retry_after)
        return self.backoff * (2 ** (attempt - 1))

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        """Pull the human readable part out of an Overpass error page."""
        text = (response.text or "").strip()

        if "</strong>" in text:
            # Overpass reports its errors as
            # '<strong style="...">Error</strong>: line 2: parse error: ...'.
            message = text.split("</strong>", 1)[1]
            message = message.split("</p>", 1)[0]
            message = (
                message.replace("&quot;", '"')
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .strip()
            )
            message = message.lstrip(":").strip()
            if message:
                return message[:300]

        return text[:300]

    @staticmethod
    def _extract_elements(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return the elements of an Overpass payload, validating its shape."""
        if not isinstance(payload, dict):
            raise OverpassRequestError(
                "The Overpass API returned a payload that is not a JSON object."
            )

        if "elements" not in payload:
            remark = payload.get("remark") or "no elements"
            raise OverpassRequestError(
                f"The Overpass API returned no elements ({remark})."
            )

        elements = payload["elements"]
        if not isinstance(elements, list):
            raise OverpassRequestError(
                "The Overpass API returned an unexpected 'elements' value."
            )

        return [element for element in elements if isinstance(element, dict)]


def build_overpass_query(
    area_expression: str,
    tags: Iterable[Dict[str, str]],
    prelude: str = "",
) -> str:
    """Build an Overpass QL query.

    Args:
        area_expression: Either a bounding box such as
            ``"20.60,-103.50,20.75,-103.30"`` or an area filter such as
            ``"area.searchArea"``.
        tags: Iterable of ``{"key": ..., "value": ...}`` mappings, one
            per tag filter.
        prelude: Optional statement placed before the filters, used to
            resolve an area by name (``{{geocodeArea:...}}->.searchArea;``).

    Returns:
        The Overpass QL query as a string.
    """
    filters = "\n".join(
        f'  nwr["{entry["key"]}"="{entry["value"]}"]({area_expression});'
        for entry in tags
    )
    return (
        "[out:json][timeout:60];\n"
        f"{prelude}\n"
        f"{filters}\n"
        "out center tags;"
    )
