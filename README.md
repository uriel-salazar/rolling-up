# Rolling Up &mdash; Skate Spots API

Django REST Framework backend for the *Rolling Up* skateboarding platform.
Users can register, publish their own skate spots and rate the spots of
other skaters. Existing skateparks can additionally be imported from
OpenStreetMap.

---

## Importing skateparks from OpenStreetMap

### How the integration works

The importer talks to the **official Overpass API**
(`https://overpass-api.de/api/interpreter`) and pulls candidates tagged
as skateparks:

| Tag                 | Meaning                                                  |
| ------------------- | -------------------------------------------------------- |
| `leisure=skatepark` | An actual skatepark, always imported.                    |
| `sport=skateboard`  | Accepted only when the `leisure` value or the name / description clearly describes a skatepark. A generic tag is not enough. |

Nodes, ways and relations are all supported:

* **nodes** carry their coordinates directly (`lat` / `lon`),
* **ways** and **relations** are queried with `out center`, so their
  centroid is read from the `center` key.

The query is a single Overpass request per import, so the public API is
not hammered:

```overpassql
[out:json][timeout:60];
{{geocodeArea:Guadalajara, Jalisco, Mexico}}->.searchArea;
(
  nwr["leisure"="skatepark"](area.searchArea);
  nwr["sport"="skateboard"](area.searchArea);
);
out center tags;
```

**Area resolution.** The `geocodeArea` specialiser above is the fastest
option because it needs no extra request, but it is not accepted by
every Overpass instance (the official one currently answers with an
HTTP 400 parse error). When that happens the importer automatically
falls back to geocoding the place name with **Nominatim** and re-runs
the query against the resulting bounding box. Both paths are logged.

**Reliability.** The HTTP client handles timeouts (`OVERPASS_TIMEOUT`,
120 s by default), retries temporary server errors with an exponential
backoff (`OVERPASS_MAX_RETRIES`, 3 attempts) and honours the
`Retry-After` header on HTTP 429. A rejected query (HTTP 400) is never
retried, because retrying would not help.

### Running the import

Import the skateparks of Guadalajara (the default location):

```bash
python manage.py import_osm_skateparks
```

Import a different city or region:

```bash
python manage.py import_osm_skateparks --location "Monterrey, Nuevo Leon, Mexico"
python manage.py import_osm_skateparks --location "Mexico City, Mexico"
```

Preview without writing anything to the database:

```bash
python manage.py import_osm_skateparks --dry-run
```

Import an explicit area, given as `south,west,north,east`:

```bash
python manage.py import_osm_skateparks --bbox "20.60,-103.50,20.75,-103.30"
```

The command prints how many skateparks were created, updated, left
unchanged and skipped, together with the reason for every skipped
object.

### How duplicates are handled

Every imported record keeps the identifier of the original OSM object in
the `osm_type` and `osm_id` fields. A **partial unique constraint**
(`unique_osm_object`) covers that pair, so the same OSM object can never
be stored twice:

```python
models.UniqueConstraint(
    fields=["osm_type", "osm_id"],
    name="unique_osm_object",
    condition=Q(osm_id__isnull=False),
)
```

The condition keeps community submitted spots (which have `osm_id =
NULL`) out of the constraint entirely.

Running the command again is safe and idempotent:

* an OSM object that is already stored is **updated** when its data
  changed, and reported as **unchanged** when nothing changed,
* **community submitted spots are never touched**,
* **user generated data is preserved**: the photo is never removed and
  a description that was edited by a user is not overwritten by the OSM
  description (the original OSM description is tracked inside
  `osm_metadata` so the difference can be detected),
* **ratings are never modified**.

### Where the data ends up

Imported skateparks are ordinary `Spots` records, so they show up in the
existing public listing endpoint, `GET /api/spots/`, next to the spots
published by the community.

| Field           | Purpose                                                        |
| --------------- | -------------------------------------------------------------- |
| `name_spot`     | The `name` tag of the OSM object.                              |
| `body`          | The `description` (or `note`) tag.                             |
| `latitude`      | Latitude, `DecimalField` with six decimal places.              |
| `longitude`     | Longitude, `DecimalField` with six decimal places.             |
| `source`        | `osm` or `community`.                                          |
| `osm_id`        | The numeric id of the OSM object.                              |
| `osm_type`      | `node`, `way` or `relation`.                                   |
| `osm_metadata`  | JSON with the raw tags plus `access`, `surface`, `lit`, `operator`, `website`, the licence and the attribution. |

