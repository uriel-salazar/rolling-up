/**
 * Behaviour test for the feed of the spots.
 *
 * The feed is plain JavaScript, so it is exercised here against a
 * small DOM stub instead of a real browser. Node runs it without any
 * dependency:
 *
 *     node skate/tests/feed.test.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PROJECT = path.resolve(__dirname, '..', '..');

// ------------------------------------------------------------------
// DOM stub
// ------------------------------------------------------------------

function makeElement(tag) {
    const element = {
        tagName: (tag || 'div').toUpperCase(),
        value: '',
        textContent: '',
        hidden: false,
        className: '',
        dataset: {},
        style: {},
        children: [],
        attributes: {},
        listeners: {},
        classList: {
            _set: new Set(),
            add(name) { this._set.add(name); },
            remove(name) { this._set.delete(name); },
            contains(name) { return this._set.has(name); },
        },
        getAttribute(name) { return this.attributes[name]; },
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
        appendChild(child) { this.children.push(child); return child; },
        querySelector(sel) { return null; },
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
        focus() {},
    };
    // Replacing the html of an element empties it.
    let html = '';
    Object.defineProperty(element, 'innerHTML', {
        get() { return html; },
        set(value) {
            html = value;
            if (value === '') {
                element.children = [];
            }
        },
    });

    return element;
}

const elements = {};
[
    'feed-grid', 'feed-count', 'feed-search', 'feed-search-clear',
    'feed-location-search', 'feed-location-results', 'feed-location-clear',
    'feed-more',
    'feed-pagination', 'feed-pagination-prev', 'feed-pagination-next',
    'feed-pagination-page',
    'spot-modal', 'spot-modal-close', 'spot-modal-image', 'spot-modal-name',
    'spot-modal-category', 'spot-modal-address', 'spot-modal-directions',
    'spot-modal-body',
].forEach((id) => { elements[id] = makeElement('div'); });
elements['feed-search'].value = '';
elements['feed-location-search'].value = '';
elements['feed-more'].hidden = true;
elements['feed-pagination'].hidden = true;
elements['feed-pagination-prev'].hidden = true;
elements['feed-pagination-next'].hidden = true;

// ------------------------------------------------------------------
// The API
// ------------------------------------------------------------------

const SPOTS = [
    {
        id: 2, name_spot: 'las cañadas', body: 'this is a test',
        image_url: 'http://test/media/a.jpeg', latitude: null, longitude: null,
        source: 'community', category: 'street', rating: null, rating_count: 0,
        osm_metadata: null,
    },
    {
        id: 3, name_spot: 'Skatepark San Jacinto', body: null, image_url: null,
        latitude: '20.662607', longitude: '-103.297262', source: 'osm',
        category: 'skatepark', rating: 4.5, rating_count: 12,
        osm_id: 123, osm_type: 'way',
        osm_metadata: {
            tags: {
                name: 'Skatepark San Jacinto',
                'addr:street': 'Calle Libre',
                'addr:city': 'Guadalajara',
            },
        },
    },
    {
        id: 4, name_spot: 'Paseo San Ignacio Skatepark', body: null,
        image_url: null, latitude: '20.671073', longitude: '-103.405057',
        source: 'osm', category: 'skatepark', rating: null, rating_count: 0,
        osm_metadata: { tags: {} },
    },
];

let fetchCalls = [];
let fetchPages = [
    { count: SPOTS.length, next: null, results: SPOTS },
];
let locationOptions = null;

const sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    document: {
        getElementById: (id) => elements[id] || null,
        createElement: (tag) => makeElement(tag),
        createElementNS: (ns, tag) => makeElement(tag),
        addEventListener: () => {},
        body: {
            classList: {
                _set: new Set(),
                add(name) { this._set.add(name); },
                remove(name) { this._set.delete(name); },
                contains(name) { return this._set.has(name); },
            },
            style: {},
        },
    },
    window: {
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        location: { search: '' },
    },
    URLSearchParams: URLSearchParams,
    AbortController: function () { this.signal = {}; this.abort = function () {}; },
    RollingUpLocationSearch: {
        create: function (options) {
            locationOptions = options;
            return { search() {}, clear() {} };
        },
    },
    fetch: function (url) {
        fetchCalls.push(url);
        const page = fetchPages.shift() || { count: 0, next: null, results: [] };
        return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(page),
        });
    },
};
sandbox.window.setTimeout = setTimeout;
sandbox.window.clearTimeout = clearTimeout;
sandbox.window.RollingUpLocationSearch = sandbox.RollingUpLocationSearch;

vm.createContext(sandbox);

function loadApi() {
    const source = fs.readFileSync(path.join(PROJECT, 'skate/static/api.js'), 'utf8');
    vm.runInContext(source, sandbox);
}

function loadRating() {
    const source = fs.readFileSync(path.join(PROJECT, 'skate/static/rating.js'), 'utf8');
    vm.runInContext(source, sandbox);
}

function loadFeed() {
    const source = fs.readFileSync(path.join(PROJECT, 'skate/static/feed.js'), 'utf8');
    vm.runInContext(source, sandbox);
}

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

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function findByClass(root, className) {
    const found = [];
    (function walk(node) {
        (node.children || []).forEach((child) => {
            const classes = (child.className || '').split(/\s+/);
            if (classes.indexOf(className) !== -1) {
                found.push(child);
            }
            walk(child);
        });
    })(root);
    return found;
}

function findByTag(root, tag) {
    const found = [];
    (function walk(node) {
        (node.children || []).forEach((child) => {
            if (child.tagName === tag) { found.push(child); }
            walk(child);
        });
    })(root);
    return found;
}

function textOf(node) {
    if (!node) { return ''; }
    if (node.textContent) { return node.textContent; }
    let text = '';
    (node.children || []).forEach((child) => { text += textOf(child); });
    return text;
}

(async function run() {
    loadApi();
    loadRating();
    loadFeed();
    await wait(30);

    const grid = elements['feed-grid'];

    console.log('\n== 1. The spots are read from the API ==');
    check('the API was asked', fetchCalls.length === 1, String(fetchCalls.length));
    check('it is the spots endpoint', fetchCalls[0].startsWith('/api/spots/?'),
        fetchCalls[0]);

    console.log('\n== 2. A card per spot ==');
    const cards = grid.children.filter((child) => child.className === 'spot-card');
    check('there is a card per spot', cards.length === 3, String(cards.length));
    check('the count is shown', elements['feed-count'].textContent === '3 spots',
        elements['feed-count'].textContent);
    check('the grid is not busy anymore', grid.getAttribute('aria-busy') === 'false',
        grid.getAttribute('aria-busy'));

    console.log('\n== 3. The picture of a spot ==');
    const withImage = cards[0];
    const images = findByTag(withImage, 'IMG');
    check('the picture is used', images.length === 1);
    check('it points at the file of the API',
        images.length === 1 && images[0].src === 'http://test/media/a.jpeg');
    check('it loads late', images.length === 1 && images[0].loading === 'lazy');
    check('the name is the alternative text',
        images.length === 1 && images[0].alt === 'las cañadas');

    console.log('\n== 4. The plate of a spot without a picture ==');
    const plates = findByClass(grid, 'spot-plate');
    check('a plate stands for every spot without a picture',
        plates.length === 2, String(plates.length));
    check('the plate shows the first letter of the name',
        plates.length === 2
        && textOf(plates[0]).charAt(0) === 'S'
        && textOf(plates[1]).charAt(0) === 'P',
        plates.map(textOf).join(' | '));
    check('the plate shows the kind of the spot',
        plates.length === 2 && textOf(plates[0]).indexOf('Skatepark') !== -1,
        plates.length ? textOf(plates[0]) : '');

    console.log('\n== 5. The name opens the spot on the map ==');
    const links = findByTag(cards[1], 'A');
    const title = links.find((link) => link.className === 'spot-card-title');
    check('the name is a link', !!title);
    check('it points at the spot of the map',
        title && title.href === '/map/?spot=3', title && title.href);

    console.log('\n== 6. The rating ==');
    const rated = findByClass(cards[1], 'spot-rating');
    check('the rating is shown', rated.length === 1);
    check('it shows the average and the amount of votes',
        rated.length === 1 && textOf(rated[0]).indexOf('4.5') !== -1
            && textOf(rated[0]).indexOf('12') !== -1,
        rated.length ? textOf(rated[0]) : '');
    const notRated = findByClass(cards[2], 'spot-rating-empty');
    check('a spot without a rating says so',
        notRated.length === 1 && textOf(notRated[0]) === 'Not rated yet',
        notRated.length ? textOf(notRated[0]) : '');
    const unratedText = textOf(notRated[0]);
    check('an unrated spot does not have a score of zero',
        unratedText.indexOf('0.0') === -1, unratedText);
    const stars = findByClass(cards[1], 'stars-readonly');
    check('the average is drawn with stars', stars.length === 1);
    const fill = stars.length === 1
        ? (stars[0].style['--fill'] || stars[0].getAttribute('style') || '')
        : '';
    check('the stars are filled in part',
        stars.length === 1 && String(fill).indexOf('--fill: 90%') !== -1,
        String(fill));

    console.log('\n== 7. The directions ==');
    const directions = findByClass(cards[1], 'spot-directions');
    check('the directions are shown when there are coordinates',
        directions.length === 1);
    check('they point at the place of the spot',
        directions.length === 1
        && directions[0].href === 'https://www.google.com/maps/dir/?api=1&destination=20.662607%2C-103.297262',
        directions.length ? directions[0].href : '');
    check('they open in a new tab',
        directions.length === 1 && directions[0].target === '_blank');
    check('the directions of a spot without a place are not shown',
        findByClass(cards[0], 'spot-directions').length === 0);

    console.log('\n== 8. The place ==');
    const places = findByClass(cards[1], 'spot-meta-item');
    check('the place of the spot is shown',
        places.some((item) => textOf(item).indexOf('Guadalajara') !== -1),
        places.map(textOf).join(' | '));
    check('a spot without a place does not show an empty place',
        findByClass(cards[2], 'spot-meta-item').every(
            (item) => textOf(item).indexOf('Not rated') !== -1
        ));

    console.log('\n== 9. The search ==');
    fetchCalls = [];
    elements['feed-search'].value = 'oasis';
    elements['feed-search'].dispatch('input');
    check('nothing is sent while the visitor types', fetchCalls.length === 0,
        String(fetchCalls.length));
    await wait(450);
    check('the search is sent after the delay', fetchCalls.length === 1,
        String(fetchCalls.length));
    check('it carries the text', fetchCalls[0].indexOf('search=oasis') !== -1,
        fetchCalls[0]);

    console.log('\n== 10. The empty state ==');
    fetchCalls = [];
    fetchPages = [{ count: 0, next: null, results: [] }];
    elements['feed-search'].value = 'nada de esto';
    elements['feed-search'].dispatch('input');
    await wait(450);
    const empty = findByClass(grid, 'feed-message');
    check('a message is shown', empty.length === 1);
    check('it says that nothing was found',
        empty.length === 1 && textOf(empty[0]).indexOf('Nothing found') !== -1,
        empty.length ? textOf(empty[0]) : '');

    console.log('\n== 11. The error state ==');
    fetchPages = [];
    sandbox.fetch = function () {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
    };
    elements['feed-search'].value = '';
    elements['feed-search'].dispatch('input');
    await wait(450);
    const failure = findByClass(grid, 'feed-message');
    check('a message is shown', failure.length === 1);
    check('it says that the spots did not load',
        failure.length === 1 && textOf(failure[0]).indexOf('did not load') !== -1,
        failure.length ? textOf(failure[0]) : '');

    console.log('\n== 12. The pagination ==');
    sandbox.fetch = function (url) {
        fetchCalls.push(url);
        return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({
                count: 2,
                next: 'http://test/api/spots/?limit=24&offset=24',
                previous: null,
                results: SPOTS.slice(0, 1),
            }),
        });
    };
    fetchCalls = [];
    elements['feed-search'].value = '';
    elements['feed-search'].dispatch('input');
    await wait(450);
    check('the first page is asked', fetchCalls.length === 1, String(fetchCalls.length));
    check('the button of the next page is shown',
        elements['feed-pagination-next'].hidden === false,
        String(elements['feed-pagination-next'].hidden));
    check('the button of the previous page is hidden',
        elements['feed-pagination-prev'].hidden === true,
        String(elements['feed-pagination-prev'].hidden));

    // The button asks for the next page.
    elements['feed-pagination-next'].dispatch('click');
    await wait(60);
    check('the next page is asked', fetchCalls.length === 2, String(fetchCalls.length));
    check('it asks for the spots that follow',
        fetchCalls.some((url) => url.indexOf('offset=24') !== -1),
        fetchCalls.join(' | '));

    console.log('\n== 13. Searching a place adds live results ==');
    const EXTERNAL = [
        {
            id: 'osm:way:99', external: true, name_spot: 'Live Park',
            body: null, latitude: 20.670000, longitude: -103.350000,
            source: 'osm', category: 'skatepark', osm_id: 99, osm_type: 'way',
            rating: null, rating_count: 0, image_url: null,
        },
        {
            id: 'osm:way:123', external: true, name_spot: 'Duplicate park',
            body: null, latitude: 20.662607, longitude: -103.297262,
            source: 'osm', category: 'skatepark', osm_id: 123, osm_type: 'way',
            rating: null, rating_count: 0, image_url: null,
        },
    ];
    fetchCalls = [];
    fetchPages = [{ count: SPOTS.length, next: null, results: SPOTS }];
    sandbox.fetch = function (url) {
        fetchCalls.push(url);
        if (url.indexOf('/api/spots/viewport/') === 0) {
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve({
                    source: 'openstreetmap', count: EXTERNAL.length,
                    results: EXTERNAL,
                }),
            });
        }
        const page = fetchPages.shift()
            || { count: 0, next: null, results: [] };
        return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve(page),
        });
    };

    locationOptions.onSelect({
        label: 'Guadalajara, Jalisco, México',
        short_label: 'Guadalajara',
        latitude: 20.6767,
        longitude: -103.3475,
        bounding_box: {
            south: 20.60, west: -103.45, north: 20.75, east: -103.25,
        },
    });
    await wait(40);

    const liveCards = findByClass(grid, 'spot-card');
    check('the viewport is asked for the place',
        fetchCalls.some((url) => url.indexOf('/api/spots/viewport/') === 0),
        fetchCalls.join(' | '));
    check('the registered spots and the live ones are merged',
        liveCards.length === 3, String(liveCards.length));
    check('the live card is marked',
        findByClass(grid, 'spot-source-live').length === 1);
    const liveTitle = findByClass(grid, 'spot-card-title')
        .find((link) => textOf(link) === 'Live Park');
    check('the live card links to OpenStreetMap',
        liveTitle && liveTitle.href === 'https://www.openstreetmap.org/way/99',
        liveTitle && liveTitle.href);
    check('the same OSM object is not repeated',
        findByClass(grid, 'spot-card-title')
            .filter((link) => textOf(link) === 'Duplicate park').length === 0);

    locationOptions.onClear();
    await wait(40);
    check('clearing the place removes the live results',
        findByClass(grid, 'spot-source-live').length === 0);

    // ------------------------------------------------------------------
    console.log('\n== The button "Ver mas" ==');
    // ------------------------------------------------------------------

    const more = elements['feed-more'];

    // The embedded feed shows a few spots and the button opens the
    // rest.
    sandbox.document.body.classList.add('is-embed');
    fetchCalls = [];
    fetchPages = [{ count: 25, next: null, results: SPOTS }];
    loadFeed();
    await wait(60);

    check('the embedded feed asks for nine spots',
        fetchCalls.some((url) => url.indexOf('limit=9') !== -1),
        fetchCalls.join(' | '));
    check('the embedded feed asks for one page',
        fetchCalls.length === 1, String(fetchCalls.length));
    check('the button is shown when there are more spots',
        more.hidden === false, String(more.hidden));

    // The whole feed shows every spot, so there is nothing more to see.
    sandbox.document.body.classList.remove('is-embed');
    fetchCalls = [];
    fetchPages = [{ count: 25, next: null, results: SPOTS }];
    loadFeed();
    await wait(60);

    check('the whole feed asks for the usual page',
        fetchCalls.some((url) => url.indexOf('limit=24') !== -1),
        fetchCalls.join(' | '));
    check('the button is hidden in the whole feed',
        more.hidden === true, String(more.hidden));

    // When every spot is shown, the button has nothing to open.
    sandbox.document.body.classList.add('is-embed');
    fetchCalls = [];
    fetchPages = [{ count: 3, next: null, results: SPOTS }];
    loadFeed();
    await wait(60);

    check('the button is hidden when all the spots are shown',
        more.hidden === true, String(more.hidden));

    console.log('\n' + (failures === 0
        ? 'ALL CHECKS PASSED'
        : failures + ' CHECK(S) FAILED'));
    process.exit(failures === 0 ? 0 : 1);
})();
