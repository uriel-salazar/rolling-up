/**
 * Behaviour test for the stars of the spots.
 *
 * The stars are plain JavaScript, so they are exercised here against
 * a small DOM stub instead of a real browser. Node runs it without any
 * dependency:
 *
 *     node skate/tests/rating.test.js
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
    return element;
}

const sandbox = {
    console: console,
    document: {
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
    },
    window: {},
};
sandbox.window.setTimeout = setTimeout;
sandbox.window.clearTimeout = clearTimeout;

vm.createContext(sandbox);

const source = fs.readFileSync(path.join(PROJECT, 'skate/static/rating.js'), 'utf8');
vm.runInContext(source, sandbox);

const Rating = sandbox.window.RollingUpRating;

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

console.log('\n== 1. The stars of the average ==');
const readOnly = Rating.createReadOnly(4.5, 12);
const stars = findByClass(readOnly, 'stars-readonly');
check('the stars are drawn', stars.length === 1);
check('they are filled in part', stars.length === 1 && stars[0].style['--fill'] === '90%',
    stars.length ? String(stars[0].style['--fill']) : '');
check('they say how much they are worth',
    stars.length === 1 && stars[0].getAttribute('aria-label') === '4.5 de 5',
    stars.length ? stars[0].getAttribute('aria-label') : '');
check('the average is shown', textOf(readOnly).indexOf('4.5') !== -1, textOf(readOnly));
check('the amount of votes is shown', textOf(readOnly).indexOf('(12)') !== -1,
    textOf(readOnly));

console.log('\n== 2. A spot without ratings ==');
const empty = Rating.createReadOnly(null, 0);
check('it says that it is not rated',
    textOf(empty).indexOf('Sin calificar') !== -1, textOf(empty));
check('it does not show a score of zero',
    textOf(empty).indexOf('0.0') === -1, textOf(empty));

console.log('\n== 3. The stars of the visitor ==');
let selected = null;
const interactive = Rating.createInteractive({
    value: 3,
    onSelect: function (score) { selected = score; },
});
const buttons = interactive.children;
check('there are five stars', buttons.length === 5, String(buttons.length));
check('they are a group of radio buttons',
    interactive.getAttribute('role') === 'radiogroup');
check('the score of the visitor is kept',
    interactive.getScore() === 3, String(interactive.getScore()));
check('the three first stars are filled',
    buttons[0].classList.contains('star-filled')
    && buttons[2].classList.contains('star-filled')
    && !buttons[3].classList.contains('star-filled'));
check('the star of the score is the one of the keyboard',
    buttons[2].getAttribute('tabindex') === '0'
    && buttons[0].getAttribute('tabindex') === '-1');
check('every star says how much it is worth',
    buttons[4].getAttribute('aria-label') === 'Califica 5 de 5',
    buttons[4].getAttribute('aria-label'));

console.log('\n== 4. The mouse ==');
buttons[3].dispatch('mouseenter');
check('the stars up to the mouse are highlighted',
    buttons[0].classList.contains('star-hover')
    && buttons[3].classList.contains('star-hover')
    && !buttons[4].classList.contains('star-hover'));
buttons[3].dispatch('mouseleave');
check('the highlight goes away',
    !buttons[0].classList.contains('star-hover'));

buttons[4].dispatch('click');
check('the click sets the score', selected === 5, String(selected));
check('the score of the group follows', interactive.getScore() === 5);
check('the stars up to the score are filled',
    buttons[4].classList.contains('star-filled')
    && buttons[0].classList.contains('star-filled'));
check('the star of the score is checked',
    buttons[4].getAttribute('aria-checked') === 'true');

console.log('\n== 5. The keyboard ==');
selected = null;
interactive.dispatch('keydown', { key: 'ArrowLeft', preventDefault: function () {} });
check('the arrow moves the score', selected === 4, String(selected));
interactive.dispatch('keydown', { key: 'Home', preventDefault: function () {} });
check('the first star is the beginning', selected === 1, String(selected));
interactive.dispatch('keydown', { key: 'End', preventDefault: function () {} });
check('the last star is the end', selected === 5, String(selected));

console.log('\n== 6. The score of the visitor can be changed ==');
interactive.setScore(2);
check('the score changes', interactive.getScore() === 2);
check('the stars are painted again',
    buttons[1].classList.contains('star-filled')
    && !buttons[2].classList.contains('star-filled'));

console.log('');
if (failures) {
    console.log(failures + ' check(s) failed.');
    process.exit(1);
}
console.log('All the checks passed.');
