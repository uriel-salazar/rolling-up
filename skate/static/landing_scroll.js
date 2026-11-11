/**
 * Landing page scroll behaviour.
 *
 * Reveals the sections as they enter the viewport and gives the
 * embedded feed and form the height of their content. That removes the
 * nested scrollbar and keeps the page scroll continuous.
 */
(function () {
    'use strict';

    const sections = Array.from(document.querySelectorAll('.landing-section'));
    const reduceMotion = window.matchMedia
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const navLinks = Array.from(document.querySelectorAll('.nav-link[href^="#"]'));
    const navById = new Map();

    navLinks.forEach(function (link) {
        const id = link.getAttribute('href').slice(1);

        if (id && !navById.has(id)) {
            navById.set(id, link);
        }
    });

    function setActiveLink(id) {
        navLinks.forEach(function (link) {
            const isActive = link.getAttribute('href') === '#' + id;

            link.classList.toggle('is-active', isActive);

            if (isActive) {
                link.setAttribute('aria-current', 'true');
            } else {
                link.removeAttribute('aria-current');
            }
        });
    }

    if (navById.size && 'IntersectionObserver' in window) {
        const spySections = Array.from(navById.keys())
            .map(function (id) { return document.getElementById(id); })
            .filter(Boolean);

        const visibleRatios = new Map();

        const spy = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                visibleRatios.set(
                    entry.target.id,
                    entry.isIntersecting ? entry.intersectionRatio : 0
                );
            });

            let bestId = null;
            let bestRatio = 0;

            visibleRatios.forEach(function (ratio, id) {
                if (ratio > bestRatio) {
                    bestRatio = ratio;
                    bestId = id;
                }
            });

            if (bestId) {
                setActiveLink(bestId);
            }
        }, {
            rootMargin: '-30% 0px -55% 0px',
            threshold: [0, 0.05, 0.15, 0.3, 0.5, 0.75, 1],
        });

        spySections.forEach(function (section) {
            spy.observe(section);
        });
    }

    if (sections.length && !reduceMotion && 'IntersectionObserver' in window) {
        sections.forEach(function (section) {
            section.classList.add('is-reveal');
        });

        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) {
                    return;
                }
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            });
        }, {
            threshold: 0.08,
            rootMargin: '0px 0px -8% 0px',
        });

        sections.forEach(function (section) {
            observer.observe(section);
        });
    }

    function frameHeight(frame) {
        try {
            const documentElement = frame.contentDocument.documentElement;
            const body = frame.contentDocument.body;

            if (!documentElement || !body) {
                return 0;
            }

            return Math.max(
                documentElement.scrollHeight,
                documentElement.offsetHeight,
                body.scrollHeight,
                body.offsetHeight
            );
        } catch (error) {
            return 0;
        }
    }

    function autoSize(frame) {
        let resizeObserver = null;

        function update() {
            const height = frameHeight(frame);

            if (height > 0) {
                frame.style.height = Math.ceil(height) + 'px';
            }
        }

        update();

        if ('ResizeObserver' in window) {
            try {
                resizeObserver = new ResizeObserver(update);
                resizeObserver.observe(frame.contentDocument.documentElement);
                resizeObserver.observe(frame.contentDocument.body);
            } catch (error) {
                resizeObserver = null;
            }
        }

        window.setTimeout(update, 150);
        window.setTimeout(update, 600);
        window.setTimeout(update, 1500);
        window.setTimeout(update, 3000);
    }

    document.querySelectorAll('iframe.landing-auto-frame').forEach(function (frame) {
        frame.addEventListener('load', function () {
            autoSize(frame);
        });

        // The frame can already be loaded when this script runs.
        if (frame.contentDocument
                && frame.contentDocument.readyState === 'complete') {
            autoSize(frame);
        }
    });
})();
