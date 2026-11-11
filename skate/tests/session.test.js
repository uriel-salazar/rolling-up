/**
 * Behaviour test for the session of the browser in the bar of the page.
 *
 * The application signs the visitors in with a token in the local
 * storage, so the server does not know who is reading the page. The
 * script shows the part of the bar that belongs to the visitor.
 *
 * The script is plain JavaScript, so it is exercised here against a
 * small DOM stub instead of a real browser. Node runs it without any
 * dependency:
 *
 *     node skate/tests/session.test.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PROJECT = path.resolve(__dirname, '..', '..');
const JS_PATH = path.join(PROJECT, 'skate/static/session.js');

// ------------------------------------------------------------------
// DOM stub
// ------------------------------------------------------------------

function makeElement(id, attribute) {
    const element = {
        id: id,
        tagName: 'DIV',
        hidden: false,
        attributes: {},
        getAttribute(name) { return this.attributes[name]; },
        setAttribute(name, value) { this.attributes[name] = value; },
    };
    if (attribute) {
        element.attributes[attribute] = attribute;
    }
    return element;
}

function buildSandbox(store) {
    const elements = {};
    const listeners = {};

    const sandbox = {
        console: console,
        document: {
            body: { classList: { _set: new Set(), toggle() {} } },
            readyState: 'complete',
            addEventListener(name, fn) {
                (listeners[name] = listeners[name] || []).push(fn);
            },
            querySelectorAll(selector) {
                if (selector !== '[data-session]') {
                    return [];
                }
                return Object.values(elements).filter(function (element) {
                    return element.getAttribute('data-session') !== undefined;
                });
            },
        },
        localStorage: {
            getItem: (key) => (key in store ? store[key] : null),
            setItem: (key, value) => { store[key] = value; },
            removeItem: (key) => { delete store[key]; },
        },
    };
    sandbox.window = sandbox;
    sandbox.global = sandbox;

    return { sandbox: sandbox, elements: elements, listeners: listeners };
}

let failures = 0;
function check(label, condition, extra) {
    if (condition) {
        console.log('  PASS  ' + label);
    } else {
        failures += 1;
        console.log('  FAIL  ' + label + (extra ? ' -> ' + extra : ''));
    }
}

// ------------------------------------------------------------------
// 1. A visitor without a session
// ------------------------------------------------------------------

console.log('\n== 1. A visitor without a session ==');
{
    const store = {};
    const built = buildSandbox(store);
    const inPart = makeElement('in', 'data-session');
    inPart.attributes['data-session'] = 'in';
    const outPart = makeElement('out', 'data-session');
    outPart.attributes['data-session'] = 'out';
    built.elements.in = inPart;
    built.elements.out = outPart;

    vm.createContext(built.sandbox);
    vm.runInContext(fs.readFileSync(JS_PATH, 'utf8'), built.sandbox);

    check('the part of the session is hidden', inPart.hidden === true);
    check('the part without a session is shown', outPart.hidden === false);
    check('the script tells whether there is a session',
        built.sandbox.RollingUpSession.hasSession() === false);
}

// ------------------------------------------------------------------
// 2. A visitor with a session
// ------------------------------------------------------------------

console.log('\n== 2. A visitor with a session ==');
{
    const store = { access: 'a-token' };
    const built = buildSandbox(store);
    const inPart = makeElement('in');
    inPart.attributes['data-session'] = 'in';
    const outPart = makeElement('out');
    outPart.attributes['data-session'] = 'out';
    built.elements.in = inPart;
    built.elements.out = outPart;

    vm.createContext(built.sandbox);
    vm.runInContext(fs.readFileSync(JS_PATH, 'utf8'), built.sandbox);

    check('the part of the session is shown', inPart.hidden === false);
    check('the part without a session is hidden', outPart.hidden === true);
    check('the script tells that there is a session',
        built.sandbox.RollingUpSession.hasSession() === true);
}

// ------------------------------------------------------------------
// 3. The bar is drawn again when the session changes
// ------------------------------------------------------------------

console.log('\n== 3. The bar is drawn again ==');
{
    const store = {};
    const built = buildSandbox(store);
    const inPart = makeElement('in');
    inPart.attributes['data-session'] = 'in';
    built.elements.in = inPart;

    vm.createContext(built.sandbox);
    vm.runInContext(fs.readFileSync(JS_PATH, 'utf8'), built.sandbox);

    check('the part of the session starts hidden', inPart.hidden === true);

    store.access = 'a-token';
    built.sandbox.RollingUpSession.refresh();

    check('the part of the session is shown after the refresh',
        inPart.hidden === false);

    delete store.access;
    built.sandbox.RollingUpSession.refresh();

    check('the part of the session is hidden again after the refresh',
        inPart.hidden === true);
}

console.log('');
if (failures) {
    console.log(failures + ' check(s) failed.');
    process.exit(1);
}
console.log('All the checks passed.');