The `source`, `osm_id`, `osm_type` and `osm_metadata` fields are
**read only** in the API, so a user cannot pretend a spot was imported
from OpenStreetMap.

Because `Spots.user` is a mandatory relation, imported records are owned
by a dedicated service account (`osm_importer`, configurable with
`OSM_SERVICE_USER`). The account has an unusable password, so it cannot
be logged into and the imported records cannot be edited through the
API.

### Configuration

All settings are read from the environment, no credentials are needed
because the Overpass API is a public service. A descriptive `User-Agent`
is however required by its usage policy.

| Variable                 | Default                                                    | Purpose                              |
| ------------------------ | ---------------------------------------------------------- | ------------------------------------ |
| `OVERPASS_API_URL`       | `https://overpass-api.de/api/interpreter`                  | Overpass endpoint.                   |
| `OVERPASS_TIMEOUT`       | `120`                                                      | Timeout of a single request, seconds. |
| `OVERPASS_MAX_RETRIES`   | `3`                                                        | Retries after the first attempt.     |
| `OVERPASS_RETRY_BACKOFF` | `3`                                                        | Base delay of the exponential backoff, seconds. |
| `OVERPASS_USER_AGENT`    | `RollingUp-SkateSpots/1.0 (https://rolling-up.onrender.com)` | User-Agent sent to Overpass and Nominatim. |
| `NOMINATIM_API_URL`      | `https://nominatim.openstreetmap.org/search`              | Geocoding service.                   |
| `NOMINATIM_TIMEOUT`      | `30`                                                       | Timeout of the geocoding request, seconds. |
| `OSM_SERVICE_USER`       | `osm_importer`                                             | Username of the service account that owns the imported spots. |

---

## Google Places API (New)

Skateparks can also be discovered with the **Google Places API (New)**.
The integration uses Nearby Search restricted to
`includedTypes: ["skateboard_park"]`, so plazas, generic parks and
courts are not imported. It retrieves the place id, name, coordinates,
address, rating and photographs through explicit field masks.

```bash
python manage.py import_google_skateparks --location "Guadalajara, Jalisco, Mexico"
python manage.py import_google_skateparks --lat 20.67 --lng -103.34 --radius 5000
python manage.py import_google_skateparks --dry-run
```

The importer merges a Google place with an existing OpenStreetMap or
community spot when the name and the position match, so the same
skatepark is never shown twice. Both provider identifiers are kept.

Google content is cached for at most 30 days
(`GOOGLE_PLACES_DATA_TTL_SECONDS`) and is hidden from the API once it
expires. Run `python manage.py purge_google_places_cache` periodically
to delete the expired records as well. Photographs are **not** stored
in the media storage of the application: the browser reads them through
`/api/places/photo/...`, which fetches them on demand and keeps the API
key on the server.

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `GOOGLE_PLACES_API_KEY` | *(empty)* | Required for Google discovery and photos. |
| `GOOGLE_PLACES_SEARCH_RADIUS` | `5000` | Default radius in metres. |
| `GOOGLE_PLACES_MAX_RESULTS` | `20` | Results per page (maximum 20). |
| `GOOGLE_PLACES_MAX_PAGES` | `3` | Pages followed per import. |
| `GOOGLE_PLACES_DATA_TTL_SECONDS` | 30 days | Maximum age of cached provider fields. |
| `GOOGLE_PLACES_PHOTO_CACHE_SECONDS` | 1 day | Browser cache for proxied photos. |
| `GOOGLE_PLACES_DEDUPE_RADIUS_METERS` | `120` | Radius used to merge the same skatepark. |

### Photographs in the existing interface

The API keeps the existing `image_url` field. The resolver fills it, in
order, from a user upload, the first Google Places photograph, or an
image explicitly tagged on OpenStreetMap with a licence or credit. A
spot without a usable picture keeps the existing placeholder. The feed
and the map preview use the same field, so no layout, typography,
colour or control was changed.

---

## Worldwide skatepark discovery

The map and the feed can show skateparks anywhere in the world without
saving them. Two read-only endpoints query Overpass for the current
viewport or for a radius around a point:

```
GET /api/spots/nearby/?lat=41.3851&lon=2.1734&radius=10000
GET /api/spots/viewport/?south=41.30&west=2.10&north=41.45&east=2.25
```

Both accept an optional `limit` (maximum `250`) and answer with the
same shape:

