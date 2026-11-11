/**
 * Behaviour test for the map of the spots.
 *
 * The map is plain JavaScript, so it is exercised here against a small
 * DOM stub instead of a real browser. Node runs it without any
 * dependency:
 *
 *     node skate/tests/map.test.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PROJECT = path.resolve(__dirname, '..', '..');
const JS_PATH = path.join(PROJECT, 'skate/static/map.js');

// ------------------------------------------------------------------
// DOM stub
// ------------------------------------------------------------------

function makeElement(id, tag) {
    const element = {
        id: id,
        tagName: (tag || 'div').toUpperCase(),
        value: '',
        textContent: '',
        innerHTML: '',
        hidden: false,
        className: '',
        classList: {
            _set: new Set(),
            _owner: null,
            add(name) { this._set.add(name); },
            remove(name) { this._set.delete(name); },
            contains(name) {
                if (this._set.has(name)) { return true; }
                const owner = this._owner;
                if (owner && typeof owner.className === 'string') {
                    return owner.className.split(/\s+/).indexOf(name) !== -1;
                }
                return false;
            },
            toggle(name, force) {
                const has = this._set.has(name);
                const want = force === undefined ? !has : force;
                if (want) { this._set.add(name); } else { this._set.delete(name); }
                return want;
            },
        },
        dataset: {},
        style: {},
        children: [],
        listeners: {},
        querySelectorAll(sel) {
            // The map asks for the entries of the list.
            if (sel === '.spot-item') {
                return this.children.filter((child) => child.classList
                    && child.classList.contains('spot-item'));
            }
            return [];
        },
        querySelector(sel) { return null; },
        appendChild(child) { this.children.push(child); },
        addEventListener(name, fn) {
            (this.listeners[name] = this.listeners[name] || []).push(fn);
        },
        dispatch(name, event) {
            const payload = event || {};
            if (typeof payload.preventDefault !== 'function') {
                payload.preventDefault = function () {};
            }
            if (typeof payload.stopPropagation !== 'function') {
                payload.stopPropagation = function () {};
            }
            (this.listeners[name] || []).forEach((fn) => fn(payload));
        },
        scrollIntoView() {},
        focus() {},
        removeAttribute() {},
        setAttribute(k, v) { this.dataset[k] = v; },
    };

    element.classList._owner = element;
    return element;
}

const elements = {};
[
    'map', 'spot-search', 'clear-search', 'map-filters', 'map-status',
    'spot-list', 'spot-preview', 'preview-name', 'preview-category',
    'preview-rating', 'preview-source', 'preview-body', 'preview-link',
    'preview-close', 'map-sidebar', 'sidebar-toggle', 'sheet-handle',
    'sheet-handle-text',
].forEach((id) => { elements[id] = makeElement(id); });

elements.map.dataset = {
    tileUrl: '/tiles/{z}/{x}/{y}{r}.png',
    tileMaxZoom: '18',
    tileSubdomains: '',
    tileAttribution: '&copy; OpenStreetMap contributors',
    defaultLat: '20.6767',
    defaultLon: '-103.3475',
    defaultZoom: '13',
};

// The checkboxes of the filters.
const filterBoxes = {
    category: [
        { value: 'skatepark', checked: true },
        { value: 'street', checked: true },
        { value: 'diy', checked: true },
    ],
    source: [
        { value: 'osm', checked: true },
        { value: 'community', checked: true },
    ],
};

// ------------------------------------------------------------------
// Leaflet stub
// ------------------------------------------------------------------

const mapState = { center: null, zoom: null, markers: [], views: [], tile: null, invalidated: 0 };
const layerState = { markers: [], cleared: 0 };
const controlState = { controls: [] };
const icons = [];

function makeMarker(position, options) {
    const marker = {
        position: position,
        options: options,
        icon: options.icon,
        title: options.title,
        listeners: {},
        on(name, fn) { this.listeners[name] = fn; return this; },
        addTo(target) {
            if (target && target.markers) {
                target.markers.push(this);
            } else {
                mapState.markers.push(this);
            }
            return this;
        },
        remove() {},
        setIcon(icon) { this.icon = icon; },
        getLatLng() { return { lat: this.position[0], lng: this.position[1] }; },
        click() { this.listeners.click && this.listeners.click({}); },
    };
    return marker;
}

const L = {
    map: function (id, options) {
        mapState.center = options.center;
        mapState.zoom = options.zoom;
        return {
            setView(c, z) { mapState.center = c; mapState.zoom = z; mapState.views.push([c, z]); },
            getZoom() { return mapState.zoom; },
            on() {},
            removeLayer() {},
            addLayer() {},
            invalidateSize() { mapState.invalidated += 1; },
        };
    },
    tileLayer: function (url, options) {
        mapState.tile = { url: url, options: options };
        return { addTo() { return this; } };
    },
    layerGroup: function () {
        const layer = {
            markers: [],
            addTo() { return this; },
            clearLayers() { layer.markers = []; layerState.markers = layer.markers; layerState.cleared += 1; },
            addLayer(m) { layer.markers.push(m); layerState.markers = layer.markers; },
        };
        layerState.markers = layer.markers;
        return layer;
    },
    marker: makeMarker,
    divIcon: function (options) {
        icons.push(options);
        return options;
    },
    circle: function () {
        return { addTo() { return this; } };
    },
    control: function (options) {
        const control = {
            options: options,
            onAdd() {
                const container = { appendChild() {}, children: [] };
                control.container = container;
                return container;
            },
            addTo() {
                if (this.onAdd) {
                    this.container = this.onAdd();
                }
                return this;
            },
        };
        controlState.controls.push(control);
        return control;
    },
    controlOptions: {},
    DomUtil: {
        create(tag, className, parent) {
            const element = makeElement('', tag);
            element.className = className || '';
            if (parent) {
                parent.appendChild(element);
            }
            return element;
        },
        stopPropagation() {},
    },
    DomEvent: { stopPropagation() {} },
};

// The named controls of Leaflet.
L.control.zoom = function () { return L.control({}); };
L.control.scale = function () { return L.control({}); };

// ------------------------------------------------------------------
// Browser globals
// ------------------------------------------------------------------

const SPOTS = [
    { id: 1, name_spot: 'Skatepark Oasis', body: 'Grande', latitude: '20.706324',
      longitude: '-103.363065', category: 'skatepark', source: 'osm',
      rating: 4.5, rating_count: 2 },
    { id: 2, name_spot: 'Plaza del centro', body: 'Calle', latitude: '20.671073',
      longitude: '-103.405057', category: 'street', source: 'community',
      rating: null, rating_count: 0 },
    { id: 3, name_spot: 'DIY del parque', body: null, latitude: '20.650534',
      longitude: '-103.367389', category: 'diy', source: 'community',
      rating: null, rating_count: 0 },
    { id: 4, name_spot: 'Sin ubicación', body: null, latitude: null,
      longitude: null, category: 'street', source: 'community',
      rating: null, rating_count: 0 },
];

let fetchCalls = [];
let fetchPages = [
    { count: 4, next: null, results: SPOTS },
];

const sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    document: {
        getElementById: (id) => elements[id] || null,
        createElement: (tag) => makeElement('', tag),
        querySelectorAll: (sel) => {
            const match = sel.match(/input\[name="(\w+)"\]:checked/);
            if (!match) {
                return [];
            }
            return filterBoxes[match[1]].filter((box) => box.checked);
        },
        addEventListener: () => {},
    },
    window: {
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        requestAnimationFrame: (fn) => setTimeout(fn, 0),
        location: { href: '' },
    },
    URLSearchParams: URLSearchParams,
    AbortController: function () { this.signal = {}; this.abort = function () {}; },
    L: L,
    fetch: function (url) {
        fetchCalls.push(url);
        const page = fetchPages.shift() || { count: 0, next: null, results: [] };
        return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(page),
        });
    },
    navigator: {
        geolocation: null,
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

function lastCall() {
    return fetchCalls[fetchCalls.length - 1];
}

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

(async function run() {
    await wait(20);

    console.log('\n== 1. The map is created ==');
    check('it is centred on the default place',
        mapState.center[0] === 20.6767 && mapState.center[1] === -103.3475,
        JSON.stringify(mapState.center));
    check('it uses the zoom of the page', mapState.zoom === 13, String(mapState.zoom));
    check('it asks the proxy for the tiles',
        mapState.tile.url === '/tiles/{z}/{x}/{y}{r}.png', mapState.tile.url);
    check('the attribution is passed on',
        mapState.tile.options.attribution.includes('OpenStreetMap'));
    check('no subdomain is sent',
        mapState.tile.options.subdomains === undefined);
    check('the map measures itself again once the page settles',
        mapState.invalidated > 0, String(mapState.invalidated));

    console.log('\n== 2. The spots are read from the API ==');
    check('the API was asked', fetchCalls.length === 1, String(fetchCalls.length));
    check('it is the public endpoint', lastCall().startsWith('/api/spots/?'));
    check('it asks for pages of 50', lastCall().includes('limit=50'), lastCall());

    console.log('\n== 3. Only the spots with coordinates are on the map ==');
    check('three markers were drawn', layerState.markers.length === 3,
        String(layerState.markers.length));
    check('the spot without a place was left out',
        !layerState.markers.some((m) => m.title === 'Sin ubicación'));
    check('the spot without a place is not in the list',
        elements['spot-list'].children.length === 3,
        String(elements['spot-list'].children.length));
    check('the status says how many there are',
        elements['map-status'].textContent === '3 spots',
        elements['map-status'].textContent);

    console.log('\n== 4. Every category has its own shape ==');
    const shapes = {};
    layerState.markers.forEach((marker) => {
        const html = marker.icon.html;
        const shape = html.includes('<rect') ? 'square'
            : html.includes('<circle') ? 'circle'
            : html.includes('<path') ? 'triangle' : 'unknown';
        shapes[marker.title] = shape;
    });
    check('a skatepark is a square', shapes['Skatepark Oasis'] === 'square',
        shapes['Skatepark Oasis']);
    check('a street spot is a circle', shapes['Plaza del centro'] === 'circle',
        shapes['Plaza del centro']);
    check('a DIY spot is a triangle', shapes['DIY del parque'] === 'triangle',
        shapes['DIY del parque']);

    console.log('\n== 5. The source changes the fill ==');
    const osmIcon = layerState.markers.find((m) => m.title === 'Skatepark Oasis').icon.html;
    const communityIcon = layerState.markers.find((m) => m.title === 'Plaza del centro').icon.html;
    check('the OSM marker is solid', osmIcon.includes('marker-osm'));
    check('the community marker is hollow', communityIcon.includes('marker-community'));

    console.log('\n== 6. Clicking a marker selects the spot ==');
    layerState.markers.find((m) => m.title === 'Skatepark Oasis').click();
    await wait(10);
    check('the preview is open', elements['spot-preview'].hidden === false);
    check('it shows the name',
        elements['preview-name'].textContent === 'Skatepark Oasis',
        elements['preview-name'].textContent);
    check('it shows the category',
        elements['preview-category'].textContent === 'Skatepark');
    check('it shows the rating',
        elements['preview-rating'].textContent.indexOf('4.5') !== -1,
        elements['preview-rating'].textContent);
    check('it shows the source',
        elements['preview-source'].textContent === 'OpenStreetMap');
    check('the map moved to the spot',
        mapState.center[0] === 20.706324, JSON.stringify(mapState.center));

    console.log('\n== 7. The list and the map stay in sync ==');
    const selected = elements['spot-list'].children.filter(
        (item) => item.classList.contains('is-selected')
    );
    check('the entry of the list is highlighted', selected.length === 1,
        String(selected.length));
    check('it is the right entry',
        selected.length === 1 && selected[0].dataset.spotId === '1',
        selected.length ? selected[0].dataset.spotId : 'none');
    const selectedMarker = layerState.markers.find(
        (m) => m.icon.html.includes('is-selected')
    );
    check('the marker is highlighted too', !!selectedMarker);

    console.log('\n== 8. The search asks the API ==');
    fetchCalls = [];
    elements['spot-search'].value = 'oasis';
    elements['spot-search'].dispatch('input');
    await wait(400);
    check('the request was sent', fetchCalls.length === 1, String(fetchCalls.length));
    check('it carries the text',
        lastCall().includes('search=oasis'), lastCall());

    console.log('\n== 9. The filters ask the API ==');
    fetchCalls = [];
    filterBoxes.category.forEach((box) => { box.checked = box.value === 'diy'; });
    elements['map-filters'].dispatch('change');
    await wait(20);
    check('the request was sent', fetchCalls.length === 1, String(fetchCalls.length));
    check('it carries the category',
        lastCall().includes('category=diy'), lastCall());
    filterBoxes.category.forEach((box) => { box.checked = true; });

    console.log('\n== 10. The location of the visitor ==');
    const locationCalls = [];
    sandbox.navigator.geolocation = {
        getCurrentPosition(onSuccess, onError) {
            locationCalls.push('called');
            onSuccess({
                coords: { latitude: 20.671, longitude: -103.34, accuracy: 30 },
            });
        },
    };
    const locateButton = controlState.controls
        .flatMap((c) => c.container ? c.container.children : []);
    check('there is a control for the location', locateButton.length >= 2,
        String(locateButton.length));
    locateButton[0].onclick({});
    await wait(10);
    check('the browser was asked', locationCalls.length === 1);
    check('the map moved to the visitor',
        mapState.center[0] === 20.671, JSON.stringify(mapState.center));

    console.log('\n== 11. The location is refused ==');
    sandbox.navigator.geolocation = {
        getCurrentPosition(onSuccess, onError) {
            onError({ code: 1, message: 'denied' });
        },
    };
    locateButton[0].onclick({});
    await wait(10);
    check('the visitor is told',
        elements['map-status'].textContent.indexOf('permiso') !== -1,
        elements['map-status'].textContent);

    console.log('\n== 12. The pagination is followed ==');
    fetchCalls = [];
    fetchPages = [
        { count: 60, next: '/api/spots/?limit=50&offset=50', results: SPOTS },
        { count: 60, next: null, results: SPOTS },
    ];
    elements['spot-search'].value = '';
    elements['spot-search'].dispatch('input');
    await wait(400);
    check('both pages were asked', fetchCalls.length === 2, String(fetchCalls.length));
    check('the second one follows the link',
        fetchCalls[1] === '/api/spots/?limit=50&offset=50', fetchCalls[1]);

    console.log('\n== 13. The list can be folded away ==');
    elements['sidebar-toggle'].dispatch('click');
    check('the list opens', elements['map-sidebar'].classList.contains('is-open'));
    elements['sidebar-toggle'].dispatch('click');
    check('the list closes', !elements['map-sidebar'].classList.contains('is-open'));

    console.log('\n' + (failures === 0
        ? 'ALL CHECKS PASSED'
        : failures + ' CHECK(S) FAILED'));
    process.exit(failures === 0 ? 0 : 1);
})();
