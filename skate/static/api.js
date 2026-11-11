/**
 * The client of the spots API.
 *
 * Every page of the application reads the spots through this module, so
 * the way the answer of the API is read and the way the pages are
 * handled stays in one place.
 */
(function (global) {
    'use strict';

    const SPOTS_URL = '/api/spots/';

    // The API answers with pages. The feed follows them until it has
    // enough spots or the end is reached.
    const DEFAULT_LIMIT = 24;
    const MAX_PAGES = 10;

    // Only one request is sent at a time. A new one cancels the one
    // that is still running.
    let controller = null;

    /**
     * Read the spots from the API.
     *
     * @param {Object} params Query parameters, for example
     *                       `{ search: 'oasis' }`. They are the ones the
     *                       endpoint already understands.
     * @param {Object} options `{ limit, maxPages }`.
     * @returns {Promise<Object>} `{ results, count }`.
     */
    async function fetchSpots(params, options) {
        const settings = options || {};
        const limit = settings.limit || DEFAULT_LIMIT;
        const maxPages = settings.maxPages || MAX_PAGES;

        if (controller) {
            controller.abort();
        }
        controller = new AbortController();

        const query = new URLSearchParams(params || {});
        query.set('limit', String(limit));

        let url = SPOTS_URL + '?' + query.toString();
        let results = [];
        let count = 0;
        let pages = 0;

        while (url && pages < maxPages) {
            const response = await fetch(url, {
                headers: { 'Accept': 'application/json' },
                signal: controller.signal,
            });

            if (!response.ok) {
                throw new Error('The API answered with HTTP ' + response.status);
            }

            const data = await response.json();
            const page = Array.isArray(data.results) ? data.results : [];

            results = results.concat(page);
            count = typeof data.count === 'number' ? data.count : results.length;
            url = data.next;
            pages += 1;

            if (!data.next) {
                break;
            }
        }

        return { results: results, count: count };
    }

    /**
     * Return the location of a spot, when the data of the API has it.
     *
     * The API does not have a place field, so the address is read from
     * the tags of OpenStreetMap when the spot comes from there.
     *
     * @param {Object} spot A spot of the API.
     * @returns {string} The address, empty when there is none.
     */
    function addressOf(spot) {
        // The API already resolves the address from Google Places or
        // from the OpenStreetMap tags. The tags stay as a fallback for
        // an older cached answer.
        if (spot.address) {
            return String(spot.address);
        }

        const metadata = spot.osm_metadata || {};
        const tags = metadata.tags || {};

        const parts = [
            tags['addr:housenumber'],
            tags['addr:street'],
            tags['addr:suburb'],
            tags['addr:neighbourhood'],
            tags['addr:city'],
        ].filter(Boolean);

        return parts.join(', ');
    }

    /**
     * Return the url that opens Google Maps with the directions to a
     * spot.
     *
     * @param {Object} spot A spot of the API.
     * @returns {string} The url, empty when the spot has no place.
     */
    function directionsUrl(spot) {
        const latitude = spot.latitude;
        const longitude = spot.longitude;
        const address = addressOf(spot);

        let destination = '';

        if (latitude !== null && latitude !== undefined && latitude !== ''
            && longitude !== null && longitude !== undefined && longitude !== '') {
            destination = latitude + ',' + longitude;
        } else if (address) {
            destination = address;
        }

        if (!destination) {
            return '';
        }

        return 'https://www.google.com/maps/dir/?api=1&destination='
            + encodeURIComponent(destination);
    }

    global.RollingUpApi = {
        fetchSpots: fetchSpots,
        addressOf: addressOf,
        directionsUrl: directionsUrl,
        SPOTS_URL: SPOTS_URL,
    };
})(window);
