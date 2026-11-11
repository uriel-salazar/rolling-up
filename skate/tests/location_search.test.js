/**
 * Behaviour test for the shared city/region search.
 *
 * Run it with Node, without dependencies:
 *
 *     node skate/tests/location_search.test.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PROJECT = path.resolve(__dirname, '..', '..');
const JS_PATH = path.join(PROJECT, 'skate/static/location_search.js');

function makeElement(id, tag) {
    const element = {
        id: id,
        tagName: (tag || 'div').toUpperCase(),
        value: '',
        textContent: '',
        _innerHTML: '',
        hidden: false,
        className: '',
        type: '',
        children: [],
        attributes: {},
        listeners: {},
        appendChild(child) {
            this.children.push(child);
            child.parentNode = this;
        },
        setAttribute(key, value) { this.attributes[key] = value; },
        getAttribute(key) { return this.attributes[key]; },
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
        contains(child) {
            if (child === this) {
                return true;
            }
            if (this.children.indexOf(child) !== -1) {
                return true;
            }
            return this.children.some((item) => item.contains && item.contains(child));
        },
        focus() {},
    };
    Object.defineProperty(element, 'innerHTML', {
        get() { return this._innerHTML; },
        set(value) {
            this._innerHTML = value;
            if (value === '') {
                this.children = [];
            }
        },
    });
    return element;
}

const input = makeElement('location-search', 'input');
const results = makeElement('location-results');
const clear = makeElement('location-clear', 'button');
clear.hidden = true;

let fetchCalls = [];
let fetchResponse = {
    ok: true,
    json: () => Promise.resolve({
        results: [
            {
                label: 'Barcelona, Cataluña, España',
                short_label: 'Barcelona',
                latitude: 41.3828939,
                longitude: 2.1774322,
                bounding_box: {
                    south: 41.3170359,
                    west: 2.0524977,
                    north: 41.4682658,
                    east: 2.2283634,
                },
            },
        ],
    }),
};
let selected = null;
let cleared = 0;

const document = {
    createElement: (tag) => makeElement('', tag),
    addEventListener: () => {},
};

const sandbox = {
    console: console,
    document: document,
    window: {},
    fetch: function (url) {
        fetchCalls.push(url);
        return Promise.resolve(fetchResponse);
    },
    AbortController: function () {
        this.signal = {};
        this.abort = function () {};
    },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(JS_PATH, 'utf8'), sandbox);

const widget = sandbox.RollingUpLocationSearch.create({
    input: input,
    results: results,
    clearButton: clear,
    onSelect: (place) => { selected = place; },
    onClear: () => { cleared += 1; },
});

let failures = 0;
function check(label, condition, extra) {
    if (condition) {
        console.log('  PASS  ' + label);
    } else {
        failures += 1;
        console.log('  FAIL  ' + label + (extra ? ' -> ' + extra : ''));
    }
}

async function run() {
    console.log('\n== 1. The widget is created ==');
    check('it returns the public API', !!widget && typeof widget.search === 'function');

    console.log('\n== 2. Nothing is requested while typing ==');
    input.value = 'Bar';
    input.dispatch('input');
    check('an input does not hit the server', fetchCalls.length === 0);

    input.dispatch('keydown', { key: 'Enter' });
    await new Promise((resolve) => setTimeout(resolve, 0));
    check('Enter asks the proxy', fetchCalls.length === 1);
    check(
        'the url carries the query',
        fetchCalls[0] === '/api/geocode/search/?q=Bar',
        fetchCalls[0]
    );

    console.log('\n== 3. A result can be picked ==');
    check('the result is shown', results.children.length === 1);
    check('the result box is open', results.hidden === false);
    results.children[0].dispatch('click');
    check('the selection is passed on', selected && selected.short_label === 'Barcelona');
    check('the input keeps the short label', input.value === 'Barcelona');
    check('the clear button is shown', clear.hidden === false);
    check('the result box is closed', results.hidden === true);
    check(
        'the bounding box is kept',
        selected.bounding_box.south === 41.3170359
            && selected.bounding_box.east === 2.2283634
    );

    console.log('\n== 4. The clear button ==');
    clear.dispatch('click');
    await new Promise((resolve) => setTimeout(resolve, 0));
    check('the value is emptied', input.value === '');
    check('the callback is called', cleared === 1);
    check('the clear button is hidden', clear.hidden === true);

    console.log('\n== 5. A failed request ==');
    fetchResponse = { ok: false, json: () => Promise.resolve({}) };
    input.value = 'Tokyo';
    input.dispatch('keydown', { key: 'Enter' });
    await new Promise((resolve) => setTimeout(resolve, 0));
    check('a message is shown', results.children.length === 1);
    check(
        'the message explains the problem',
        results.children[0].textContent.indexOf('unavailable') !== -1,
        results.children[0].textContent
    );

    console.log('\n== 6. A short query ==');
    fetchCalls = [];
    input.value = 'Ba';
    input.dispatch('keydown', { key: 'Enter' });
    await new Promise((resolve) => setTimeout(resolve, 0));
    check('the server is not asked', fetchCalls.length === 0);
    check(
        'the visitor is asked for more characters',
        results.children[0].textContent.indexOf('at least') !== -1,
        results.children[0].textContent
    );

    console.log('');
    if (failures) {
        console.log(failures + ' CHECK(S) FAILED');
        process.exitCode = 1;
    } else {
        console.log('ALL CHECKS PASSED');
    }
}

run();