```json
{
  "source": "openstreetmap",
  "count": 1,
  "results": [
    {
      "id": "osm:way:123456",
      "external": true,
      "name_spot": "Skatepark de la Mar Bella",
      "latitude": 41.3985,
      "longitude": 2.2055,
      "category": "skatepark",
      "source": "osm",
      "osm_id": 123456,
      "osm_type": "way",
      "image_url": null
    }
  ],
  "area": {"type": "viewport", "south": 41.3, "west": 2.1,
           "north": 41.45, "east": 2.25},
  "cached": false,
  "stale": false,
  "attribution": "© OpenStreetMap contributors"
}
```

The live results

* are **never written to the database**,
* are limited to `leisure=skatepark`, so plazas and generic parks are
  not shown as skateparks,
* are deduplicated by OSM type and id,
* carry `external: true` and an id with the `osm:` prefix,
* include nodes, ways and relations,
* reuse the same address and image rules as the registered spots,
* keep the latest answer for a day (`OVERPASS_DISCOVERY_STALE_SECONDS`)
  so a temporary Overpass `502` or `504` does not empty the map or the
  feed.

The browser only asks for a viewport when the map is at zoom 10 or
closer, and the request is debounced. A viewport may span at most two
degrees, which keeps the public Overpass query small. The feed uses the
bounding box of the selected place when it is small enough and falls
back to a 50 km radius around its centre for a country or a very large
region.

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `OVERPASS_DISCOVERY_DEFAULT_RADIUS` | `10000` | Default radius in metres. |
| `OVERPASS_DISCOVERY_MAX_RADIUS` | `50000` | Largest accepted radius. |
| `OVERPASS_DISCOVERY_MAX_RESULTS` | `250` | Results kept per answer. |
| `OVERPASS_DISCOVERY_MAX_VIEWPORT_SPAN` | `2.0` | Largest accepted box, degrees. |
| `OVERPASS_DISCOVERY_CACHE_SECONDS` | `300` | How long an answer is fresh. |
| `OVERPASS_DISCOVERY_STALE_SECONDS` | `86400` | How long a stale answer is kept. |
| `OVERPASS_DISCOVERY_THROTTLE_RATE` | `60/min` | Requests allowed per user and minute. |

The location search of the map and the feed is public, because it is a
read-only helper of a public page:

```
GET /api/geocode/search/?q=Barcelona
```

The answer now includes the `bounding_box` of the place, so the map can
fit a city or a region without a second request:

```json
"bounding_box": {"south": 41.3170359, "west": 2.0524977,
                 "north": 41.4682658, "east": 2.2283634}
```

The two boxes and the radius are validated on the server. Outside the
usage policy the endpoints answer `400`; when Overpass is down and
there is no cached answer they answer `503` with an empty `results`
list, so the registered spots remain usable.

---

## Interactive location selection

Users publish their spots through a form with a map, so they never have
to type a latitude and a longitude by hand.

### The pages

| URL                     | What it does                                             |
| ----------------------- | -------------------------------------------------------- |
| `/spots/new/`           | The form to publish a new spot.                          |
| `/spots/<id>/edit/`     | The form to edit one of your spots.                      |

The pages are public, because the application logs the users in with a
JWT that the browser keeps in the local storage: the server can not
tell who is visiting. The API is what protects the spots, it refuses a
write from an unauthenticated user and a write on a spot of somebody
else. When the visitor does have a Django session the ownership is
checked on the page as well.

### The map

The map is drawn with **Leaflet** and uses the tiles of
**OpenStreetMap**. The visitor can

* click anywhere on the map to drop a marker,
* drag the marker to move it,
* search a skatepark, a street, an address or a neighbourhood,
* clear the selection.

The selected coordinates are shown under the map and are also sent
automatically with the form. The tiles are desaturated a little so the
map fits inside the dark interface.

The map is centred on **Guadalajara, Mexico** (`20.6767, -103.3475`,
zoom 13) and it opens on the coordinates of the spot when it is being
edited.

### The location search

The browser never talks to Nominatim directly. Every search goes
through the backend:

```
GET /api/geocode/search/?q=skatepark guadalajara
```

