/**
 * Location picker for the spot form.
 *
 * Lets the user drop a marker on an OpenStreetMap map, search for a
 * place by name and keeps the hidden latitude / longitude inputs in
 * sync with the selection.
 *
 * The search goes through the backend proxy at /api/geocode/search/,
 * which identifies the application, caches the answers and throttles
 * the requests.
 *
 * The search is only sent when the visitor asks for it, by pressing
 * Enter or the search button. The Nominatim usage policy forbids
 * building an auto-complete on top of the public API, so nothing is
 * requested while the visitor is typing.
 */

(function () {
    'use strict';

    // Guadalajara, Mexico. Used when the spot has no location yet.
    const DEFAULT_CENTER = [20.6767, -103.3475];
    const DEFAULT_ZOOM = 13;
    const MIN_QUERY_LENGTH = 3;

    const mapElement = document.getElementById('map');
    if (!mapElement) {
        return;
    }

    const form = document.getElementById('spot-form');
    const searchInput = document.getElementById('location-search');
    const searchButton = document.getElementById('search-button');
    const resultsBox = document.getElementById('search-results');
    const latitudeInput = document.getElementById('latitude');
    const longitudeInput = document.getElementById('longitude');
    const latitudeManual = document.getElementById('latitude-manual');
    const longitudeManual = document.getElementById('longitude-manual');
    const coordinatesOutput = document.getElementById('coordinates-output');
    const clearButton = document.getElementById('clear-location');
    const mapError = document.getElementById('map-error');
    const statusBox = document.getElementById('form-status');
    const submitButton = document.getElementById('submit-button');

    let map = null;
    let marker = null;
    let searchController = null;

    // Navigation links of the embedded form must escape the iframe.
    if (document.body.classList.contains('is-embed')) {
        document.querySelectorAll('a[href="/profile/"], a[href="/feed/"]')
            .forEach(function (link) {
                link.target = '_top';
            });
    }

    // -----------------------------------------------------------------
    // Coordinates
    // -----------------------------------------------------------------

    /** Read a coordinate from a form control, ignoring empty values. */
    function readCoordinate(input) {
        const raw = (input.value || '').trim();
        if (raw === '') {
            return null;
        }
        const value = Number(raw);
        return Number.isFinite(value) ? value : null;
    }

    /** Round a coordinate to the precision accepted by the API. */
    function roundCoordinate(value) {
        return Number(Number(value).toFixed(6));
    }

    /** Write the coordinates into the hidden inputs and the readout. */
    function setCoordinates(latitude, longitude) {
        const hasLocation = latitude !== null && longitude !== null;

        if (hasLocation) {
            latitude = roundCoordinate(latitude);
            longitude = roundCoordinate(longitude);
        }

        latitudeInput.value = hasLocation ? String(latitude) : '';
        longitudeInput.value = hasLocation ? String(longitude) : '';

        // The manual fields are only overwritten when the pair is
        // complete, so a half typed coordinate is not thrown away.
        if (hasLocation) {
            latitudeManual.value = String(latitude);
            longitudeManual.value = String(longitude);
            coordinatesOutput.textContent =
                latitude.toFixed(6) + ', ' + longitude.toFixed(6);
            coordinatesOutput.classList.remove('is-empty');
        } else {
            coordinatesOutput.textContent = 'Ubicación no seleccionada';
            coordinatesOutput.classList.add('is-empty');
        }

        clearButton.hidden = !hasLocation;
    }

    /** Move the map to a position and put the marker there. */
    function selectPosition(latitude, longitude, options) {
        const settings = options || {};
        setCoordinates(latitude, longitude);

        if (!map) {
            return;
        }

        const position = [latitude, longitude];

        if (marker) {
            marker.setLatLng(position);
        } else {
            marker = L.marker(position, { draggable: true, autoPan: true }).addTo(map);
            marker.on('dragend', function () {
                const position = marker.getLatLng();
                setCoordinates(position.lat, position.lng);
            });
        }

        if (settings.pan !== false) {
            map.setView(position, settings.zoom || Math.max(map.getZoom(), 15));
        }
    }

    /** Remove the marker and clear the coordinates. */
    function clearLocation() {
        setCoordinates(null, null);
        latitudeManual.value = '';
        longitudeManual.value = '';
        if (marker && map) {
            map.removeLayer(marker);
        }
        marker = null;
    }

    // -----------------------------------------------------------------
    // Map
    // -----------------------------------------------------------------

    function initMap() {
        if (typeof L === 'undefined') {
            mapError.hidden = false;
            return;
        }

        const initialLatitude = Number(mapElement.dataset.latitude);
        const initialLongitude = Number(mapElement.dataset.longitude);
        const hasInitial = Number.isFinite(initialLatitude)
            && Number.isFinite(initialLongitude)
            && mapElement.dataset.latitude !== ''
            && mapElement.dataset.longitude !== '';

        map = L.map('map', {
            center: hasInitial ? [initialLatitude, initialLongitude] : DEFAULT_CENTER,
            zoom: hasInitial ? DEFAULT_ZOOM + 4 : DEFAULT_ZOOM,
            scrollWheelZoom: false,
        });

        // The tile URL and the attribution come from the server, so the
        // provider can be switched without a new release. The usage
        // policies of the tile services ask for exactly that, and for a
        // clearly visible attribution.
        // https://operations.osmfoundation.org/policies/tiles/
        const tileOptions = {
            maxZoom: Number(mapElement.dataset.tileMaxZoom) || 19,
            attribution: mapElement.dataset.tileAttribution,
        };

        // Only the providers that use subdomains need this one.
        if (mapElement.dataset.tileSubdomains) {
            tileOptions.subdomains = mapElement.dataset.tileSubdomains;
        }

        L.tileLayer(mapElement.dataset.tileUrl, tileOptions).addTo(map);

        // The wheel should only zoom the map once the user clicked it,
        // otherwise the page can not be scrolled over the map.
        map.on('click', function (event) {
            selectPosition(event.latlng.lat, event.latlng.lng);
        });

        map.on('focus', function () {
            map.scrollWheelZoom.enable();
        });
        map.on('blur', function () {
            map.scrollWheelZoom.disable();
        });

        if (hasInitial) {
            selectPosition(initialLatitude, initialLongitude, { pan: false });
        } else {
            setCoordinates(null, null);
        }
    }

    // -----------------------------------------------------------------
    // Search
    // -----------------------------------------------------------------

    function hideResults() {
        resultsBox.hidden = true;
        resultsBox.innerHTML = '';
    }

    function renderResults(results) {
        resultsBox.innerHTML = '';

        if (!results.length) {
            hideResults();
            return;
        }

        results.forEach(function (result) {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'search-result';

            const title = document.createElement('span');
            title.className = 'search-result-title';
            title.textContent = result.short_label || result.label;

            const detail = document.createElement('span');
            detail.className = 'search-result-detail';
            detail.textContent = result.label || '';

            item.appendChild(title);
            item.appendChild(detail);

            item.addEventListener('click', function () {
                selectPosition(result.latitude, result.longitude, { zoom: 16 });
                hideResults();
                searchInput.value = result.short_label || result.label;
            });

            resultsBox.appendChild(item);
        });

        resultsBox.hidden = false;
    }

    function runSearch(query) {
        // Abort a search that is still running, it is not needed anymore.
        if (searchController) {
            searchController.abort();
        }
        searchController = new AbortController();

        const token = localStorage.getItem('access');
        const headers = { 'Accept': 'application/json' };
        if (token) {
            headers['Authorization'] = 'Bearer ' + token;
        }

        fetch('/api/geocode/search/?q=' + encodeURIComponent(query), {
            headers: headers,
            signal: searchController.signal,
        })
            .then(function (response) {
                if (response.status === 429) {
                    showStatus('Demasiadas búsquedas, espera un momento.', 'error');
                    return;
                }
                if (!response.ok) {
                    showStatus(
                        'La búsqueda no está disponible. Puedes marcar el spot en el mapa.',
                        'error'
                    );
                    return;
                }
                return response.json();
            })
            .then(function (data) {
                if (!data) {
                    return;
                }
                renderResults(data.results || []);
            })
            .catch(function (error) {
                if (error.name === 'AbortError') {
                    return;
                }
                showStatus(
                    'La búsqueda no está disponible. Puedes marcar el spot en el mapa.',
                    'error'
                );
            });
    }

    /**
     * Run the search the visitor asked for.
     *
     * Nothing is sent while the visitor types: the Nominatim usage
     * policy forbids an auto-complete built on the public API. The
     * request is only sent when the search is confirmed.
     */
    function submitSearch() {
        const query = searchInput.value.trim();

        if (query.length < MIN_QUERY_LENGTH) {
            hideResults();
            showStatus(
                'Escribe al menos ' + MIN_QUERY_LENGTH + ' caracteres para buscar.',
                'error'
            );
            return;
        }

        runSearch(query);
    }

    searchButton.addEventListener('click', submitSearch);

    searchInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            submitSearch();
        } else if (event.key === 'Escape') {
            hideResults();
        }
    });

    document.addEventListener('click', function (event) {
        if (!resultsBox.contains(event.target)
            && event.target !== searchInput) {
            hideResults();
        }
    });

    // -----------------------------------------------------------------
    // Manual coordinates
    // -----------------------------------------------------------------

    function syncManualInputs() {
        const latitude = readCoordinate(latitudeManual);
        const longitude = readCoordinate(longitudeManual);

        if (latitude === null && longitude === null) {
            clearLocation();
            return;
        }

        if (latitude === null || longitude === null) {
            // Half a pair. Nothing is stored, so the spot is published
            // without a location instead of with a wrong one.
            setCoordinates(null, null);
            showStatus(
                'Escribe la latitude y la longitude para tener una ubicación.',
                'error'
            );
            return;
        }

        selectPosition(latitude, longitude);
    }

    latitudeManual.addEventListener('change', syncManualInputs);
    longitudeManual.addEventListener('change', syncManualInputs);

    clearButton.addEventListener('click', function () {
        clearLocation();
        searchInput.value = '';
    });

    // -----------------------------------------------------------------
    // Submit
    // -----------------------------------------------------------------

    function getToken() {
        return localStorage.getItem('access');
    }

    /**
     * The CSRF token of the page. It is sent with every write so the
     * request also works when the visitor happens to have a Django
     * session open.
     */
    function getCsrfToken() {
        const input = form.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : '';
    }

    function showStatus(message, kind) {
        statusBox.textContent = message;
        statusBox.className = 'form-status' + (kind ? ' is-' + kind : '');
    }

    /**
     * The application keeps the access token in the local storage, so
     * the server can not know who is visiting the page. When there is
     * no token the form is disabled and the visitor is asked to log
     * in.
     */
    function requireLogin() {
        if (getToken()) {
            return false;
        }

        const notice = document.getElementById('login-notice');
        if (notice) {
            notice.hidden = false;
        }
        submitButton.disabled = true;
        return true;
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();

        if (requireLogin()) {
            return;
        }

        const name = document.getElementById('name_spot').value.trim();
        if (!name) {
            showStatus('Ponle un nombre a tu spot.', 'error');
            document.getElementById('name_spot').focus();
            return;
        }

        const token = getToken();
        if (!token) {
            showStatus('Tu sesión expiró. Vuelve a iniciar sesión.', 'error');
            return;
        }

        const data = new FormData();

        data.append('name_spot', name);
        data.append('body', document.getElementById('body').value.trim());

        const category = form.querySelector('input[name="category"]:checked');
        if (category) {
            data.append('category', category.value);
        }

        const fileInput = document.getElementById('image_url');
        if (fileInput.files.length) {
            data.append('image_url', fileInput.files[0]);
        }

        // The two coordinates are always sent together. An empty value
        // means "no location", so a spot created without one keeps it
        // empty and an existing spot can have its location removed.
        data.append('latitude', latitudeInput.value.trim());
        data.append('longitude', longitudeInput.value.trim());

        submitButton.disabled = true;
        showStatus('Guardando...');

        const spotId = mapElement.dataset.spotId;
        const url = spotId
            ? '/api/spots/' + spotId + '/'
            : '/api/spots/';
        const method = spotId ? 'PATCH' : 'POST';

        fetch(url, {
            method: method,
            headers: {
                'Authorization': 'Bearer ' + token,
                'X-CSRFToken': getCsrfToken(),
                'Accept': 'application/json',
            },
            body: data,
        })
            .then(function (response) {
                if (response.status === 401 || response.status === 403) {
                    showStatus(
                        spotId
                            ? 'No puedes editar este spot. Solo puedes editar los tuyos.'
                            : 'Tu sesión expiró. Vuelve a iniciar sesión.',
                        'error'
                    );
                    return null;
                }
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result) {
                    return;
                }
                if (!result.ok) {
                    showStatus(formatErrors(result.data), 'error');
                    submitButton.disabled = false;
                    return;
                }
                showStatus('Guardado.', 'success');
                if (document.body.classList.contains('is-embed')
                        && window.top !== window.self) {
                    window.top.location.href = '/#spots';
                } else {
                    window.location.href = '/feed/';
                }
            })
            .catch(function () {
                showStatus(
                    'No se pudo guardar el spot. Inténtalo de nuevo.',
                    'error'
                );
                submitButton.disabled = false;
            });
    });

    /** Turn the DRF error payload into a readable message. */
    function formatErrors(payload) {
        if (!payload) {
            return 'No se pudo guardar el spot.';
        }
        if (typeof payload === 'string') {
            return payload;
        }
        if (payload.detail) {
            return payload.detail;
        }

        const messages = [];
        Object.keys(payload).forEach(function (field) {
            const value = payload[field];
            if (Array.isArray(value)) {
                messages.push(value.join(' '));
            } else {
                messages.push(String(value));
            }
        });

        return messages.join(' ') || 'No se pudo guardar el spot.';
    }

    initMap();
    requireLogin();
})();
