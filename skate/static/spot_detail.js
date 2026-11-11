/**
 * Spot detail page.
 *
 * Handles uploading additional photos to a spot and rating a spot.
 * Both require the visitor to be logged in (JWT in local storage).
 */

(function () {
    'use strict';

    const spotId = document.body.dataset.spotId;
    const token = localStorage.getItem('access');

    // ------------------------------------------------------------------
    // Photo upload
    // ------------------------------------------------------------------

    const photoForm = document.getElementById('photo-upload-form');
    const photoStatus = document.getElementById('photo-status');

    if (photoForm) {
        photoForm.addEventListener('submit', function (event) {
            event.preventDefault();

            if (!token) {
                photoStatus.textContent = 'Log in to upload photos.';
                photoStatus.className = 'spot-form-status is-error';
                return;
            }

            const imageInput = document.getElementById('photo-image');
            if (!imageInput.files.length) {
                photoStatus.textContent = 'Choose a photo first.';
                photoStatus.className = 'spot-form-status is-error';
                return;
            }

            const data = new FormData();
            data.append('image', imageInput.files[0]);

            const captionInput = document.getElementById('photo-caption');
            const caption = (captionInput.value || '').trim();
            if (caption) {
                data.append('caption', caption);
            }

            const submitButton = document.getElementById('photo-submit');
            submitButton.disabled = true;
            submitButton.textContent = 'Uploading...';
            photoStatus.textContent = '';
            photoStatus.className = 'spot-form-status';

            fetch('/api/spots/' + spotId + '/photos/', {
                method: 'POST',
                headers: {
                    'Authorization': 'Bearer ' + token,
                    'Accept': 'application/json',
                },
                body: data,
            })
                .then(function (response) {
                    if (response.status === 401 || response.status === 403) {
                        photoStatus.textContent = 'Log in to upload photos.';
                        photoStatus.className = 'spot-form-status is-error';
                        submitButton.disabled = false;
                        submitButton.textContent = 'Upload';
                        return null;
                    }
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (!result) {
                        return;
                    }
                    if (!result.ok) {
                        let message = 'Could not upload the photo.';
                        if (result.data && result.data.detail) {
                            message = result.data.detail;
                        }
                        photoStatus.textContent = message;
                        photoStatus.className = 'spot-form-status is-error';
                        submitButton.disabled = false;
                        submitButton.textContent = 'Upload';
                        return;
                    }

                    photoStatus.textContent = 'Photo uploaded.';
                    photoStatus.className = 'spot-form-status is-success';
                    photoForm.reset();

                    // Add the new photo to the gallery.
                    const grid = document.querySelector('.spot-photo-grid');
                    const item = document.createElement('div');
                    item.className = 'spot-photo-item';
                    item.innerHTML =
                        '<img src="' + result.data.image_url + '" alt="' +
                        (result.data.caption || 'Photo') + '">' +
                        (result.data.caption
                            ? '<span class="photo-caption">' + result.data.caption + '</span>'
                            : '') +
                        '<button type="button" class="photo-delete" data-photo-id="' +
                        result.data.id + '" title="Delete">&times;</button>';
                    grid.insertBefore(item, grid.firstChild);

                    submitButton.disabled = false;
                    submitButton.textContent = 'Upload';
                })
                .catch(function () {
                    photoStatus.textContent = 'Could not upload the photo. Try again.';
                    photoStatus.className = 'spot-form-status is-error';
                    submitButton.disabled = false;
                    submitButton.textContent = 'Upload';
                });
        });
    }

    // ------------------------------------------------------------------
    // Delete a photo (only the uploader can delete)
    // ------------------------------------------------------------------

    document.addEventListener('click', function (event) {
        const button = event.target.closest('.photo-delete');
        if (!button) {
            return;
        }

        const photoId = button.getAttribute('data-photo-id');
        if (!token) {
            return;
        }

        if (!confirm('Delete this photo?')) {
            return;
        }

        fetch('/api/spots/' + spotId + '/photos/' + photoId + '/', {
            method: 'DELETE',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Accept': 'application/json',
            },
        })
            .then(function (response) {
                if (response.ok) {
                    button.closest('.spot-photo-item').remove();
                }
            });
    });

    // ------------------------------------------------------------------
    // Rating
    // ------------------------------------------------------------------

    const stars = document.querySelectorAll('.spot-rating-input .star');
    const ratingStatus = document.getElementById('rating-status');

    if (stars.length && ratingStatus) {
        let selectedScore = null;

        stars.forEach(function (star) {
            star.addEventListener('mouseenter', function () {
                const score = Number(star.getAttribute('data-score'));
                stars.forEach(function (s) {
                    if (Number(s.getAttribute('data-score')) <= score) {
                        s.classList.add('star-hover');
                    } else {
                        s.classList.remove('star-hover');
                    }
                });
            });

            star.addEventListener('mouseleave', function () {
                stars.forEach(function (s) {
                    s.classList.remove('star-hover');
                });
            });

            star.addEventListener('click', function () {
                if (!token) {
                    ratingStatus.textContent = 'Log in to rate this spot.';
                    ratingStatus.className = 'spot-form-status is-error';
                    return;
                }

                selectedScore = Number(star.getAttribute('data-score'));

                stars.forEach(function (s) {
                    if (Number(s.getAttribute('data-score')) <= selectedScore) {
                        s.classList.add('star-selected');
                    } else {
                        s.classList.remove('star-selected');
                    }
                });

                submitRating(selectedScore);
            });
        });

        function submitRating(score) {
            const submitButton = document.querySelector('.spot-rating-input');
            ratingStatus.textContent = 'Saving...';
            ratingStatus.className = 'spot-form-status';

            fetch('/api/spots/' + spotId + '/rating/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token,
                    'Accept': 'application/json',
                },
                body: JSON.stringify({ score: score }),
            })
                .then(function (response) {
                    if (response.status === 401 || response.status === 403) {
                        ratingStatus.textContent = 'Log in to rate this spot.';
                        ratingStatus.className = 'spot-form-status is-error';
                        return null;
                    }
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (!result) {
                        return;
                    }
                    if (!result.ok) {
                        ratingStatus.textContent = 'Could not save the rating.';
                        ratingStatus.className = 'spot-form-status is-error';
                        return;
                    }

                    ratingStatus.textContent = 'Rating saved.';
                    ratingStatus.className = 'spot-form-status is-success';

                    // Move the rating display to the "current" section.
                    const currentSection = document.querySelector('.spot-rating-current');
                    const inputSection = document.querySelector('.spot-rating-input');
                    if (currentSection && inputSection) {
                        inputSection.hidden = true;
                        currentSection.hidden = false;
                    }
                })
                .catch(function () {
                    ratingStatus.textContent = 'Could not save the rating. Try again.';
                    ratingStatus.className = 'spot-form-status is-error';
                });
        }
    }

    // ------------------------------------------------------------------
    // Map
    // ------------------------------------------------------------------

    const mapElement = document.getElementById('spot-map');
    if (mapElement && typeof L !== 'undefined') {
        const lat = Number(mapElement.dataset.lat);
        const lon = Number(mapElement.dataset.lon);
        const zoom = Number(mapElement.dataset.zoom) || 15;

        const map = L.map('spot-map', {
            center: [lat, lon],
            zoom: zoom,
            scrollWheelZoom: false,
        });

        const tileOptions = {
            maxZoom: Number(mapElement.dataset.tileMaxZoom) || 19,
            attribution: mapElement.dataset.tileAttribution,
        };

        if (mapElement.dataset.tileSubdomains) {
            tileOptions.subdomains = mapElement.dataset.tileSubdomains;
        }

        L.tileLayer(mapElement.dataset.tileUrl, tileOptions).addTo(map);

        L.marker([lat, lon]).addTo(map);

        map.on('focus', function () {
            map.scrollWheelZoom.enable();
        });
        map.on('blur', function () {
            map.scrollWheelZoom.disable();
        });
    }

    // Set the spot ID on the body for other scripts.
    if (spotId) {
        document.body.dataset.spotId = spotId;
    }

})();
