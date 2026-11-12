/**
 * Behaviour test for the rating of a spot on the detail page.
 *
 * The page is plain JavaScript, so it is exercised here against a
 * small DOM stub instead of a real browser. Node runs it without any
 * dependency:
 *
 *     node skate/tests/spot_detail_rating.test.js
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
        disabled: false,
        className: '',
        dataset: {},
        style: {
            setProperty(name, value) { this[name] = value; },
        },
        children: [],
        attributes: {},
        listeners: {},
        classList: {
            _set: new Set(),
            add(name) { this._set.add(name); },
            remove(name) { this._set.delete(name); },
            contains(name) { return this._set.has(name); },
            toggle(name, force) {
                if (force) { this._set.add(name); } else { this._set.delete(name); }
            },
        },
        getAttribute(name) { return this.attributes[name]; },
        setAttribute(name, value) { this.attributes[name] = value; },
        appendChild(child) { this.children.push(child); return child; },
        querySelector() { return null; },
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
    'photo-upload-form', 'photo-status', 'photo-image', 'photo-caption',
    'photo-submit', 'spot-photo-grid',
    'rating-section', 'rating-average', 'rating-form', 'rating-login-note',
    'rating-stars', 'rating-comment', 'rating-submit', 'rating-delete',
    'rating-status', 'rating-score', 'rating-current', 'rating-list',
    'spot-map',
].forEach((id) => { elements[id] = makeElement('div'); });

elements['rating-section'].dataset = {
    spotId: '13',
    average: '4.5',
    count: '12',
    userScore: '',
    userComment: '',
};
elements['rating-comment'].value = '';

// ------------------------------------------------------------------
// The session of the browser
// ------------------------------------------------------------------

const TOKEN = 'header.' + Buffer.from(JSON.stringify({
    user_id: '2', username: 'leoooo',
})).toString('base64url') + '.signature';

const store = { access: TOKEN };

// ------------------------------------------------------------------
// The API
// ------------------------------------------------------------------

let calls = [];
let responses = [];

function answer(status, payload) {
    return Promise.resolve({
        ok: status < 400,
        status: status,
        json: () => Promise.resolve(payload || {}),
    });
}

const sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    atob: (value) => Buffer.from(value, 'base64').toString('binary'),
    btoa: (value) => Buffer.from(value, 'binary').toString('base64'),
    localStorage: {
        getItem: (key) => store[key] || null,
        setItem: (key, value) => { store[key] = value; },
        removeItem: (key) => { delete store[key]; },
    },
    document: {
        getElementById: (id) => elements[id] || null,
        createElement: (tag) => makeElement(tag),
        querySelector: () => null,
        querySelectorAll: () => [],
        addEventListener: () => {},
        body: {
            dataset: { spotId: '13' },
            classList: {
                _set: new Set(),
                add() {}, remove() {}, contains() { return false; },
            },
            style: {},
        },
    },
    window: {
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        location: { href: '' },
        addEventListener: () => {},
    },
    URLSearchParams: URLSearchParams,
    AbortController: function () { this.signal = {}; this.abort = function () {}; },
    fetch: function (url, options) {
        calls.push({ url: url, options: options || {} });
        const next = responses.shift();
        if (!next) {
            return answer(404, {});
        }
        return next;
    },
};
sandbox.window.setTimeout = setTimeout;
sandbox.window.clearTimeout = clearTimeout;
sandbox.window.localStorage = sandbox.localStorage;

vm.createContext(sandbox);

function loadScript(name) {
    const source = fs.readFileSync(path.join(PROJECT, 'skate/static', name), 'utf8');
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

function textOf(node) {
    if (!node) { return ''; }
    if (node.textContent) { return node.textContent; }
    let text = '';
    (node.children || []).forEach((child) => { text += textOf(child); });
    return text;
}

(async function run() {
    loadScript('rating.js');
    loadScript('spot_detail.js');
    await wait(30);

    const form = elements['rating-form'];
    const starsBox = elements['rating-stars'];
    const status = elements['rating-status'];
    const submit = elements['rating-submit'];
    const comment = elements['rating-comment'];
    const list = elements['rating-list'];

    console.log('\n== 1. The visitor is logged in ==');
    check('the form of the rating is shown', form.hidden === false);
    check('the note to log in is hidden', elements['rating-login-note'].hidden === true);
    check('the stars of the visitor are drawn',
        findByClass(starsBox, 'star-button').length === 5);
    check('the average of the spot is drawn',
        findByClass(elements['rating-average'], 'stars-readonly').length === 1);

    console.log('\n== 2. The rating is saved ==');
    calls = [];
    responses = [answer(201, { id: 5, score: 4, comment: 'Buen bowl' })];

    const stars = findByClass(starsBox, 'star-button');
    stars[3].dispatch('click');
    comment.value = 'Buen bowl';
    submit.dispatch('click');
    await wait(30);

    const posted = calls.find((call) => call.url.indexOf('/rate/') !== -1);
    check('the rating is sent to the spot', !!posted,
        calls.map((call) => call.url).join(' | '));
    check('it is a POST', posted && posted.options.method === 'POST');
    check('the token travels with it',
        posted && posted.options.headers.Authorization === 'Bearer ' + TOKEN);
    check('the score and the comment are sent',
        posted && posted.options.body.indexOf('"score":4') !== -1
        && posted.options.body.indexOf('Buen bowl') !== -1,
        posted ? posted.options.body : '');
    check('the stars are filled before the answer',
        stars[3].classList.contains('star-filled'));
    check('the status says that it was saved',
        status.textContent.indexOf('guardada') !== -1, status.textContent);
    check('the average is asked again',
        calls.some((call) => call.url.indexOf('/api/spots/13/') !== -1),
        calls.map((call) => call.url).join(' | '));

    console.log('\n== 3. The rating is not valid ==');
    calls = [];
    responses = [answer(400, { score: ['Ensure this value is less than or equal to 5.'] })];

    stars[4].dispatch('click');
    submit.dispatch('click');
    await wait(30);

    check('the error of the server is shown',
        status.textContent.indexOf('less than or equal') !== -1, status.textContent);
    check('the status is an error', status.className.indexOf('is-error') !== -1,
        status.className);

    console.log('\n== 4. The session is gone ==');
    calls = [];
    responses = [answer(401, { detail: 'Token inválido' })];
    store.access = TOKEN;

    stars[2].dispatch('click');
    submit.dispatch('click');
    await wait(30);

    check('the visitor goes to the page of the session',
        sandbox.window.location.href === '/profile/',
        sandbox.window.location.href);
    check('the token is forgotten', !store.access);

    console.log('\n== 5. The list of the ratings ==');
    calls = [];
    responses = [
        answer(200, {
            count: 2,
            results: [
                {
                    id: 5, score: 4, comment: 'Buen bowl',
                    user_username: 'leoooo', user: 2,
                    created_at: '2026-11-11T21:00:00Z',
                },
                {
                    id: 6, score: 5, comment: '',
                    user_username: 'otro', user: 3,
                    created_at: '2026-11-12T10:00:00Z',
                },
            ],
        }),
        answer(200, { rating: 4.5, rating_count: 2 }),
    ];

    // The list is asked again when the page is loaded.
    elements['rating-section'].dataset.userScore = '';
    loadScript('spot_detail.js');
    await wait(40);

    const items = findByClass(list, 'spot-rating-item');
    check('every rating is drawn', items.length === 2, String(items.length));
    check('the name of the rider is shown',
        items.length === 2 && textOf(items[0]).indexOf('leoooo') !== -1,
        items.length ? textOf(items[0]) : '');
    check('the score is shown',
        items.length === 2 && textOf(items[0]).indexOf('4.0') !== -1,
        items.length ? textOf(items[0]) : '');
    check('the comment is shown',
        items.length === 2 && textOf(items[0]).indexOf('Buen bowl') !== -1,
        items.length ? textOf(items[0]) : '');
    check('the date is shown',
        items.length === 2 && textOf(items[0]).indexOf('2026') !== -1,
        items.length ? textOf(items[0]) : '');
    check('a rating without a comment does not leave an empty line',
        items.length === 2 && textOf(items[1]).indexOf('otro') !== -1,
        items.length ? textOf(items[1]) : '');

    console.log('');
    if (failures) {
        console.log(failures + ' check(s) failed.');
        process.exit(1);
    }
    console.log('All the checks passed.');
})();
