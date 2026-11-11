/**
 * The session of the visitor in the bar of the page.
 *
 * The application keeps the access token in the local storage of the
 * browser, so the server can not know who is reading the page: the
 * bar of the page is drawn for everybody and this script shows the
 * part that belongs to the visitor.
 *
 * The markup uses `data-session`:
 *
 *   data-session="in"   only when there is a session,
 *   data-session="out"  only when there is no session.
 *
 * The elements that belong to a session come with the `hidden`
 * attribute, so nothing is shown before the script runs.
 */
(function () {
    'use strict';

    /** Whether the browser holds a session of the application. */
    function hasSession() {
        return !!localStorage.getItem('access');
    }

    /** Show the part of the page that belongs to the session. */
    function applySession() {
        const logged = hasSession();

        document.body.classList.toggle('has-session', logged);

        document.querySelectorAll('[data-session]').forEach(function (element) {
            const wanted = element.getAttribute('data-session');
            element.hidden = (wanted === 'in') !== logged;
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applySession);
    } else {
        applySession();
    }

    // The page can ask for the bar to be drawn again, for example when
    // the token of the session turned out to be expired.
    global.RollingUpSession = {
        refresh: applySession,
        hasSession: hasSession,
    };
})();
