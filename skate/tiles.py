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
import math
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

# The connection to the provider of the tiles is kept open. Without it
# every tile opens a new connection and repeats the handshake, and
# the map waits for it.
_session = requests.Session()
_session.headers.update({"User-Agent": settings.OVERPASS_USER_AGENT})


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
        response = _session.get(url, headers=headers, timeout=30)
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


def tile_range(latitude: float, longitude: float, zoom: int):
    """Return the tiles that show a place at a level of zoom.

    The map of the page of a spot is small, but the browser asks for
    the tiles around the place, and it asks for them at the same time.
    The server answers them one after the other, so the map appears
    slowly. The tiles are brought here before the browser asks for
    them, and then the answer comes from the cache.

    Args:
        latitude: The latitude of the place.
        longitude: The longitude of the place.
        zoom: The level of zoom of the map.

    Returns:
        A list of ``(zoom, x, y)``.
    """
    if not all(isinstance(value, (int, float)) for value in (latitude, longitude)):
        return []

    # The number of tiles that the browser asks for around the place.
    radius = 2

    # The position of the place in the grid of tiles.
    scale = 2 ** zoom
    x = int((longitude + 180.0) / 360.0 * scale)
    sin_lat = math.sin(math.radians(max(-85.0, min(85.0, latitude))))
    y = int(
        (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    )

    tiles = []
    for delta_x in range(-radius, radius + 1):
        for delta_y in range(-radius, radius + 1):
            tile_x = x + delta_x
            tile_y = y + delta_y
            if 0 <= tile_x < scale and 0 <= tile_y < scale:
                tiles.append((zoom, tile_x, tile_y))

    return tiles


def warm_tiles(latitude, longitude, zoom):
    """Bring the tiles of a place into the cache of the server.

    It is called when the page of a spot is served, before the browser
    asks for the tiles. The tiles that are already in the cache are
    left alone.
    """
    if not settings.OSM_TILE_URL:
        return

    for tile_zoom, tile_x, tile_y in tile_range(latitude, longitude, zoom):
        cache_key = 'tile:%d:%d:%d:%s' % (tile_zoom, tile_x, tile_y, '1x')
        if cache.get(cache_key) is not None:
            continue

        url = build_tile_url(tile_zoom, tile_x, tile_y, '')
        if url is None:
            continue

        try:
            response = _session.get(url, timeout=10)
        except requests.RequestException:
            continue

        if not response.ok:
            continue

        content_type = response.headers.get('Content-Type', 'image/png')
        max_age = response.headers.get('Cache-Control')
        if not max_age:
            max_age = f"public, max-age={DEFAULT_CACHE_SECONDS}"

        cache.set(
            cache_key,
            (response.content, content_type, max_age),
            DEFAULT_CACHE_SECONDS,
        )
