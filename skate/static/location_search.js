/**
 * Search a city, region or country through the application proxy.
 *
 * The widget deliberately has no autocomplete: it only asks Nominatim
 * when the visitor submits a query. The server caches and throttles the
 * answers, so the public geocoding service is not flooded.
 *
 * The same widget is used by the map and by the feed. The result items
 * reuse the existing `.search-result` styles of the application.
 */
(function (global) {
    'use strict';

    const MIN_LENGTH = 3;

    function create(options) {
        const input = options.input;
        const resultsBox = options.results;
        const clearButton = options.clearButton || null;
        const onSelect = options.onSelect || function () {};

        if (!input || !resultsBox) {
            return null;
        }

        let controller = null;
        let selectedLabel = '';

        /**
         * A fixed box escapes the horizontal scroller of the map
         * filters, so the list stays visible on a phone too.
         */
        function positionResults() {
            if (!resultsBox.style || !input.getBoundingClientRect) {
                return;
            }

            const rect = input.getBoundingClientRect();
            resultsBox.style.position = 'fixed';
            resultsBox.style.top = (rect.bottom + 6) + 'px';
            resultsBox.style.left = rect.left + 'px';
            resultsBox.style.right = 'auto';
            resultsBox.style.width = rect.width + 'px';
        }

        function showResults() {
            positionResults();
            resultsBox.hidden = false;
        }

        function hideResults() {
            resultsBox.innerHTML = '';
            resultsBox.hidden = true;
        }

        function renderMessage(text) {
            const item = document.createElement('p');
            item.className = 'search-result search-result-detail';
            item.textContent = text;
            resultsBox.appendChild(item);
            showResults();
        }

        function renderResults(results) {
            resultsBox.innerHTML = '';

            if (!results.length) {
                renderMessage('No place found. Try a city, region or country.');
                return;
            }

            results.forEach(function (place) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'search-result';

                const title = document.createElement('span');
                title.className = 'search-result-title';
                title.textContent = place.short_label || place.label;

                const detail = document.createElement('span');
                detail.className = 'search-result-detail';
                detail.textContent = place.label || '';

                button.appendChild(title);
                button.appendChild(detail);
                button.addEventListener('click', function () {
                    selectedLabel = place.short_label || place.label || '';
                    input.value = selectedLabel;
                    if (clearButton) {
                        clearButton.hidden = false;
                    }
                    hideResults();
                    onSelect(place);
                });

                resultsBox.appendChild(button);
            });

            showResults();
        }

        async function search() {
            const query = input.value.trim();

            if (query.length < MIN_LENGTH) {
                hideResults();
                renderMessage('Type at least ' + MIN_LENGTH + ' characters.');
                return;
            }

            if (controller) {
                controller.abort();
            }
            controller = new AbortController();

            try {
                const response = await fetch(
                    '/api/geocode/search/?q=' + encodeURIComponent(query),
                    {
                        headers: { 'Accept': 'application/json' },
                        signal: controller.signal,
                    }
                );

                if (!response.ok) {
                    renderMessage('The location search is unavailable right now.');
                    return;
                }

                const data = await response.json();
                renderResults(Array.isArray(data.results) ? data.results : []);
            } catch (error) {
                if (error.name === 'AbortError') {
                    return;
                }
                renderMessage('The location search is unavailable right now.');
            }
        }

        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                search();
            } else if (event.key === 'Escape') {
                hideResults();
            }
        });

        input.addEventListener('input', function () {
            if (clearButton) {
                clearButton.hidden = input.value === '';
            }
            if (input.value.trim() !== selectedLabel) {
                hideResults();
            }
        });

        if (clearButton) {
            clearButton.addEventListener('click', function () {
                input.value = '';
                selectedLabel = '';
                clearButton.hidden = true;
                hideResults();
                if (options.onClear) {
                    options.onClear();
                }
                input.focus();
            });
        }

        document.addEventListener('click', function (event) {
            if (event.target !== input && !resultsBox.contains(event.target)) {
                hideResults();
            }
        });

        if (global.addEventListener) {
            global.addEventListener('resize', function () {
                if (!resultsBox.hidden) {
                    positionResults();
                }
            });
            global.addEventListener('scroll', function () {
                if (!resultsBox.hidden) {
                    positionResults();
                }
            }, true);
        }

        return {
            search: search,
            clear: function () {
                input.value = '';
                selectedLabel = '';
                if (clearButton) {
                    clearButton.hidden = true;
                }
                hideResults();
            },
        };
    }

    global.RollingUpLocationSearch = { create: create };
})(window);
