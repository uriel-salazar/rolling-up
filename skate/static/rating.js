/**
 * The stars of a spot.
 *
 * The module draws the same two things everywhere:
 *
 * - the read only stars, with the average of the spot and the number
 *   of ratings, filled in part when the average is not a whole number,
 * - the interactive stars, with the score of the visitor, that can be
 *   used with the mouse and with the keyboard.
 *
 * It only uses the colours and the sizes of the application: the gold
 * of the stars, the grey of the empty ones and the typography of the
 * rest of the interface.
 */

(function (global) {
    'use strict';

    const MAX_STARS = 5;

    /** The text of the score, always with one decimal. */
    function formatScore(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) {
            return '0.0';
        }
        return number.toFixed(1);
    }

    /** The number of stars that are full, and the part of the next one. */
    function fillOf(score) {
        const value = Math.max(0, Math.min(MAX_STARS, Number(score) || 0));
        return (value / MAX_STARS) * 100;
    }

    /**
     * The stars that show the average of a spot.
     *
     * @param {number} score The average of the ratings.
     * @param {number} count How many ratings there are.
     * @param {Object} options `{ id, size }`.
     * @returns {HTMLElement}
     */
    function createReadOnly(score, count, options) {
        const settings = options || {};
        const hasRating = score !== null && score !== undefined && score !== '';

        const box = document.createElement('div');
        box.className = 'spot-rating-readonly';

        if (!hasRating) {
            const empty = document.createElement('span');
            empty.className = 'spot-rating-empty';
            empty.textContent = settings.emptyText || 'Sin calificar todavía';
            box.appendChild(empty);
            return box;
        }

        const stars = document.createElement('span');
        stars.className = 'stars-readonly';
        if (settings.size) {
            stars.classList.add('stars-readonly-' + settings.size);
        }
        stars.style.setProperty
            ? stars.style.setProperty('--fill', fillOf(score) + '%')
            : stars.setAttribute('style', '--fill: ' + fillOf(score) + '%;');
        stars.setAttribute('role', 'img');
        stars.setAttribute('aria-label', formatScore(score) + ' de 5');

        const base = document.createElement('span');
        base.className = 'stars-readonly-base';
        base.setAttribute('aria-hidden', 'true');
        base.textContent = '★★★★★';

        const fill = document.createElement('span');
        fill.className = 'stars-readonly-fill';
        fill.setAttribute('aria-hidden', 'true');
        fill.textContent = '★★★★★';

        stars.appendChild(base);
        stars.appendChild(fill);
        box.appendChild(stars);

        const scoreText = document.createElement('span');
        scoreText.className = 'spot-rating-value';
        scoreText.textContent = formatScore(score);
        box.appendChild(scoreText);

        const countText = document.createElement('span');
        countText.className = 'spot-rating-count';
        countText.textContent = '(' + (count || 0) + ')';
        box.appendChild(countText);

        return box;
    }

    /**
     * The stars the visitor can use.
     *
     * @param {Object} options `{ value, onSelect, label }`.
     * @returns {HTMLElement}
     */
    function createInteractive(options) {
        const settings = options || {};
        let selected = Number(settings.value) || 0;

        const field = document.createElement('div');
        field.className = 'stars-field';
        field.setAttribute('role', 'radiogroup');
        field.setAttribute('aria-label', settings.label || 'Califica este spot');

        const buttons = [];
        let focused = Math.max(0, (Number(settings.value) || 1) - 1);

        function paint(index) {
            buttons.forEach(function (button, position) {
                const score = position + 1;
                button.classList.toggle('star-filled', score <= index);
                button.classList.toggle('star-selected', score <= selected);
                button.setAttribute('aria-checked', score === selected ? 'true' : 'false');
                button.setAttribute(
                    'tabindex',
                    score === (index || selected) ? '0' : '-1'
                );
            });
        }

        function hover(index) {
            buttons.forEach(function (button, position) {
                button.classList.toggle('star-hover', position < index);
            });
        }

        function select(score, notify) {
            selected = score;
            paint(score);
            if (typeof settings.onSelect === 'function') {
                settings.onSelect(score);
            }
        }

        for (let score = 1; score <= MAX_STARS; score += 1) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'star star-button';
            button.setAttribute('role', 'radio');
            button.setAttribute('aria-checked', 'false');
            button.setAttribute('aria-label', 'Califica ' + score + ' de 5');
            button.setAttribute('title', score + ' de 5');
            button.dataset.score = String(score);
            button.textContent = '★';

            button.addEventListener('mouseenter', function () {
                hover(score);
            });

            button.addEventListener('mouseleave', function () {
                hover(0);
            });

            button.addEventListener('focus', function () {
                focused = score - 1;
                hover(score);
            });

            button.addEventListener('blur', function () {
                hover(0);
            });

            button.addEventListener('click', function () {
                focused = score - 1;
                select(score, true);
            });

            buttons.push(button);
            field.appendChild(button);
        }

        // The keyboard: the arrows move between the stars and the
        // score follows, the same way the other radio groups work.
        field.addEventListener('keydown', function (event) {
            let next = focused;
            if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
                next = Math.min(MAX_STARS - 1, focused + 1);
            } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
                next = Math.max(0, focused - 1);
            } else if (event.key === 'Home') {
                next = 0;
            } else if (event.key === 'End') {
                next = MAX_STARS - 1;
            } else {
                return;
            }

            event.preventDefault();
            focused = next;
            buttons[next].focus();
            select(next + 1, true);
        });

        paint(selected);

        field.setScore = function (score) {
            selected = Number(score) || 0;
            paint(selected);
        };

        field.getScore = function () {
            return selected;
        };

        return field;
    }

    global.RollingUpRating = {
        createReadOnly: createReadOnly,
        createInteractive: createInteractive,
        formatScore: formatScore,
        MAX_STARS: MAX_STARS,
    };
})(window);
