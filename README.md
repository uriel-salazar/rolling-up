# Rolling Up &mdash; Skate Spots API

Django REST Framework backend for the *Rolling Up* skateboarding platform.
Users can register, publish their own skate spots and rate the spots of
other skaters. Existing skateparks can additionally be imported from
OpenStreetMap.

---

## Importing skateparks from OpenStreetMap

### How the integration works

The importer talks to the **official Overpass API**
(`https://overpass-api.de/api/interpreter`) and pulls every object that
is tagged as a skatepark:

| Tag                | Meaning                                                  |
| ------------------ | -------------------------------------------------------- |
| `leisure=skatepark` | A skatepark, always imported.                           |
| `sport=skateboard`  | Skateboarding somewhere. Only imported when the object also looks like a skatepark (a `leisure` value of `skatepark`, `sports_centre`, `sports_center`, `park` or `recreation_ground`, or a name / description that mentions a skatepark). This avoids importing a single ramp or a basketball court that merely mentions skateboarding. |

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

## Tests

The whole suite mocks the external services, it never depends on a live
Overpass connection.

```bash
python manage.py test skate
```

| Test module                 | Covers                                                       |
| --------------------------- | ------------------------------------------------------------ |
| `skate/tests/test_osm_parser.py`  | Nodes, ways, relations, missing names, missing tags, invalid coordinates, skatepark detection. |
| `skate/tests/test_osm_client.py`  | Successful responses, rejected queries, connection failures, retries, rate limiting, invalid payloads. |
| `skate/tests/test_osm_import.py`  | Creation, duplicate prevention, repeated imports, dry run, community protection, the management command. |