```json
{
  "query": "skatepark guadalajara",
  "count": 2,
  "results": [
    {
      "label": "Skatepark San Jacinto, Guadalajara, Jalisco, Mexico",
      "short_label": "Skatepark San Jacinto",
      "latitude": 20.6626053,
      "longitude": -103.2972632,
      "category": "leisure",
      "type": "skatepark",
      "osm_id": 256129315,
      "osm_type": "way",
      "bounding_box": {
        "south": 20.6400,
        "west": -103.3200,
        "north": 20.6800,
        "east": -103.2800
      }
    }
  ]
}
```

The proxy exists to respect the [Nominatim usage
policy](https://operations.osmfoundation.org/policies/nominatim/):

* the request carries a proper `User-Agent` that identifies the
  application,
* the answers are cached for 24 hours, so a popular search is not
  requested again,
* the whole application is limited to **one request per second**,
  globally and not per user, because the policy applies the limit to
  the sum of the traffic of every user,
* a search needs at least three characters,
* the search is only sent when the visitor asks for it, with the
  **Buscar** button or with the `Enter` key.

> **No auto-complete.** The policy states that *"auto-complete search
> is not yet supported by Nominatim and you must not implement such a
> service on the client side using the API"*, and lists it under the
> uses that are **strictly forbidden**. The form therefore does not
> search while the visitor types: the results only appear once the
> search is confirmed. The visitor still gets a list of results to
> pick from, so nothing is lost.

Not every skatepark exists in OpenStreetMap. The search is a helper,
never a requirement: a spot can always be placed by clicking on the
map, and a spot can be published without any location at all.

### Coordinates in the API

`latitude` and `longitude` are **optional**:

| Situation                             | Result                                        |
| ------------------------------------- | --------------------------------------------- |
| neither is sent                       | the spot is created without a location       |
| both are sent                         | the location is stored                        |
| both are sent as `null`               | the location is removed                       |
| both are sent as an empty string      | the location is removed                       |
| only one of them is sent              | `400`, "Latitude and longitude must be sent together" |
| a value outside of the valid range    | `400`, "Ensure this value is less than or equal to 90" |

The coordinates are stored as decimals with six decimal places, which
is about eleven centimetres. `0` is never used as a default: a spot
without a location keeps `NULL`.

> **Note for API clients:** the spot endpoint accepts `multipart/form-data`
> and `application/x-www-form-urlencoded` (needed for the image upload)
> and, since now, `application/json` as well. Over multipart, an empty
> value is how a location is removed.

### Configuration

| Variable                    | Default        | Purpose                                     |
| --------------------------- | -------------- | ------------------------------------------- |
| `GEOCODE_MIN_QUERY_LENGTH`  | `3`            | Shortest accepted search.                   |
| `GEOCODE_MAX_RESULTS`       | `8`            | Number of results returned per search.      |
| `GEOCODE_CACHE_SECONDS`     | `86400`        | How long a search is cached, seconds.       |
| `GEOCODE_LANGUAGE`          | `es`           | Language of the results.                    |
| `GEOCODE_THROTTLE_RATE`     | `30/min`       | Searches allowed per user and minute.       |
| `NOMINATIM_MAX_REQUESTS_PER_SECOND` | `1`    | Requests per second for the whole site.     |
| `NOMINATIM_USER_AGENT`      | `RollingUp-SkateSpots/1.0 (...)` | User-Agent sent to Nominatim.      |
| `OSM_TILE_URL`              | `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png` | Tile URL of the map.      |
| `OSM_TILE_MAX_ZOOM`         | `18`           | Highest zoom level of the map. CARTO stops at 18. |
| `OSM_TILE_SUBDOMAINS`       | *(empty)*      | Only for a provider that uses subdomains.   |
| `OSM_TILE_API_KEY`          | *(empty)*      | Key of the tile provider, CARTO needs one.  |
| `OSM_CONTACT_EMAIL`         | `rollingup.app@gmail.com` | Contact address shown on the map. |
| `SECURE_REFERRER_POLICY`    | `strict-origin-when-cross-origin` | Lets the browser send the Referer to the tile servers. |

---

## Following the OpenStreetMap usage policies

The application uses three services of the OpenStreetMap Foundation.
Each one has its own usage policy and the application follows all
three.

### The tiles &mdash; [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)

The provider of the tiles is a setting, so it can be changed without a
new release, which is what the policy asks for.

| Provider | Key | Notes |
| -------- | --- | ----- |
| The CARTO Voyager basemaps (default) | **required** | The style that fits the interface. |
| The CARTO dark basemaps | **required** | `dark_all` instead of `voyager`. |
| The standard OpenStreetMap tiles | not needed | Free, no account. The dark look is done with a CSS filter. |

| Requirement | How it is met |
| ----------- | ------------- |
| Use exactly `https://tile.openstreetmap.org/{z}/{x}/{y}.png` when the standard tiles are used | `OSM_TILE_URL` is a setting. The default is CARTO, and the standard url has no `{s}` subdomain shortcut. |
| Show a clear attribution | The attribution is rendered by Leaflet in the corner of the map and keeps a readable size and contrast. It is never hidden behind a toggle or off screen. |
| Offer a way to report a map problem | The attribution links to `https://www.openstreetmap.org/fixthemap`. |
| Publish a contact address | The attribution links to `OSM_CONTACT_EMAIL`. |
| Send a valid `Referer` | `SECURE_REFERRER_POLICY` is set to `strict-origin-when-cross-origin`. Django's default, `same-origin`, drops the `Referer` on every cross origin request, which the policy forbids. |
| Do not hide the tile URL in the code | `OSM_TILE_URL` is a setting, so the service can be switched without a new release. |
| Do not prefetch or scrape tiles | Nothing is fetched that the visitor is not looking at. There is no offline mode. |
| Honour the caching headers | The browser caches the tiles with the headers the server sends. |
| Credit both projects on CARTO | The attribution adds the credit of CARTO when that provider is used, as their terms ask. |

> **The raster tiles of CARTO only go up to zoom 18.** A bigger
> `OSM_TILE_MAX_ZOOM` makes the server answer *"Forbidden: raster tiles
> are available up to zoom 18"*, so the map shows empty tiles instead
> of the streets. The application lowers the value automatically and
> logs a warning.
>
> **Without a CARTO key the map does not work.** Since September 2026
> CARTO answers every request without a key with the same placeholder
> tile that says *API KEY REQUIRED*, whatever the location is. Get a
> free key at <https://carto.com/basemaps/apikey/> and put it in
> `OSM_TILE_API_KEY`.
>
> ```bash
> # The Voyager style, the default
> OSM_TILE_URL="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
> OSM_TILE_SUBDOMAINS="abcd"
> OSM_TILE_MAX_ZOOM="18"
> OSM_TILE_API_KEY="your_key_here"
>
> # The dark style
> OSM_TILE_URL="https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png"
>
> # The standard OpenStreetMap tiles, no key needed
> OSM_TILE_URL="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
> OSM_TILE_SUBDOMAINS=""
> OSM_TILE_MAX_ZOOM="19"
> ```

### The geocoder &mdash; [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)

| Requirement | How it is met |
| ----------- | ------------- |
| Maximum of one request per second | `NOMINATIM_MAX_REQUESTS_PER_SECOND` (1 by default) is applied globally by `skate.geocode.services`, so the traffic of every user is added up and stays under the limit. |
| Identify the application | Every request carries `User-Agent: RollingUp-SkateSpots/1.0 (https://rolling-up.onrender.com)`. |
| Cache the results | The answers are cached for 24 hours. |
| Use a proxy | The browser never calls Nominatim, it goes through `/api/geocode/search/`. |
| **No auto-complete** | The form does not search while the visitor types. The search is only sent when it is confirmed, because the policy forbids building an auto-complete on the public API. |
| Display the attribution | The search box shows *"Búsqueda por © OpenStreetMap contributors"*. |
| Stay switchable | `NOMINATIM_API_URL` is a setting. |

### The data &mdash; Overpass API

The importer sends one query per run, with the same identifying
`User-Agent`, and it caches the answers it receives.

> **Note:** the global rate limit is held in the memory of the process.
> When the application runs with more than one worker, each worker
> keeps its own counter. Use a shared cache or a single worker if the
> traffic grows.

---

## The map of the spots

The map is the central piece of the application. It lives at **`/map/`**
and reads the spots from the public API, so it works without an
account.

### The layout

**On a desktop** the map takes the space on the left and the list of
the spots is a column of 340 pixels on the right. Above both there is a
bar with the search and a row with the filters.

**On a phone** the map takes the whole screen, the search floats above
it and the list becomes a sheet that comes up from the bottom. The head
of the sheet is its handle.

### The markers

Every spot gets its own marker and the shape tells the kind of the
spot, so the markers can be told apart without relying on the colour
only:

| Shape  | Kind of spot |
| ------ | ------------ |
| square | `skatepark`  |
| circle | `street`     |
| triangle | `diy`       |

The fill tells where the spot comes from: the spots imported from
OpenStreetMap are solid and the ones of the community are hollow.

### The API the map reads

The map uses the endpoint that already existed, with three optional
parameters. Without them the answer is the same as before.

```
GET /api/spots/?search=oasis&category=skatepark&source=osm
```

| Parameter  | What it does |
| ---------- | ------------ |
| `search`   | Looks for the text in the name and in the description. |
| `category` | `skatepark`, `street` or `diy`. |
| `source`   | `osm` or `community`. |

A wrong value is ignored, the map never ends up empty because of a
typo. The answer is paginated and the map follows the pages until the
spots are exhausted, up to 500 of them.

Every spot carries its `id`, `name_spot`, `body`, `latitude`,
`longitude`, `category`, `source`, `image_url`, `rating` and
`rating_count`. The `rating` is the average of the scores and it is
read only, a client can not send it.

### The type of a spot

The model had no kind of spot, so one was added:

| Value | Meaning |
| ----- | ------- |
| `skatepark` | A built skatepark. |
| `street` | A spot in the street. |
| `diy` | A homemade spot. |

The importer fills it from the OpenStreetMap tags: a place tagged
`leisure=skatepark`, or a place that calls itself a skatepark in its
name, is a `skatepark`. The users pick it when they publish a spot.

### The tiles go through the application

The tiles are served by `/tiles/{z}/{x}/{y}.png` instead of by the
browser directly. Two reasons:

* the key of the tile provider is a credential and it must not reach
  the browser,
* the request can carry a `User-Agent` that identifies the
  application and the caching headers of the provider are passed on,
  which the usage policies ask for.

The proxy only fetches the tiles that the browser is showing, there is
no prefetching and no offline mode.

### Configuration

| Variable              | Default | Purpose                                   |
| --------------------- | ------- | ----------------------------------------- |
| `MAP_DEFAULT_LAT`     | `20.6767` | Latitude the map opens at.              |
| `MAP_DEFAULT_LON`     | `-103.3475` | Longitude the map opens at.            |
| `MAP_DEFAULT_ZOOM`    | `13`    | Zoom the map opens at.                     |
| `TILE_PROXY_PATH`     | `/tiles/{z}/{x}/{y}{r}.png` | Where the tiles are served from. |

---

## The feed of the spots

The feed lives at **`/feed/`**. It is the editorial page of the
application: a lot of air, big photography and a clear hierarchy.

### What it reads

The feed uses the endpoint that already existed:

```
GET /api/spots/?search=<text>&limit=24
```

The `search` parameter is the one the endpoint already understands, it
looks for the text in the name and in the description of the spots. The
pages of the answer are followed until there are no more spots.

### The plates

Every spot gets a card with

1. the picture of the spot,
2. the name,
3. the place and the rating,
4. a link with the directions to the spot.

A spot without a picture gets a **plate**: a monogram with the kind of
the spot, so the composition of the page stays together. A picture
that does not load gets the same plate.

The layout is a CSS Grid of three columns with cards that span a
different number of rows, so the page has the rhythm of a magazine
without a masonry library. It falls down to two columns on a tablet
and to one on a phone.

### The place and the rating

The API does not have a field for the city or for the neighbourhood.
The address is read from the tags of OpenStreetMap when the spot comes
from there, and the line is left out when there is nothing to show.

A spot without a rating says *Not rated yet*. It never gets a score of
zero.

### Opening a spot

The project has no public page for a single spot, the only one is the
page to edit a spot, which belongs to its author. The cards open the
spot on the map instead, with `?spot=<id>`, where the panel of the map
shows the name, the kind, the rating, the description and the
directions.

### Configuration

Nothing to configure. The page reads the same API as the rest of the
application.

---

## The type of the application

Two families, and only two, on every page:

| Face | Weights | Where |
| ---- | ------- | ----- |
| **LINE Seed JP** | 400, 700 | The system face: body, navigation, buttons, forms, labels and metadata. |
| **Big Shoulders Display** | 500, 600, 700 | The display face: the titles, the brand and the names of the spots. |

They are loaded once, from `skate/static/styles.css`, and every page
uses them through the same rules.

```css
@import url('https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@500;600;700&family=LINE+Seed+JP:wght@400;700&display=swap');
```

**Why LINE Seed JP.** It is the corporate typeface of LINE, a geometry
based grotesque that is neutral enough to carry the interface and still
has a character of its own. It only comes with four weights (100, 400,
700 and 800), so the middle of the scale is served with the two that
are close to it.

It is hosted on Google Fonts and the browser only downloads the Latin
subset, about 33 KB per weight, the rest of the file is for the
Japanese glyphs and is never fetched.

**Why Big Shoulders Display next to it.** A tall condensed face against
a neutral grotesque is the classic pairing for an editorial layout: the
display face carries the voice, the system face stays out of the way.
It is also the face that gives the pages their streetwear character.

The fonts that were there before (`Poppins`, `Miniver` and `Roboto`)
were removed: `Miniver` and `Roboto` were downloaded on every page and
were never used by a single rule.

---

## Attribution and licence (ODbL)

The data retrieved from OpenStreetMap is licensed under the
**Open Database License (ODbL) 1.0**. Importing it into this database
does not remove that obligation.

**Any user interface that displays imported skateparks must show the
attribution:**

> &copy; OpenStreetMap contributors

The attribution is already stored on every imported record in
`osm_metadata["attribution"]`, together with
`osm_metadata["license"] = "ODbL-1.0"`, so it can be rendered directly
from the API response.

Further requirements of the ODbL:

* The attribution must be **visible on the page**, not only in the
  source code or in a hover tooltip.
* Derived databases have to be **shared under the ODbL** as well.
* The licence and the attribution have to be kept when the data is
  exported or re-published.

Full details: <https://www.openstreetmap.org/copyright> and
<https://opendatacommons.org/licenses/odbl/1-0/>

---

## Running the development server

The usual command serves plain HTTP only:

```bash
python manage.py runserver
```

Django's `runserver` does not speak HTTPS, so any client that opens an
`https://` connection to it (a browser that upgrades the scheme, a mobile
app, a service worker) gets a `Bad request syntax` error with the message
*"You're accessing the development server over HTTPS, but it only supports
HTTP."*.

For those cases there is a `runsslserver` command that runs the same
development server (auto-reloader, debug pages, static files) behind TLS:

```bash
python manage.py runsslserver            # https://127.0.0.1:8000/
python manage.py runsslserver 0.0.0.0:8443   # reachable from a phone
```

The first run generates a self-signed certificate in `skate/certs/`
(`dev.crt` and `dev.key`, both ignored by git). The browser shows a
certificate warning that has to be accepted once. The paths can be changed
with `--certfile` and `--keyfile`, or with the `SSL_CERTFILE` and
`SSL_KEYFILE` environment variables.

Use `http://` when the client does not need a secure origin, it is always
the simpler option.

---

## Tests

The whole suite mocks the external services, it never depends on a live
Overpass connection.

```bash
python manage.py test skate
```

The location picker is plain JavaScript, so it has its own test that
runs against a small DOM stub instead of a real browser. Node runs it
without any dependency:

```bash
node skate/tests/spot_form.test.js
node skate/tests/location_search.test.js
```

| Test module                 | Covers                                                       |
| --------------------------- | ------------------------------------------------------------ |
| `skate/tests/test_osm_parser.py`  | Nodes, ways, relations, missing names, missing tags, invalid coordinates, skatepark detection. |
| `skate/tests/test_osm_client.py`  | Successful responses, rejected queries, connection failures, retries, rate limiting, invalid payloads. |
| `skate/tests/test_osm_import.py`  | Creation, duplicate prevention, repeated imports, dry run, community protection, the management command. |
| `skate/tests/test_location_picker.py` | Coordinate validation, creating and editing a spot with or without a location, image upload, the location search, its bounding box and the form pages. |
| `skate/tests/test_discovery.py` | Nearby and viewport validation, nodes/ways/relations, deduplication, the `leisure=skatepark` query, caching, stale answers and the `503`/`400` responses. |
| `skate/tests/test_map.py` | The endpoint the map reads, the search and the filters, the ratings, the page of the map and the proxy of the tiles. |
| `skate/tests/spot_form.test.js`    | The map, the marker, the manual coordinates, the debounced search and the payload that is sent. |
| `skate/tests/location_search.test.js` | The shared city/region search, its submit-only request, the bounding box and its error states. |
| `skate/tests/map.test.js`           | The map, the markers, the list, the selection, the search, the filters, the location, the pagination and the link to a spot. |
| `skate/tests/feed.test.js`          | The cards, the pictures, the plates, the rating, the directions, the search and the states of the feed. |
