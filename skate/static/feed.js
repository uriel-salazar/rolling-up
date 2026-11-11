/**
 * The feed of the skate spots.
 *
 * The spots are read from the public API of the application. The
 * search uses the `search` parameter the endpoint already understands,
 * so the name and the description of the spots are looked for.
 */
(function () {
    'use strict';

    const grid = document.getElementById('feed-grid');
    const countBox = document.getElementById('feed-count');
    const searchInput = document.getElementById('feed-search');
    const clearButton = document.getElementById('feed-search-clear');
    const locationSearchInput = document.getElementById('feed-location-search');
    const locationSearchResults = document.getElementById('feed-location-results');
    const locationClearButton = document.getElementById('feed-location-clear');

    // The search waits for the visitor to stop typing.
    const SEARCH_DELAY = 400;

    // How many plates are shown while the spots are loaded.
    const SKELETONS = 6;

    // The live results of a selected place. They are never saved.
    const DISCOVERY_LIMIT = 250;
    // The biggest box the discovery endpoint accepts. It has to be the
    // same value the server uses, otherwise the answer is refused.
    const DISCOVERY_MAX_SPAN = 1.5;
    const DISCOVERY_RADIUS = 50000;

    let selectedLocation = null;
    let externalController = null;
    let loadVersion = 0;

    const CATEGORY_LABELS = {
        skatepark: 'Skatepark',
        street: 'Street spot',
        diy: 'DIY spot',
    };

    // ------------------------------------------------------------------
    // The plates
    // ------------------------------------------------------------------

    /**
     * Build the card of a spot.
     *
     * @param {Object} spot A spot of the API.
     * @returns {HTMLElement} The card.
     */
    function buildCard(spot) {
        const card = document.createElement('article');
        card.className = 'spot-card';

        const media = document.createElement('div');
        media.className = 'spot-card-media';

        if (spot.image_url) {
            const image = document.createElement('img');
            image.src = spot.image_url;
            image.alt = spot.name_spot;
            image.loading = 'lazy';
            // The attribution travels with the picture. It is exposed
            // as a tooltip and as metadata so the licence stays with
            // the image without changing the composition of the card.
            if (spot.image_attribution) {
                image.title = String(spot.image_attribution);
                image.dataset.attribution = String(spot.image_attribution);
            }
            if (spot.image_license) {
                image.dataset.license = String(spot.image_license);
            }
            // A picture that does not load leaves the same plate that
            // a spot without a picture gets.
            image.addEventListener('error', function () {
                image.remove();
                if (!media.querySelector('.spot-plate')) {
                    media.appendChild(buildPlate(spot));
                }
            });
            media.appendChild(image);

            // Tap the picture to open the detail modal.
            image.style.cursor = 'pointer';
            image.addEventListener('click', function () {
                openSpotModal(spot);
            });
        } else {
            media.appendChild(buildPlate(spot));
        }

        card.appendChild(media);

        const info = document.createElement('div');
        info.className = 'spot-card-info';

        // The name opens the spot on the map.
        const name = document.createElement('h2');
        name.className = 'spot-card-name';

        const title = document.createElement('a');
        title.className = 'spot-card-title';
        title.href = spot.external && spot.osm_type && spot.osm_id
            ? 'https://www.openstreetmap.org/' + spot.osm_type + '/' + spot.osm_id
            : '/map/?spot=' + encodeURIComponent(spot.id);
        title.textContent = spot.name_spot;

        if (spot.external) {
            title.target = '_blank';
            title.rel = 'noopener noreferrer';
        }

        name.appendChild(title);
        info.appendChild(name);

        const meta = document.createElement('div');
        meta.className = 'spot-card-meta';

        const address = window.RollingUpApi.addressOf(spot);
        if (address) {
            meta.appendChild(buildMeta(iconPin(), address, 'spot-meta-item'));
        }

        meta.appendChild(buildRating(spot));

        if (spot.external) {
            const live = document.createElement('span');
            live.className = 'spot-meta-item spot-source-live';
            live.textContent = 'OSM live';
            meta.appendChild(live);
        }

        if (meta.children.length) {
            info.appendChild(meta);
        }

        const directions = window.RollingUpApi.directionsUrl(spot);
        if (directions) {
            const link = document.createElement('a');
            link.className = 'spot-directions';
            link.href = directions;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = 'Ver en Google Maps';
            info.appendChild(link);
        }

        card.appendChild(info);
        return card;
    }

    /**
     * Build the plate that stands for a spot without a picture.
     *
     * It is not a broken image, it is part of the composition of the
     * page.
     */
    function buildPlate(spot) {
        const plate = document.createElement('div');
        plate.className = 'spot-plate';

        const initial = document.createElement('span');
        initial.className = 'spot-plate-initial';
        initial.setAttribute('aria-hidden', 'true');
        initial.textContent = (spot.name_spot || '?').trim().charAt(0).toUpperCase();

        const label = document.createElement('span');
        label.className = 'spot-plate-label';
        label.textContent = CATEGORY_LABELS[spot.category] || 'Spot';

        plate.appendChild(initial);
        plate.appendChild(label);
        return plate;
    }

    /**
     * Build a piece of information of the card.
     */
    function buildMeta(icon, text, className) {
        const item = document.createElement('span');
        item.className = className;
        item.appendChild(icon);

        const label = document.createElement('span');
        label.textContent = text;
        item.appendChild(label);

        return item;
    }

    /**
     * Build the rating of a spot.
     *
     * A spot without a rating is not rated yet, it does not have a
     * score of zero.
     */
    function buildRating(spot) {
        const hasRating = spot.rating !== null && spot.rating !== undefined;

        if (!hasRating) {
            const item = document.createElement('span');
            item.className = 'spot-meta-item spot-rating-empty';
            item.textContent = 'Not rated yet';
            return item;
        }

        const score = Number(spot.rating);
        const count = spot.rating_count || 0;

        const item = document.createElement('span');
        item.className = 'spot-meta-item spot-rating';

        // The stars with the average, filled in part when the average
        // is not a whole number.
        if (window.RollingUpRating) {
            item.appendChild(
                window.RollingUpRating.createReadOnly(score, count, { size: 'small' })
            );
            return item;
        }

        item.appendChild(iconStar());

        const label = document.createElement('span');
        label.textContent = count
            ? score.toFixed(1) + ' (' + count + ')'
            : score.toFixed(1);
        item.appendChild(label);

        return item;
    }
    /** The icon of the place. */
    function iconPin() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute(
            'd',
            'M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z'
        );
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', '12');
        circle.setAttribute('cy', '10');
        circle.setAttribute('r', '2.5');

        svg.appendChild(path);
        svg.appendChild(circle);
        return svg;
    }

    /** The icon of the rating. */
    function iconStar() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        svg.setAttribute('fill', 'currentColor');
        svg.setAttribute('stroke', 'none');

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute(
            'd',
            'M12 3.2l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.3l5.8-.8z'
        );
        svg.appendChild(path);
        return svg;
    }

    // ------------------------------------------------------------------
    // The live discovery
    // ------------------------------------------------------------------

    /** The stable identity of a spot, also for live OSM results. */
    function spotIdentity(spot) {
        if (spot && spot.osm_type && spot.osm_id) {
            return 'osm:' + spot.osm_type + ':' + spot.osm_id;
        }
        return 'spot:' + spot.id;
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

    /** The selected place as a box or as a radius. */
    function selectedArea() {
        if (!selectedLocation) {
            return null;
        }

        const box = selectedLocation.bounding_box;
        if (box) {
            const south = Number(box.south);
            const west = Number(box.west);
            const north = Number(box.north);
            const east = Number(box.east);
            if ([south, west, north, east].every(Number.isFinite)
                && south < north && west < east) {
                return { type: 'bbox', south, west, north, east };
            }
        }

        const latitude = Number(selectedLocation.latitude);
        const longitude = Number(selectedLocation.longitude);
        if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
            return {
                type: 'radius',
                latitude,
                longitude,
                radius: DISCOVERY_RADIUS,
            };
        }

        return null;
    }

    /** The distance in metres between two points. */
    function distanceInMetres(latitude, longitude, otherLatitude, otherLongitude) {
        const radius = 6371000;
        const toRadians = Math.PI / 180;
        const dLatitude = (otherLatitude - latitude) * toRadians;
        const dLongitude = (otherLongitude - longitude) * toRadians;
        const a = Math.sin(dLatitude / 2) * Math.sin(dLatitude / 2)
            + Math.cos(latitude * toRadians)
            * Math.cos(otherLatitude * toRadians)
            * Math.sin(dLongitude / 2) * Math.sin(dLongitude / 2);
        return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    /** Whether a registered spot belongs to the selected place. */
    function isInsideSelectedArea(spot) {
        const area = selectedArea();
        if (!area) {
            return true;
        }

        if (spot.latitude === null || spot.latitude === undefined
            || spot.longitude === null || spot.longitude === undefined
            || spot.latitude === '' || spot.longitude === '') {
            return false;
        }

        const latitude = Number(spot.latitude);
        const longitude = Number(spot.longitude);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
            return false;
        }

        if (area.type === 'bbox') {
            return latitude >= area.south && latitude <= area.north
                && longitude >= area.west && longitude <= area.east;
        }

        return distanceInMetres(
            area.latitude,
            area.longitude,
            latitude,
            longitude
        ) <= area.radius;
    }

    /** The discovery endpoint that fits the selected place. */
    function externalUrl() {
        const area = selectedArea();
        if (!area) {
            return '';
        }

        if (area.type === 'bbox'
            && area.north - area.south <= DISCOVERY_MAX_SPAN
            && area.east - area.west <= DISCOVERY_MAX_SPAN) {
            const query = new URLSearchParams({
                south: area.south.toFixed(6),
                west: area.west.toFixed(6),
                north: area.north.toFixed(6),
                east: area.east.toFixed(6),
                limit: String(DISCOVERY_LIMIT),
            });
            return '/api/spots/viewport/?' + query.toString();
        }

        let latitude;
        let longitude;
        if (area.type === 'bbox') {
            latitude = (area.south + area.north) / 2;
            longitude = (area.west + area.east) / 2;
        } else {
            latitude = area.latitude;
            longitude = area.longitude;
        }

        const query = new URLSearchParams({
            lat: latitude.toFixed(6),
            lon: longitude.toFixed(6),
            radius: String(DISCOVERY_RADIUS),
            limit: String(DISCOVERY_LIMIT),
        });
        return '/api/spots/nearby/?' + query.toString();
    }

    /** Read the live skateparks of the selected place. */
    async function fetchExternal() {
        const url = externalUrl();
        if (!url) {
            return [];
        }

        if (externalController) {
            externalController.abort();
        }
        externalController = new AbortController();

        try {
            const response = await fetch(url, {
                headers: { 'Accept': 'application/json' },
                signal: externalController.signal,
            });
            if (!response.ok) {
                throw new Error('The discovery API answered with HTTP '
                    + response.status);
            }
            const data = await response.json();
            return Array.isArray(data.results) ? data.results : [];
        } catch (error) {
            if (error.name === 'AbortError') {
                return [];
            }
            console.warn('The live skateparks could not be loaded:', error);
            return [];
        }
    }

    // ------------------------------------------------------------------
    // The states
    // ------------------------------------------------------------------

    /** Show the plates that stand for the spots that are loading. */
    function showSkeletons() {
        grid.innerHTML = '';
        grid.setAttribute('aria-busy', 'true');

        for (let index = 0; index < SKELETONS; index += 1) {
            const skeleton = document.createElement('div');
            skeleton.className = 'feed-skeleton';

            const media = document.createElement('div');
            media.className = 'feed-skeleton-media';

            const line = document.createElement('div');
            line.className = 'feed-skeleton-line';

            const short = document.createElement('div');
            short.className = 'feed-skeleton-line short';

            skeleton.appendChild(media);
            skeleton.appendChild(line);
            skeleton.appendChild(short);
            grid.appendChild(skeleton);
        }
    }

    /** Show a message instead of the spots. */
    function showMessage(title, text, isError) {
        grid.innerHTML = '';
        grid.setAttribute('aria-busy', 'false');

        const message = document.createElement('div');
        message.className = 'feed-message' + (isError ? ' is-error' : '');

        const heading = document.createElement('h2');
        heading.className = 'feed-message-title';
        heading.textContent = title;

        const paragraph = document.createElement('p');
        paragraph.className = 'feed-message-text';
        paragraph.textContent = text;

        message.appendChild(heading);
        message.appendChild(paragraph);
        grid.appendChild(message);
    }

    // ------------------------------------------------------------------
    // The feed
    // ------------------------------------------------------------------

    /** Read the spots and draw them. */
    async function loadSpots() {
        const query = searchInput.value.trim();
        const version = ++loadVersion;

        showSkeletons();
        countBox.textContent = '';

        try {
            const externalPromise = selectedLocation
                ? fetchExternal()
                : Promise.resolve([]);
            const embedded = document.body.classList.contains('is-embed');
            const data = await window.RollingUpApi.fetchSpots(
                { search: query },
                { limit: embedded ? 9 : 24, maxPages: 10 }
            );

            if (version !== loadVersion) {
                return;
            }

            const external = await externalPromise;
            if (version !== loadVersion) {
                return;
            }

            const registered = selectedLocation
                ? data.results.filter(isInsideSelectedArea)
                : data.results;
            const results = mergeSpots(registered, external).filter(function (spot) {
                if (!query || !spot.external) {
                    return true;
                }
                const name = String(spot.name_spot || '').toLowerCase();
                const body = String(spot.body || '').toLowerCase();
                return name.indexOf(query.toLowerCase()) !== -1
                    || body.indexOf(query.toLowerCase()) !== -1;
            });

            // The spots with a picture come first, the order of the
            // rest is the order of the answer of the API.
            const withImage = [];
            const withoutImage = [];
            results.forEach(function (spot) {
                if (spot.image_url) {
                    withImage.push(spot);
                } else {
                    withoutImage.push(spot);
                }
            });
            const ordered = withImage.concat(withoutImage);

            grid.setAttribute('aria-busy', 'false');

            if (!results.length) {
                countBox.textContent = '';
                const where = selectedLocation
                    ? ' near ' + (selectedLocation.short_label
                        || selectedLocation.label || 'this place')
                    : '';
                showMessage(
                    'Nothing found',
                    query
                        ? 'No spot matches that search. Try another word.'
                        : selectedLocation
                            ? 'No skatepark was found' + where
                                + '. Try another place.'
                            : 'There is no spot yet. Be the first to add one.',
                    false
                );
                return;
            }

            countBox.textContent = results.length === 1
                ? '1 spot'
                : results.length + ' spots';

            grid.innerHTML = '';
            ordered.forEach(function (spot) {
                grid.appendChild(buildCard(spot));
            });
        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }
            showMessage(
                'The spots did not load',
                'Check the connection and try again.',
                true
            );
        }
    }

    // ------------------------------------------------------------------
    // The search
    // ------------------------------------------------------------------

    let searchTimer = null;

    searchInput.addEventListener('input', function () {
        window.clearTimeout(searchTimer);
        clearButton.hidden = searchInput.value === '';

        searchTimer = window.setTimeout(loadSpots, SEARCH_DELAY);
    });

    searchInput.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            searchInput.value = '';
            clearButton.hidden = true;
            loadSpots();
        }
    });

    clearButton.addEventListener('click', function () {
        searchInput.value = '';
        clearButton.hidden = true;
        loadSpots();
        searchInput.focus();
    });

    // ------------------------------------------------------------------
    // The location search
    // ------------------------------------------------------------------

    function setupLocationSearch() {
        if (!window.RollingUpLocationSearch || !locationSearchInput
            || !locationSearchResults) {
            return;
        }

        window.RollingUpLocationSearch.create({
            input: locationSearchInput,
            results: locationSearchResults,
            clearButton: locationClearButton,
            onSelect: function (place) {
                selectedLocation = place;
                loadSpots();
            },
            onClear: function () {
                selectedLocation = null;
                loadSpots();
            },
        });
    }

    // ------------------------------------------------------------------
    // Spot detail modal
    // ------------------------------------------------------------------

    const modal = document.getElementById('spot-modal');
    const modalClose = document.getElementById('spot-modal-close');
    const modalImage = document.getElementById('spot-modal-image');
    const modalName = document.getElementById('spot-modal-name');
    const modalCategory = document.getElementById('spot-modal-category');
    const modalAddress = document.getElementById('spot-modal-address');
    const modalDirections = document.getElementById('spot-modal-directions');
    const modalBody = document.getElementById('spot-modal-body');

    /** Open the detail modal of a spot. */
    function openSpotModal(spot) {
        const address = window.RollingUpApi.addressOf(spot);

        modalImage.src = spot.image_url || '';
        modalImage.alt = spot.name_spot || 'Spot';
        modalImage.hidden = !spot.image_url;

        modalName.textContent = spot.name_spot || 'Spot';
        modalCategory.textContent = CATEGORY_LABELS[spot.category] || 'Spot';
        modalAddress.textContent = address || 'Sin dirección';

        const directions = window.RollingUpApi.directionsUrl(spot);
        if (directions) {
            modalDirections.href = directions;
            modalDirections.hidden = false;
        } else {
            modalDirections.hidden = true;
        }

        modalBody.textContent = spot.body ? String(spot.body) : '';
        modalBody.hidden = !spot.body;

        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
    }

    /** Close the detail modal. */
    function closeSpotModal() {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    modalClose.addEventListener('click', closeSpotModal);

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !modal.hidden) {
            closeSpotModal();
        }
    });

    // ------------------------------------------------------------------

    setupLocationSearch();
    loadSpots();
})();
