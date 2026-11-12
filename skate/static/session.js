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
(function (global) {
    'use strict';

    function clearStoredSession() {
        localStorage.removeItem('access');
        localStorage.removeItem('refresh');
    }

    function isJwtExpired(token) {
        if (!token || typeof token !== 'string') {
            return true;
        }

        const parts = token.split('.');
        if (parts.length !== 3) {
            return false;
        }

        try {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
            const now = Math.floor(Date.now() / 1000);
            return typeof payload.exp === 'number' && payload.exp <= now;
        } catch (error) {
            return false;
        }
    }

    /** Whether the browser holds a valid session of the application. */
    function hasSession() {
        const token = localStorage.getItem('access');
        if (!token) {
            return false;
        }

        if (isJwtExpired(token)) {
            clearStoredSession();
            return false;
        }

        return true;
    }

    function logout(redirectTo) {
        clearStoredSession();
        if (typeof global.RollingUpSession !== 'undefined' && typeof global.RollingUpSession.refresh === 'function') {
            global.RollingUpSession.refresh();
        }
        window.location.href = redirectTo || '/profile/';
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
        clearStoredSession: clearStoredSession,
        logout: logout,
    };

    document.querySelectorAll('[data-logout-button]').forEach(function (button) {
        button.addEventListener('click', function () {
            logout(button.dataset.redirect || '/profile/');
        });
    });
})(window);
