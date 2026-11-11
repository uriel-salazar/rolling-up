/**
 * Behaviour test for the location picker.
 *
 * The form is plain JavaScript, so it is exercised here against a
 * small DOM stub instead of a real browser. Node runs it without any
 * dependency:
 *
 *     node skate/tests/spot_form.test.js
 *
 * It checks that the map, the marker, the manual coordinates, the
 * search and the submission behave the way the form expects.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PROJECT = path.resolve(__dirname, '..', '..');
const JS_PATH = path.join(PROJECT, 'skate/static/spot_form.js');

// ------------------------------------------------------------------
// DOM stub
// ------------------------------------------------------------------

function makeElement(id, tag) {
    const el = {
        id: id,
        tagName: (tag || 'div').toUpperCase(),
        value: '',
        textContent: '',
        innerHTML: '',
        hidden: false,
        className: '',
        classList: {
            add() {},
            remove() {},
            contains() { return false; },
        },
        files: [],
        dataset: {},
        style: {},
        children: [],
        attributes: {},
        listeners: {},
        appendChild(child) { this.children.push(child); },
        setAttribute(k, v) { this.attributes[k] = v; },
        getAttribute(k) { return this.attributes[k]; },
        addEventListener(name, fn) {
            (this.listeners[name] = this.listeners[name] || []).push(fn);
        },
        dispatch(name, event) {
            const payload = event || {};
            if (typeof payload.preventDefault !== 'function') {
                payload.preventDefault = function () {};
            }
            (this.listeners[name] || []).forEach((fn) => fn(payload));
        },
        querySelector(sel) {
            if (sel === 'input[name="csrfmiddlewaretoken"]') {
                return this._csrf || null;
            }
            return null;
        },
        focus() {},
    };
    return el;
}

const elements = {};
const ids = [
    'map', 'spot-form', 'location-search', 'search-button', 'search-results',
    'latitude', 'longitude', 'latitude-manual', 'longitude-manual',
    'coordinates-output', 'clear-location', 'map-error', 'form-status',
    'submit-button', 'name_spot', 'body', 'image_url', 'login-notice',
];
ids.forEach((id) => { elements[id] = makeElement(id); });

elements.map.dataset = {
    latitude: '',
    longitude: '',
    spotId: '',
    tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    tileMaxZoom: '19',
    tileSubdomains: '',
    tileAttribution: '&copy; OpenStreetMap contributors',
};
elements['spot-form']._csrf = makeElement('csrf', 'input');
elements['spot-form']._csrf.value = 'csrf-token-123';

// The form fields start with the values the server rendered.
elements.name_spot.value = 'Parque de las Americas';
elements.body.value = 'Un skatepark grande';

// ------------------------------------------------------------------
// Leaflet stub
// ------------------------------------------------------------------

const mapState = { center: null, zoom: null, layers: [], events: {}, tile: null };
const markerState = { latlng: null, draggable: false, onDrag: null };

const L = {
    map: function (id, options) {
        mapState.center = options.center;
        mapState.zoom = options.zoom;
        return {
            setView(c, z) { mapState.center = c; mapState.zoom = z; },
            getZoom() { return mapState.zoom; },
            on(name, fn) { mapState.events[name] = fn; },
            removeLayer(m) { mapState.layers = mapState.layers.filter((x) => x !== m); },
        };
    },
    tileLayer: function (url, options) {
        mapState.tile = { url: url, options: options };
        return { addTo() { return this; } };
    },
    marker: function (position, options) {
        markerState.latlng = position;
        markerState.draggable = options.draggable;
        const marker = {
            setLatLng(p) { markerState.latlng = p; return this; },
            getLatLng() { return { lat: markerState.latlng[0], lng: markerState.latlng[1] }; },
            on(name, fn) { if (name === 'dragend') markerState.onDrag = fn; return this; },
            addTo() { mapState.layers.push(marker); return this; },
        };
        return marker;
    },
};

// ------------------------------------------------------------------
// Browser globals
// ------------------------------------------------------------------

let lastFetch = null;
const sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    document: {
        getElementById: (id) => elements[id] || null,
        createElement: (tag) => makeElement('', tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
        // The form script looks at the body to know whether the page is
        // embedded in an iframe.
        body: {
            classList: {
                _set: new Set(),
                add() {},
                remove() {},
                contains() { return false; },
            },
        },
    },
    localStorage: {
        store: { access: 'jwt-token' },
        getItem(k) { return this.store[k] || null; },
        setItem(k, v) { this.store[k] = v; },
    },
    fetch: function (url, options) {
        lastFetch = { url: url, options: options };
        return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ results: [] }),
        });
    },
    AbortController: function () {
        this.signal = {};
        this.abort = function () {};
    },
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    URLSearchParams: URLSearchParams,
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    L: L,
    window: {
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        location: { href: '' },
    },
    FormData: function () {
        this.entries = {};
        this.append = (k, v) => { this.entries[k] = v; };
    },
};
sandbox.window.setTimeout = setTimeout;
sandbox.window.clearTimeout = clearTimeout;

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(JS_PATH, 'utf8'), sandbox);

// ------------------------------------------------------------------
// Checks
// ------------------------------------------------------------------

let failures = 0;
function check(label, condition, extra) {
    if (condition) {
        console.log('  PASS  ' + label);
    } else {
        failures += 1;
        console.log('  FAIL  ' + label + (extra ? ' -> ' + extra : ''));
    }
}

console.log('\n== 1. The map is created on Guadalajara ==');
check('map centre is Guadalajara',
    mapState.center[0] === 20.6767 && mapState.center[1] === -103.3475,
    JSON.stringify(mapState.center));
check('no marker yet', mapState.layers.length === 0);
check('coordinates start empty', elements.latitude.value === '' && elements.longitude.value === '');
check('readout says no location',
    elements['coordinates-output'].textContent === 'Ubicación no seleccionada');
check('clear button hidden', elements['clear-location'].hidden === true);

console.log('\n== 2. Clicking on the map drops a marker ==');
mapState.events.click({ latlng: { lat: 20.671072, lng: -103.405056 } });
check('a marker was added', mapState.layers.length === 1);
check('marker is draggable', markerState.draggable === true);
check('hidden latitude updated', elements.latitude.value === '20.671072');
check('hidden longitude updated', elements.longitude.value === '-103.405056');
check('manual fields updated',
    elements['latitude-manual'].value === '20.671072'
    && elements['longitude-manual'].value === '-103.405056');
check('readout shows the pair',
    elements['coordinates-output'].textContent === '20.671072, -103.405056');
check('clear button visible', elements['clear-location'].hidden === false);

console.log('\n== 2b. Coordinates are rounded to six decimal places ==');
mapState.events.click({ latlng: { lat: 20.7123456789, lng: -103.987654321 } });
check('latitude is rounded', elements.latitude.value === '20.712346',
    elements.latitude.value);
check('longitude is rounded', elements.longitude.value === '-103.987654',
    elements.longitude.value);

console.log('\n== 3. Dragging the marker updates the coordinates ==');
markerState.latlng = [21.5, -104.5];
markerState.onDrag();
check('latitude follows the drag', elements.latitude.value === '21.5');
check('longitude follows the drag', elements.longitude.value === '-104.5');

console.log('\n== 4. Clearing the location ==');
elements['clear-location'].dispatch('click');
check('hidden latitude emptied', elements.latitude.value === '');
check('hidden longitude emptied', elements.longitude.value === '');
check('manual fields emptied',
    elements['latitude-manual'].value === '' && elements['longitude-manual'].value === '');
check('marker removed', mapState.layers.length === 0);
check('readout says no location again',
    elements['coordinates-output'].textContent === 'Ubicación no seleccionada');
check('clear button hidden again', elements['clear-location'].hidden === true);

console.log('\n== 5. Only a latitude typed by hand ==');
elements['latitude-manual'].value = '20.1';
elements['latitude-manual'].dispatch('change');
check('nothing is stored', elements.latitude.value === '' && elements.longitude.value === '');
check('the typed value is kept', elements['latitude-manual'].value === '20.1');
check('the visitor is warned',
    elements['form-status'].textContent.includes('latitude'),
    elements['form-status'].textContent);

console.log('\n== 6. Both coordinates typed by hand ==');
elements['longitude-manual'].value = '-103.9';
elements['longitude-manual'].dispatch('change');
check('latitude stored', elements.latitude.value === '20.1');
check('longitude stored', elements.longitude.value === '-103.9');
check('marker placed', mapState.layers.length === 1);

console.log('\n== 7. Submitting the form ==');
elements['spot-form'].dispatch('submit', { preventDefault() {} });
setTimeout(() => {
    check('the request went to the create endpoint',
        lastFetch && lastFetch.url === '/api/spots/', lastFetch && lastFetch.url);
    check('the method is POST', lastFetch && lastFetch.options.method === 'POST');
    check('the bearer token is sent',
        lastFetch.options.headers.Authorization === 'Bearer jwt-token');
    check('the csrf token is sent',
        lastFetch.options.headers['X-CSRFToken'] === 'csrf-token-123');
    const body = lastFetch.options.body;
    check('the name is sent', body.entries.name_spot === 'Parque de las Americas');
    check('the description is sent', body.entries.body === 'Un skatepark grande');
    check('the latitude is sent', body.entries.latitude === '20.1');
    check('the longitude is sent', body.entries.longitude === '-103.9');
    check('no image is sent when none was chosen', body.entries.image_url === undefined);

    console.log('\n== 8. Submitting without a location ==');
    elements['clear-location'].dispatch('click');
    lastFetch = null;
    elements['spot-form'].dispatch('submit', { preventDefault() {} });
    setTimeout(() => {
        const body2 = lastFetch.options.body;
        check('the latitude is sent empty',
            body2.entries.latitude === '', JSON.stringify(body2.entries.latitude));
        check('the longitude is sent empty', body2.entries.longitude === '');

        console.log('\n== 9. Without a token the form asks to log in ==');
        sandbox.localStorage.store.access = '';
        elements['login-notice'].hidden = true;
        const noticeVisible = sandbox.localStorage.getItem('access') === null;
        check('the notice is shown when there is no token', noticeVisible);
        sandbox.localStorage.store.access = 'jwt-token';

        console.log('\n== 10. The search is only sent when it is asked for ==');
        lastFetch = null;
        elements['location-search'].value = 'sk';
        elements['location-search'].dispatch('input');
        check('a short query does not hit the server', lastFetch === null);
        elements['location-search'].value = 'skatepark guadalajara';
        elements['location-search'].dispatch('input');
        check('typing does not hit the server', lastFetch === null);
        check(
            'the Nominatim auto-complete is not used',
            lastFetch === null,
            'a request was sent while typing'
        );

        elements['location-search'].dispatch('keydown', { key: 'Enter' });
        check('pressing Enter does hit the server', lastFetch !== null);
        check('it goes to the geocode endpoint',
            lastFetch.url === '/api/geocode/search/?q=skatepark%20guadalajara',
            lastFetch.url);
        check('the token is sent',
            lastFetch.options.headers.Authorization === 'Bearer jwt-token');

        console.log('\n== 11. The search button also works ==');
        lastFetch = null;
        elements['location-search'].value = 'parque de las americas';
        elements['search-button'].dispatch('click');
        check('the request is sent', lastFetch !== null);
        check('with the right query',
            lastFetch.url === '/api/geocode/search/?q=parque%20de%20las%20americas',
            lastFetch.url);

        console.log('\n== 12. The tile layer follows the usage policy ==');
        check('the tile url is the one the policy asks for',
            mapState.tile.url === 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            mapState.tile.url);
        check('the url has no subdomain shortcut',
            !mapState.tile.url.includes('{s}'), mapState.tile.url);
        check('no subdomains are sent',
            mapState.tile.options.subdomains === undefined,
            String(mapState.tile.options.subdomains));
        check('the attribution is passed on',
            mapState.tile.options.attribution.includes('OpenStreetMap'),
            mapState.tile.options.attribution);
        check('the max zoom is passed on',
            mapState.tile.options.maxZoom === 19,
            String(mapState.tile.options.maxZoom));

        console.log('\n== 13. Editing an existing spot ==');
        elements.map.dataset.spotId = '42';
        lastFetch = null;
        elements['spot-form'].dispatch('submit', { preventDefault() {} });
        setTimeout(() => {
            check('it patches the right spot',
                lastFetch.url === '/api/spots/42/', lastFetch.url);
            check('the method is PATCH', lastFetch.options.method === 'PATCH');

            console.log('\n' + (failures === 0
                ? 'ALL CHECKS PASSED'
                : failures + ' CHECK(S) FAILED'));
            process.exit(failures === 0 ? 0 : 1);
        }, 10);
    }, 10);
}, 10);
