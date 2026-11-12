/**
 * The map of the skate spots of Rolling Up.
 *
 * The spots come from the public API of the project, the map is drawn
 * with Leaflet and the tiles come from the tile provider of the
 * application.
 *
 * The file is organised in the following parts:
 *
 *   1. the configuration that the server puts in the page,
 *   2. the API layer,
 *   3. the markers,
 *   4. the map itself,
 *   5. the list of results and the selection,
 *   6. the search and the filters,
 *   7. the location of the visitor.
 */
(function () {
    'use strict';

    // -----------------------------------------------------------------
    // 1. Configuration
    // -----------------------------------------------------------------

    const mapElement = document.getElementById('map');
    if (!mapElement) {
        return;
    }

    const searchInput = document.getElementById('spot-search');
    const clearSearchButton = document.getElementById('clear-search');
    const locationSearchInput = document.getElementById('map-location-search');
    const locationSearchResults = document.getElementById('map-location-results');
    const locationSearchClear = document.getElementById('map-location-clear');
    const filtersPanel = document.getElementById('map-filters');
    const statusBox = document.getElementById('map-status');
    const listBox = document.getElementById('spot-list');
    const preview = document.getElementById('spot-preview');
    const previewImage = document.getElementById('preview-image');
    const previewImageAttribution = document.getElementById(
        'preview-image-attribution'
    );
    const previewName = document.getElementById('preview-name');
    const previewCategory = document.getElementById('preview-category');
    const previewRating = document.getElementById('preview-rating');
    const previewSource = document.getElementById('preview-source');
    const previewBody = document.getElementById('preview-body');
    const previewLink = document.getElementById('preview-link');
    const previewDirections = document.getElementById('preview-directions');
    const previewClose = document.getElementById('preview-close');
    const sidebar = document.getElementById('map-sidebar');
    const sidebarHead = document.getElementById('sidebar-head');
    const sidebarToggle = document.getElementById('sidebar-toggle');

    const API_URL = '/api/spots/';

    // How many spots are read at most and how many pages are asked for.
    const MAX_SPOTS = 500;
    const PAGE_SIZE = 50;
    const MAX_PAGES = 10;

    // The search waits for the visitor to stop typing.
    const SEARCH_DELAY = 300;

    // The external skateparks are discovered for the current viewport.
    const DISCOVERY_DELAY = 450;
    const DISCOVERY_MIN_ZOOM = 10;
    const DISCOVERY_MAX_SPAN = 1.5;
    const DISCOVERY_LIMIT = 250;

    const config = {
        tileUrl: mapElement.dataset.tileUrl,
        tileMaxZoom: Number(mapElement.dataset.tileMaxZoom) || 18,
        tileSubdomains: mapElement.dataset.tileSubdomains || '',
        tileAttribution: mapElement.dataset.tileAttribution || '',
        center: [
            Number(mapElement.dataset.defaultLat) || 20.6767,
            Number(mapElement.dataset.defaultLon) || -103.3475,
        ],
        zoom: Number(mapElement.dataset.defaultZoom) || 13,
    };

    const CATEGORY_LABELS = {
        skatepark: 'Skatepark',
        street: 'Street spot',
        diy: 'DIY spot',
    };

    const SOURCE_LABELS = {
        osm: 'OpenStreetMap',
        google: 'Google',
        community: 'Comunidad',
    };

    // The source filter keeps its two existing controls. The Google
    // results are part of the same external discovery as OSM, so they
    // follow the OpenStreetMap control without adding a new one.
    const SOURCE_GROUPS = {
        osm: ['osm', 'google'],
        community: ['community'],
        google: ['google'],
    };

    // -----------------------------------------------------------------
    // 2. The API
    // -----------------------------------------------------------------

    let requestController = null;

    /**
     * Read the spots from the API.
     *
     * The endpoint is paginated, so the pages are followed until the
     * spots are exhausted or the limit is reached.
     *
     * @param {Object} params The query parameters of the request.
     * @returns {Promise<Array>} The spots of the API.
     */
    async function fetchSpots(params) {
        if (requestController) {
            requestController.abort();
        }
        requestController = new AbortController();

        const query = new URLSearchParams(params);
        query.set('limit', String(PAGE_SIZE));

        let url = API_URL + '?' + query.toString();
        const spots = [];
        let pages = 0;

        while (url && pages < MAX_PAGES && spots.length < MAX_SPOTS) {
            const response = await fetch(url, {
                headers: { 'Accept': 'application/json' },
                signal: requestController.signal,
            });

            if (!response.ok) {
                throw new Error('The API answered with HTTP ' + response.status);
            }

            const data = await response.json();
            const results = Array.isArray(data.results) ? data.results : [];

            spots.push(...results);
            url = data.next;
            pages += 1;
        }

        return spots.slice(0, MAX_SPOTS);
    }

    /** Return the query parameters of the current search and filters. */
    function currentParams() {
        const params = { search: searchInput.value.trim() };

        const categories = readChecked('category');
        const sources = readChecked('source');

        // The API takes a single value for each filter, so the filter is
        // only sent when exactly one option is selected. When more than
        // one is selected the answer is filtered in the browser, which
        // keeps the spots of every selected option.
        if (categories.length === 1) {
            params.category = categories[0];
        }
        if (sources.length === 1 && sources[0] === 'community') {
            params.source = 'community';
        }

        params._categories = categories;
        params._sources = sources;

        return params;
    }

    /** Return the values of the checkboxes of a group that are checked. */
    function readChecked(name) {
        const boxes = document.querySelectorAll(
            'input[name="' + name + '"]:checked'
        );
        return Array.prototype.map.call(boxes, (box) => box.value);
    }

    // -----------------------------------------------------------------
    // 3. The markers
    // -----------------------------------------------------------------

    /**
     * Build the icon of a marker.
     *
     * The shape tells the kind of the spot and the fill tells where it
     * comes from, so the markers can be told apart without relying on
     * the colour only.
     */
    function markerIcon(spot, isSelected) {
        const category = spot.category || 'street';
        const isOsm = spot.source === 'osm';

        const fill = isOsm ? '#111111' : '#f5f5f5';
        const stroke = '#111111';
        const inner = isOsm ? '#f5f5f5' : '#111111';

        let shape = '';
        if (category === 'skatepark') {
            shape = '<rect x="6" y="6" width="12" height="12" rx="2.5" '
                + 'fill="' + fill + '" stroke="' + stroke + '" stroke-width="1.5"/>';
        } else if (category === 'diy') {
            shape = '<path d="M12 4 L20 19 L4 19 Z" fill="' + fill + '" '
                + 'stroke="' + stroke + '" stroke-width="1.5" stroke-linejoin="round"/>';
        } else {
            shape = '<circle cx="12" cy="12" r="6.5" fill="' + fill + '" '
                + 'stroke="' + stroke + '" stroke-width="1.5"/>';
        }

        const scale = isSelected ? 1.35 : 1;

        const html = '<div class="marker marker-' + category
            + (isOsm ? ' marker-osm' : ' marker-community')
            + (isSelected ? ' is-selected' : '') + '" style="transform: scale(' + scale + ')">'
            + '<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">'
            + shape + '</svg>'
            + '<span class="marker-dot" style="background:' + inner + '"></span>'
            + '</div>';

        return L.divIcon({
            className: 'marker-wrapper',
            html: html,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
            popupAnchor: [0, -12],
        });
    }

    /** The icon of the position of the visitor. */
    function locationIcon() {
        const html = '<div class="marker marker-location">'
            + '<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">'
            + '<circle cx="12" cy="12" r="7" fill="#2f7de1" fill-opacity="0.25" '
            + 'stroke="#2f7de1" stroke-width="1.5"/>'
            + '<circle cx="12" cy="12" r="3.5" fill="#2f7de1" stroke="#ffffff" stroke-width="1.5"/>'
            + '</svg></div>';

        return L.divIcon({
            className: 'marker-wrapper',
            html: html,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
        });
    }

    // -----------------------------------------------------------------
    // 4. The map
    // -----------------------------------------------------------------

    let map = null;
    let markerLayer = null;
    let locationMarker = null;
    let locationCircle = null;

    /** The markers of the spots, by the id of the spot. */
    const markers = new Map();

    /** The spots that are on the map, by the id of the spot. */
    const spotsById = new Map();

    /** The spot that is selected right now. */
    let selectedId = null;

    /** The registered spots and the live OpenStreetMap discoveries. */
    let registeredSpots = [];
    let externalSpots = new Map();
    let externalController = null;
    let viewportTimer = null;
    let locationSearch = null;

    function initMap() {
        if (typeof L === 'undefined') {
            showStatus('El mapa no se pudo cargar. Recarga la página.', 'error');
            return;
        }

        map = L.map('map', {
            center: config.center,
            zoom: config.zoom,
            scrollWheelZoom: true,
            zoomControl: true,
        });

        const tileOptions = {
            maxZoom: config.tileMaxZoom,
            attribution: config.tileAttribution,
        };
        if (config.tileSubdomains) {
            tileOptions.subdomains = config.tileSubdomains;
        }

        L.tileLayer(config.tileUrl, tileOptions).addTo(map);

        // The markers live in their own layer, so they can be replaced
        // without touching the rest of the map.
        markerLayer = L.layerGroup().addTo(map);

        L.control.zoom({ position: 'bottomright' }).addTo(map);
        L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);

        // Leaflet measures the container when it starts. The layout of
        // the page settles a little later, so the map has to be told
        // to measure itself again, otherwise a strip of the map stays
        // empty.
        window.requestAnimationFrame(function () {
            map.invalidateSize();
        });
        window.setTimeout(function () {
            map.invalidateSize();
        }, 300);

        createCustomControls();

        map.on('moveend', function () {
            scheduleDiscovery();
        });
        map.on('zoomend', function () {
            scheduleDiscovery();
        });
    }

    /** The controls that Leaflet does not bring. */
    function createCustomControls() {
        const control = L.control({ position: 'bottomright' });

        control.onAdd = function () {
            const container = L.DomUtil.create(
                'div', 'leaflet-bar map-custom-controls'
            );

            const locateButton = L.DomUtil.create(
                'button', 'map-control-button', container
            );
            locateButton.type = 'button';
            locateButton.innerHTML = '&#9678;';
            locateButton.title = 'Mi ubicación';
            locateButton.setAttribute('aria-label', 'Centrar en mi ubicación');
            locateButton.onclick = function (event) {
                L.DomEvent.stopPropagation(event);
                locateVisitor();
            };

            const resetButton = L.DomUtil.create(
                'button', 'map-control-button', container
            );
            resetButton.type = 'button';
            resetButton.innerHTML = '&#8634;';
            resetButton.title = 'Ver todos los spots';
            resetButton.setAttribute('aria-label', 'Ver todos los spots');
            resetButton.onclick = function (event) {
                L.DomEvent.stopPropagation(event);
                resetView();
            };

            return container;
        };

        control.addTo(map);
    }

    /** Put the map back where it started. */
    function resetView() {
        map.setView(config.center, config.zoom);
        if (selectedId !== null) {
            selectSpot(null);
        }
    }

    // -----------------------------------------------------------------
    // 5. The results and the selection
    // -----------------------------------------------------------------

    /** Draw the markers and fill the list. */
    function render(spots) {
        markerLayer.clearLayers();
        markers.clear();
        spotsById.clear();

        let shown = 0;

        spots.forEach(function (spot) {
            const position = readPosition(spot);
            if (!position) {
                // A spot without coordinates can not be on the map.
                return;
            }

            spotsById.set(spot.id, spot);
            shown += 1;

            const marker = L.marker(position, {
                icon: markerIcon(spot, false),
                title: spot.name_spot,
                alt: spot.name_spot,
                keyboard: true,
                riseOnHover: true,
            });

            marker.on('click', function () {
                selectSpot(spot.id, { fromMap: true });
            });

            marker.addTo(markerLayer);
            markers.set(spot.id, marker);
        });

        renderList(spots.filter(function (spot) {
            return readPosition(spot) !== null;
        }));

        if (shown === 0) {
            showStatus(
                spots.length
                    ? 'Ninguno de estos spots tiene una ubicación.'
                    : 'No hay spots que cumplan la búsqueda.',
                'empty'
            );
        } else {
            showStatus(
                shown + (shown === 1 ? ' spot' : ' spots'),
                'ok'
            );
        }

        openSpotOfTheLink(spots);
    }

    /**
     * Open the spot of the link.
     *
     * The feed sends the visitor to the map with the id of the spot in
     * the address, so the spot is selected as soon as the spots are
     * loaded.
     */
    function openSpotOfTheLink(spots) {
        if (selectedId !== null || !spots.length) {
            return;
        }

        const wanted = new URLSearchParams(window.location.search).get('spot');
        if (!wanted) {
            return;
        }

        const spot = spots.find(function (item) {
            return String(item.id) === wanted;
        });

        if (!spot || !readPosition(spot)) {
            return;
        }

        selectSpot(spot.id, { fromList: true });
    }

    /**
     * Return the url that opens Google Maps with the directions to a
     * spot, or an empty string when the spot has no place.
     */
    function directionsUrl(spot) {
        const latitude = spot.latitude;
        const longitude = spot.longitude;

        if (latitude === null || latitude === undefined || latitude === ''
            || longitude === null || longitude === undefined || longitude === '') {
            return '';
        }

        return 'https://www.google.com/maps/dir/?api=1&destination='
            + encodeURIComponent(latitude + ',' + longitude);
    }

    /** Return the position of a spot, or null when it has none. */
    function readPosition(spot) {        if (spot.latitude === null || spot.longitude === null
            || spot.latitude === undefined || spot.longitude === undefined
            || spot.latitude === '' || spot.longitude === '') {
            return null;
        }

        const latitude = Number(spot.latitude);
        const longitude = Number(spot.longitude);

        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
            return null;
        }
        if (latitude < -90 || latitude > 90) {
            return null;
        }
        if (longitude < -180 || longitude > 180) {
            return null;
        }

        return [latitude, longitude];
    }

    /** Fill the list of results. */
    function renderList(spots) {
        listBox.innerHTML = '';

        spots.forEach(function (spot) {
            const item = document.createElement('li');
            item.className = 'spot-item';
            item.dataset.spotId = String(spot.id);

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'spot-item-button';

            const name = document.createElement('span');
            name.className = 'spot-item-name';
            name.textContent = spot.name_spot;

            const meta = document.createElement('span');
            meta.className = 'spot-item-meta';
            meta.appendChild(buildTag(
                CATEGORY_LABELS[spot.category] || 'Spot',
                'tag tag-' + (spot.category || 'street')
            ));
            if (spot.rating) {
                meta.appendChild(buildTag(
                    '★ ' + Number(spot.rating).toFixed(1), 'tag tag-rating'
                ));
            }
            meta.appendChild(buildTag(
                spot.external
                    ? 'OSM live'
                    : (SOURCE_LABELS[spot.source] || spot.source),
                'tag tag-source'
            ));

            button.appendChild(name);
            button.appendChild(meta);
            button.addEventListener('click', function () {
                selectSpot(spot.id, { fromList: true });
            });

            item.appendChild(button);
            listBox.appendChild(item);
        });
    }

    /** Build a small label. */
    function buildTag(text, className) {
        const tag = document.createElement('span');
        tag.className = className;
        tag.textContent = text;
        return tag;
    }

    /**
     * Select a spot, or clear the selection.
     *
     * The map and the list are kept in sync: a marker that is clicked
     * highlights the entry of the list and the other way round.
     */
    function selectSpot(spotId, options) {
        const settings = options || {};

        selectedId = spotId;

        // The markers are redrawn so the selected one stands out.
        markers.forEach(function (marker, id) {
            const spot = spotsById.get(id);
            if (spot) {
                marker.setIcon(markerIcon(spot, id === selectedId));
            }
        });

        // The entry of the list is highlighted too.
        Array.prototype.forEach.call(
            listBox.querySelectorAll('.spot-item'),
            function (item) {
                const isSelected = String(item.dataset.spotId) === String(selectedId);
                item.classList.toggle('is-selected', isSelected);
                if (isSelected) {
                    item.scrollIntoView({ block: 'nearest' });
                }
            }
        );

        if (selectedId === null) {
            preview.hidden = true;
            return;
        }

        const spot = spotsById.get(selectedId);
        if (!spot) {
            return;
        }

        const position = readPosition(spot);
        if (position && (settings.fromList || settings.fromMap)) {
            map.setView(position, Math.max(map.getZoom(), 15));
        }

        fillPreview(spot);
    }

    /** Fill the picture of the selected spot, when it has one. */
    function fillPreviewImage(spot) {
        if (!previewImage) {
            return;
        }

        previewImage.onerror = null;
        previewImage.removeAttribute('src');
        previewImage.removeAttribute('title');
        previewImage.alt = '';
        previewImage.hidden = true;

        if (previewImageAttribution) {
            previewImageAttribution.textContent = '';
        }

        const url = spot.image_url;
        if (!url) {
            return;
        }

        const attribution = spot.image_attribution
            ? String(spot.image_attribution)
            : '';

        // A broken photograph must not break the panel: it simply
        // disappears and the existing layout of the spot stays.
        previewImage.onerror = function () {
            previewImage.hidden = true;
            previewImage.removeAttribute('src');
            if (previewImageAttribution) {
                previewImageAttribution.textContent = '';
            }
        };
        previewImage.src = url;
        previewImage.alt = spot.name_spot || 'Skatepark';
        previewImage.title = attribution;
        previewImage.hidden = false;

        if (previewImageAttribution) {
            previewImageAttribution.textContent = attribution;
        }
    }

    /** Fill the panel with the information of a spot. */
    function fillPreview(spot) {
        fillPreviewImage(spot);
        previewName.textContent = spot.name_spot;

        previewCategory.textContent =
            CATEGORY_LABELS[spot.category] || 'Spot';
        previewCategory.className = 'preview-category preview-category-'
            + (spot.category || 'street');

        if (spot.rating) {
            previewRating.textContent = '★ ' + Number(spot.rating).toFixed(1)
                + ' (' + (spot.rating_count || 0) + ')';
            previewRating.hidden = false;
        } else {
            previewRating.textContent = 'Sin votos';
            previewRating.hidden = false;
        }

        previewSource.textContent = spot.external
            ? 'OSM live'
            : (SOURCE_LABELS[spot.source] || spot.source);

        const body = spot.body ? String(spot.body) : '';
        previewBody.textContent = body;
        previewBody.hidden = body === '';

        // The directions to the spot, when it has a place.
        const directions = directionsUrl(spot);
        if (previewDirections) {
            previewDirections.href = directions;
            previewDirections.hidden = !directions;
        }

        if (spot.external && spot.osm_type && spot.osm_id) {
            previewLink.href = 'https://www.openstreetmap.org/' + spot.osm_type
                + '/' + spot.osm_id;
            previewLink.textContent = 'Ver en OpenStreetMap';
            previewLink.target = '_blank';
            previewLink.rel = 'noopener';
        } else {
            previewLink.href = '/spots/' + spot.id + '/';
            previewLink.textContent = 'Ver detalle';
            previewLink.removeAttribute('target');
            previewLink.removeAttribute('rel');
        }

        preview.hidden = false;
    }

    /** Write a message under the title of the list. */
    function showStatus(message, kind) {
        statusBox.textContent = message;
        statusBox.className = 'sidebar-status'
            + (kind ? ' sidebar-status-' + kind : '');
    }

    // -----------------------------------------------------------------
    // 6. The live discovery
    // -----------------------------------------------------------------

    /** The stable identity of a spot, also for live OSM results. */
    function spotIdentity(spot) {
        if (spot && spot.osm_type && spot.osm_id) {
            return 'osm:' + spot.osm_type + ':' + spot.osm_id;
        }
        return 'spot:' + spot.id;
    }

    /** Whether a spot is inside the viewport of the map. */
    function isInsideViewport(spot, viewport) {
        const position = readPosition(spot);
        if (!position) {
            return false;
        }
        return position[0] >= viewport.south && position[0] <= viewport.north
            && position[1] >= viewport.west && position[1] <= viewport.east;
    }

    /**
     * Return the current viewport when it is small enough for Overpass.
     * Low zooms are skipped because the answer would be enormous.
     */
    function currentViewport() {
        if (!map || !map.getBounds) {
            return null;
        }
        if (map.getZoom() < DISCOVERY_MIN_ZOOM) {
            return null;
        }

        const bounds = map.getBounds();
        if (!bounds || !bounds.getSouth) {
            return null;
        }

        const viewport = {
            south: bounds.getSouth(),
            west: bounds.getWest(),
            north: bounds.getNorth(),
            east: bounds.getEast(),
        };

        if (![viewport.south, viewport.west, viewport.north, viewport.east]
            .every(Number.isFinite)) {
            return null;
        }
        if (viewport.south >= viewport.north || viewport.west >= viewport.east) {
            return null;
        }
        if (viewport.north - viewport.south > DISCOVERY_MAX_SPAN
            || viewport.east - viewport.west > DISCOVERY_MAX_SPAN) {
            return null;
        }

        return viewport;
    }

    /** Merge registered spots with the live results, without duplicates. */
    function mergeSpots(registered, external) {
        const seen = new Set();
        const merged = [];

        registered.forEach(function (spot) {
            const identity = spotIdentity(spot);
            if (!seen.has(identity)) {
                seen.add(identity);
                merged.push(spot);
            }
        });

        external.forEach(function (spot) {
            const identity = spotIdentity(spot);
            if (!seen.has(identity)) {
                seen.add(identity);
                merged.push(spot);
            }
        });

        return merged;
    }

    /** Apply the search and the filters to any kind of spot. */
    function visibleSpots() {
        const categories = readChecked('category');
        const sources = readChecked('source');
        const term = searchInput.value.trim().toLowerCase();
        const viewport = currentViewport();

        let registered = registeredSpots;
        let external = Array.from(externalSpots.values());

        if (viewport) {
            registered = registered.filter(function (spot) {
                return isInsideViewport(spot, viewport);
            });
            external = external.filter(function (spot) {
                return isInsideViewport(spot, viewport);
            });
        } else if (registeredSpots.length) {
            // A live result for another place must not stay on the map
            // when the visitor zooms out to the whole world.
            external = [];
        }

        return mergeSpots(registered, external).filter(function (spot) {
            const category = spot.category || 'street';
            if (categories.indexOf(category) === -1) {
                return false;
            }

            const matchesSource = sources.some(function (source) {
                const group = SOURCE_GROUPS[source] || [source];
                return group.indexOf(spot.source) !== -1;
            });
            if (!matchesSource) {
                return false;
            }

            if (!term) {
                return true;
            }

            const name = String(spot.name_spot || '').toLowerCase();
            const body = String(spot.body || '').toLowerCase();
            return name.indexOf(term) !== -1 || body.indexOf(term) !== -1;
        });
    }

    /** Draw the registered spots and the live results. */
    function renderVisible() {
        render(visibleSpots());
    }

    /** Ask the API for the skateparks of the current viewport. */
    async function loadViewport() {
        const viewport = currentViewport();

        if (!viewport) {
            if (externalSpots.size) {
                externalSpots = new Map();
                renderVisible();
            }
            return;
        }

        if (externalController) {
            externalController.abort();
        }
        externalController = new AbortController();

        const query = new URLSearchParams({
            south: viewport.south.toFixed(6),
            west: viewport.west.toFixed(6),
            north: viewport.north.toFixed(6),
            east: viewport.east.toFixed(6),
            limit: String(DISCOVERY_LIMIT),
        });

        try {
            const response = await fetch(
                '/api/spots/viewport/?' + query.toString(),
                {
                    headers: { 'Accept': 'application/json' },
                    signal: externalController.signal,
                }
            );

            if (!response.ok) {
                throw new Error('The discovery API answered with HTTP '
                    + response.status);
            }

            const data = await response.json();
            const results = Array.isArray(data.results) ? data.results : [];
            const next = new Map();

            results.forEach(function (spot) {
                next.set(spotIdentity(spot), spot);
            });

            externalSpots = next;
            renderVisible();
        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }
            // The registered spots stay usable when Overpass is down.
            console.warn('The live skateparks could not be loaded:', error);
            showStatus('No se pudieron cargar los spots de OpenStreetMap.', 'error');
        }
    }

    /** Wait for the map to settle before asking Overpass. */
    function scheduleDiscovery(delay) {
        window.clearTimeout(viewportTimer);
        viewportTimer = window.setTimeout(
            loadViewport,
            delay === undefined ? DISCOVERY_DELAY : delay
        );
    }

    /** Move the map to the selected place. */
    function showPlace(place) {
        const bbox = place.bounding_box;

        if (bbox) {
            const south = Number(bbox.south);
            const west = Number(bbox.west);
            const north = Number(bbox.north);
            const east = Number(bbox.east);

            if ([south, west, north, east].every(Number.isFinite)
                && south < north && west < east) {
                map.fitBounds([[south, west], [north, east]], {
                    padding: [24, 24],
                    maxZoom: 16,
                });
                // A whole country/city bounding box is usually too large
                // for Overpass: make sure we end up close enough to discover.
                if (map.getZoom() < DISCOVERY_MIN_ZOOM) {
                    map.setZoom(DISCOVERY_MIN_ZOOM);
                }
                scheduleDiscovery(0);
                return;
            }
        }

        const latitude = Number(place.latitude);
        const longitude = Number(place.longitude);
        if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
            map.setView([latitude, longitude], 14);
            scheduleDiscovery(0);
        }
    }

    /** Build the shared location search of the map. */
    function setupLocationSearch() {
        if (!window.RollingUpLocationSearch || !locationSearchInput
            || !locationSearchResults || !map) {
            return;
        }

        locationSearch = window.RollingUpLocationSearch.create({
            input: locationSearchInput,
            results: locationSearchResults,
            clearButton: locationSearchClear,
            onSelect: showPlace,
            onClear: function () {
                externalSpots = new Map();
                resetView();
                renderVisible();
            },
        });
    }

    // -----------------------------------------------------------------
    // 7. The search and the filters
    // -----------------------------------------------------------------

    let searchTimer = null;

    function refresh() {
        showStatus('Cargando spots...', 'loading');

        const params = currentParams();
        delete params._categories;
        delete params._sources;

        fetchSpots(params)
            .then(function (spots) {
                registeredSpots = spots;
                renderVisible();
                scheduleDiscovery(0);
            })
            .catch(function (error) {
                if (error.name === 'AbortError') {
                    return;
                }
                console.error('The spots could not be loaded:', error);
                showStatus(
                    'No se pudieron cargar los spots. Inténtalo de nuevo.',
                    'error'
                );
            });
    }

    if (searchInput && clearSearchButton) {
        searchInput.addEventListener('input', function () {
            window.clearTimeout(searchTimer);
            clearSearchButton.hidden = searchInput.value === '';

            searchTimer = window.setTimeout(refresh, SEARCH_DELAY);
        });

        searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                searchInput.value = '';
                clearSearchButton.hidden = true;
                refresh();
            }
        });

        clearSearchButton.addEventListener('click', function () {
            searchInput.value = '';
            clearSearchButton.hidden = true;
            refresh();
            searchInput.focus();
        });
    }

    filtersPanel.addEventListener('change', function () {
        refresh();
    });

    previewClose.addEventListener('click', function () {
        selectSpot(null);
    });

    // -----------------------------------------------------------------
    // 8. The position of the visitor
    // -----------------------------------------------------------------

    /**
     * Ask the browser where the visitor is and move the map there.
     *
     * The position stays in the browser, it is never sent to the
     * server.
     */
    function locateVisitor() {
        if (!navigator.geolocation) {
            showStatus(
                'Este navegador no puede compartir tu ubicación.', 'error'
            );
            return;
        }

        showStatus('Buscando tu ubicación...', 'loading');

        navigator.geolocation.getCurrentPosition(
            function (position) {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;

                if (locationMarker) {
                    map.removeLayer(locationMarker);
                }
                if (locationCircle) {
                    map.removeLayer(locationCircle);
                }

                locationMarker = L.marker([latitude, longitude], {
                    icon: locationIcon(),
                    title: 'Tu ubicación',
                    alt: 'Tu ubicación',
                    zIndexOffset: 1000,
                }).addTo(map);

                if (position.coords.accuracy) {
                    locationCircle = L.circle([latitude, longitude], {
                        radius: position.coords.accuracy,
                        color: '#2f7de1',
                        weight: 1,
                        fillColor: '#2f7de1',
                        fillOpacity: 0.12,
                    }).addTo(map);
                }

                map.setView([latitude, longitude], 15);
                showStatus('Estás aquí.', 'ok');
            },
            function (error) {
                showStatus(geolocationMessage(error), 'error');
            },
            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 30000,
            }
        );
    }

    /** Return a message that explains why the location is not available. */
    function geolocationMessage(error) {
        if (!error) {
            return 'No se pudo obtener tu ubicación.';
        }
        if (error.code === 1) {
            return 'No diste permiso para ver tu ubicación.';
        }
        if (error.code === 2) {
            return 'Tu ubicación no está disponible en este momento.';
        }
        if (error.code === 3) {
            return 'La búsqueda de tu ubicación tardó demasiado.';
        }
        return 'No se pudo obtener tu ubicación.';
    }

    // -----------------------------------------------------------------
    // The mobile layout
    // -----------------------------------------------------------------

    /** Show or hide the list. On a phone it is a sheet at the bottom. */
    function toggleSidebar() {
        const isOpen = sidebar.classList.toggle('is-open');

        if (sidebarToggle) {
            sidebarToggle.setAttribute('aria-expanded', String(isOpen));
        }
        return isOpen;
    }

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function (event) {
            event.stopPropagation();
            toggleSidebar();
        });
    }

    // The head of the sheet is the handle of the sheet.
    if (sidebarHead) {
        sidebarHead.addEventListener('click', function (event) {
            const target = event.target;
            if (target && target.closest && target.closest('button')) {
                return;
            }
            toggleSidebar();
        });
    }

    // -----------------------------------------------------------------
    // Start
    // -----------------------------------------------------------------

    initMap();
    setupLocationSearch();
    refresh();
})();
