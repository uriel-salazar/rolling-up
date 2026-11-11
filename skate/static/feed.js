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

    // The search waits for the visitor to stop typing.
    const SEARCH_DELAY = 400;

    // How many plates are shown while the spots are loaded.
    const SKELETONS = 6;

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
            // A picture that does not load leaves the same plate that
            // a spot without a picture gets.
            image.addEventListener('error', function () {
                image.remove();
                if (!media.querySelector('.spot-plate')) {
                    media.appendChild(buildPlate(spot));
                }
            });
            media.appendChild(image);
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
        title.href = '/map/?spot=' + encodeURIComponent(spot.id);
        title.textContent = spot.name_spot;

        name.appendChild(title);
        info.appendChild(name);

        const meta = document.createElement('div');
        meta.className = 'spot-card-meta';

        const address = window.RollingUpApi.addressOf(spot);
        if (address) {
            meta.appendChild(buildMeta(iconPin(), address, 'spot-meta-item'));
        }

        meta.appendChild(buildRating(spot));

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
            link.textContent = 'Get directions';
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

        showSkeletons();
        countBox.textContent = '';

        try {
            const data = await window.RollingUpApi.fetchSpots(
                { search: query },
                { limit: 24, maxPages: 10 }
            );

            grid.setAttribute('aria-busy', 'false');

            if (!data.results.length) {
                countBox.textContent = '';
                showMessage(
                    'Nothing found',
                    query
                        ? 'No spot matches that search. Try another word.'
                        : 'There is no spot yet. Be the first to add one.',
                    false
                );
                return;
            }

            countBox.textContent = data.count === 1
                ? '1 spot'
                : data.count + ' spots';

            grid.innerHTML = '';
            data.results.forEach(function (spot) {
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

    loadSpots();
})();
