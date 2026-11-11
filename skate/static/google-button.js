// Google sign-in button state.
//
// The flow leaves this page, so the loading state only covers the
// moment before the browser navigates to Google and prevents a second
// click while the request is in flight.
(function () {
    "use strict";

    document.querySelectorAll("[data-google-button]").forEach(function (button) {
        button.addEventListener("click", function () {
            if (button.classList.contains("is-loading")) {
                return;
            }

            button.classList.add("is-loading");
            button.setAttribute("aria-busy", "true");
            button.setAttribute("aria-disabled", "true");

            var label = button.querySelector(".google-btn__label");
            if (label) {
                label.textContent = "Cargando…";
            }
        });
    });
})();
