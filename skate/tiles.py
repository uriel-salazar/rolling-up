"""Proxy for the map tiles.

The tiles are served by the application instead of by the browser
directly for two reasons:

* the key of the tile provider is a credential, it must not be part of
  the html that reaches the browser,
* the request can carry a ``User-Agent`` that identifies the
  application and the caching headers of the provider can be passed on,
  which the usage policies of the tile services ask for.

Only the tiles that the browser is showing are fetched, there is no
prefetching and no offline mode.
"""

from __future__ import annotations

import logging
import re

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

# A tile is /{z}/{x}/{y}.png and the retina version adds @2x before the
# extension.
TILE_PATH = re.compile(r"^(?P<z>\d{1,2})/(?P<x>\d{1,9})/(?P<y>\d{1,9})(@2x)?\.png$")

# The tile servers send their own caching headers, they are passed on
# so the browser does not ask for a tile it already has.
DEFAULT_CACHE_SECONDS = 60 * 60 * 24 * 7


@csrf_exempt
@require_GET
def tile(request, path):
    """Serve one map tile.

    Args:
        path: The path of the tile, ``{z}/{x}/{y}.png`` or
            ``{z}/{x}/{y}@2x.png``.

    Returns:
        The tile as a PNG, or an error when the tile can not be
        fetched.
    """
    match = TILE_PATH.match(path)
    if not match:
        return HttpResponse("Invalid tile path.", status=400)

    zoom = int(match.group('z'))
    x = int(match.group('x'))
    y = int(match.group('y'))
    retina = match.group(4) or ''

    url = build_tile_url(zoom, x, y, retina)
    if url is None:
        return HttpResponse(
            "The tile provider is not configured.", status=404
        )

    # The tile is kept in the cache of the server, so the same tile is
    # not asked to the provider again. Without this, every visitor of
    # the map waits for the provider while the server has the answer
    # already.
    cache_key = 'tile:%d:%d:%d:%s' % (zoom, x, y, retina or '1x')
    cached = cache.get(cache_key)
    if cached is not None:
        content, content_type, max_age = cached
        return tile_response(content, content_type, max_age, 'cache')

    headers = {'User-Agent': settings.OVERPASS_USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        logger.warning("The tile %s could not be fetched: %s", path, exc)
        return HttpResponse("The tile could not be fetched.", status=502)

    if not response.ok:
        logger.warning(
            "The tile provider answered HTTP %s for %s.",
            response.status_code,
            path,
        )
        return HttpResponse(
            "The tile could not be fetched.", status=response.status_code
        )

    content_type = response.headers.get(
        'Content-Type', 'image/png'
    )

    # The tile servers send their own caching headers, they are passed
    # on so the browser does not ask again for a tile it already has.
    max_age = response.headers.get('Cache-Control')
    if not max_age:
        max_age = f"public, max-age={DEFAULT_CACHE_SECONDS}"

    cache.set(
        cache_key,
        (response.content, content_type, max_age),
        DEFAULT_CACHE_SECONDS,
    )

    return tile_response(response.content, content_type, max_age, 'proxy')


def tile_response(content, content_type, max_age, source):
    """Build the answer of a tile.

    The caching headers of the provider are passed on, so the browser
    does not ask again for a tile it already has.
    """
    http_response = HttpResponse(content, content_type=content_type)
    http_response['Cache-Control'] = max_age
    http_response['X-Tile-Source'] = source
    return http_response


def build_tile_url(zoom: int, x: int, y: int, retina: str = ''):
    """Build the url of a tile of the configured provider.

    Returns:
        The url, or ``None`` when no provider is configured.
    """
    template = settings.OSM_TILE_URL
    if not template:
        return None

    url = template
    url = url.replace('{z}', str(zoom))
    url = url.replace('{x}', str(x))
    url = url.replace('{y}', str(y))
    url = url.replace('{r}', retina)
    url = url.replace('{s}', pick_subdomain(zoom, x, y))

    # The key of the provider stays on the server.
    if settings.OSM_TILE_API_KEY:
        separator = '&' if '?' in url else '?'
        url = f"{url}{separator}key={settings.OSM_TILE_API_KEY}"

    return url


def pick_subdomain(zoom: int, x: int, y: int) -> str:
    """Return the subdomain that serves a tile.

    The providers that use subdomains spread the load over them. The
    choice only depends on the position of the tile, so the browser
    always asks the same host for the same tile and its cache keeps
    working.
    """
    subdomains = settings.OSM_TILE_SUBDOMAINS
    if not subdomains:
        return 'a'
    return subdomains[(zoom * 31 + x * 17 + y) % len(subdomains)]
