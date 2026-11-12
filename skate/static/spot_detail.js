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

    /**
     * The id of the rider of the session of the browser.
     *
     * The token of the session is a JWT, so the id of the user is read
     * from its payload. The answer is null when there is no session or
     * when the token can not be read.
     */
    function sessionUserId() {
        const access = localStorage.getItem('access');
        if (!access) {
            return null;
        }
        try {
            const payload = access.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
            const claims = JSON.parse(atob(payload));
            return claims.user_id ? String(claims.user_id) : null;
        } catch (error) {
            return null;
        }
    }

    /**
     * Show the delete button only on the photographs the visitor
     * uploaded. The API refuses the deletion of the photographs of
     * somebody else anyway, this only keeps the page honest.
     */
    function refreshDeleteButtons() {
        const id = sessionUserId();
        document.querySelectorAll('.photo-delete').forEach(function (button) {
            const owner = button.getAttribute('data-uploaded-by');
            button.hidden = !id || !owner || String(owner) !== id;
        });
    }

    // ------------------------------------------------------------------
    // Photo upload
    // ------------------------------------------------------------------

    const photoForm = document.getElementById('photo-upload-form');
    const photoStatus = document.getElementById('photo-status');
    const photoLoginNote = document.getElementById('photo-login-note');

    // The session lives in the browser, so the server does not know who
    // is reading the page. The form is shown to the visitors that have
    // a token and the note is shown to the ones that do not.
    if (photoForm) {
        photoForm.hidden = !token;
    }
    if (photoLoginNote) {
        photoLoginNote.hidden = !!token;
    }

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
                        '<img src="' + result.data.image + '" alt="' +
                        (result.data.caption || 'Photo') + '">' +
                        (result.data.caption
                            ? '<span class="photo-caption">' + result.data.caption + '</span>'
                            : '') +
                        '<button type="button" class="photo-delete" data-photo-id="' +
                        result.data.id + '" data-uploaded-by="' +
                        (result.data.uploaded_by || '') + '" title="Delete">&times;</button>';
                    grid.insertBefore(item, grid.firstChild);
                    refreshDeleteButtons();

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
            }
        })
        .then(function (response) {
            if (response.ok) {
                button.closest('.spot-photo-item').remove();
                return;
            }
            if (response.status === 401 || response.status === 403) {
                localStorage.removeItem('access');
                localStorage.removeItem('refresh');
                window.location.href = '/profile/';
            }
        });
});

    // ------------------------------------------------------------------
    // Delete the cover photo (only the owner or an admin can)
    // ------------------------------------------------------------------

    document.addEventListener('click', function (event) {
        const button = event.target.closest('.cover-delete');
        if (!button) {
            return;
        }

        if (!token) {
            return;
        }

        if (!confirm('¿Eliminar la foto de portada?')) {
            return;
        }

        const id = button.getAttribute('data-spot-id') || spotId;

        fetch('/api/spots/' + id + '/', {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token,
                'Accept': 'application/json',
            },
            body: JSON.stringify({ image_url: null }),
        })
            .then(function (response) {
                if (response.ok) {
                    location.reload();
                    return;
                }
                if (response.status === 401 || response.status === 403) {
                    localStorage.removeItem('access');
                    localStorage.removeItem('refresh');
                    window.location.href = '/profile/';
                }
            });
    });

    // The delete buttons are shown only to the uploader of the photo.
    refreshDeleteButtons();

    // ------------------------------------------------------------------
    // Rating
    // ------------------------------------------------------------------

    const ratingSection = document.getElementById('rating-section');
    const ratingAverage = document.getElementById('rating-average');
    const ratingForm = document.getElementById('rating-form');
    const ratingLoginNote = document.getElementById('rating-login-note');
    const ratingStarsBox = document.getElementById('rating-stars');
    const ratingComment = document.getElementById('rating-comment');
    const ratingSubmit = document.getElementById('rating-submit');
    const ratingDelete = document.getElementById('rating-delete');
    const ratingStatus = document.getElementById('rating-status');
    const ratingScore = document.getElementById('rating-score');
    const ratingCurrent = document.getElementById('rating-current');
    const ratingList = document.getElementById('rating-list');

    if (ratingSection && window.RollingUpRating) {
        const spot = {
            id: ratingSection.dataset.spotId,
            average: ratingSection.dataset.average || '',
            count: Number(ratingSection.dataset.count || 0),
            userScore: ratingSection.dataset.userScore || '',
            userComment: ratingSection.dataset.userComment || '',
        };

        let score = Number(spot.userScore) || 0;
        let myRatingId = null;

        // ------------------------------------------------------------------
        // The average of the spot
        // ------------------------------------------------------------------

        function paintAverage() {
            ratingAverage.innerHTML = '';
            ratingAverage.appendChild(
                window.RollingUpRating.createReadOnly(spot.average, spot.count)
            );
        }

        // ------------------------------------------------------------------
        // The stars of the visitor
        // ------------------------------------------------------------------

        const stars = window.RollingUpRating.createInteractive({
            value: score,
            label: 'Califica este spot',
            onSelect: function (value) {
                score = value;
            },
        });
        ratingStarsBox.appendChild(stars);

        ratingComment.value = spot.userComment || '';
        ratingCurrent.hidden = !score;

        function paintCurrent() {
            ratingScore.textContent = score ? score : '';
            ratingCurrent.hidden = !score;
            ratingDelete.hidden = !score;
        }

        paintCurrent();

        // ------------------------------------------------------------------
        // The list of the ratings
        // ------------------------------------------------------------------

        function paintList(ratings) {
            ratingList.innerHTML = '';

            if (!ratings.length) {
                const empty = document.createElement('p');
                empty.className = 'spot-no-photos';
                empty.textContent = 'Todavía no hay calificaciones.';
                ratingList.appendChild(empty);
                return;
            }

            ratings.forEach(function (rating) {
                const item = document.createElement('article');
                item.className = 'spot-rating-item';

                const head = document.createElement('div');
                head.className = 'spot-rating-item-head';

                const user = document.createElement('span');
                user.className = 'spot-rating-item-user';
                user.textContent = rating.user_username || 'Rider';
                head.appendChild(user);

                const value = document.createElement('span');
                value.className = 'spot-rating-item-score';
                value.textContent = window.RollingUpRating.formatScore(rating.score);
                head.appendChild(value);

                const date = document.createElement('span');
                date.className = 'spot-rating-item-date';
                date.textContent = formatDate(rating.created_at);
                head.appendChild(date);

                item.appendChild(head);

                if (rating.comment) {
                    const comment = document.createElement('p');
                    comment.className = 'spot-rating-item-comment';
                    comment.textContent = rating.comment;
                    item.appendChild(comment);
                }

                ratingList.appendChild(item);
            });
        }

        function formatDate(value) {
            if (!value) {
                return '';
            }
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) {
                return '';
            }
            return date.toLocaleDateString('es-MX', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
            });
        }

        function loadRatings() {
            return fetch('/api/spots/' + spot.id + '/ratings/?limit=50', {
                headers: { 'Accept': 'application/json' },
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('HTTP ' + response.status);
                    }
                    return response.json();
                })
                .then(function (data) {
                    const ratings = Array.isArray(data.results) ? data.results : [];
                    const mine = ratings.filter(isMine);

                    if (mine.length) {
                        myRatingId = mine[0].id;
                        score = Number(mine[0].score) || 0;
                        spot.userScore = score;
                        spot.userComment = mine[0].comment || '';
                        ratingComment.value = spot.userComment;
                        stars.setScore(score);
                        paintCurrent();
                    }

                    paintList(ratings);
                })
                .catch(function () {
                    // The list is extra, the page works without it.
                });
        }

        /** The id of the rider of the session of the browser. */
        function isMine(rating) {
            const id = sessionUserId();
            if (!id) {
                return false;
            }
            return rating.user !== undefined && String(rating.user) === id;
        }

        // ------------------------------------------------------------------
        // The session of the visitor
        // ------------------------------------------------------------------

        if (token) {
            ratingForm.hidden = false;
            ratingLoginNote.hidden = true;
        } else {
            ratingForm.hidden = true;
            ratingLoginNote.hidden = false;
        }

        // ------------------------------------------------------------------
        // Saving the rating
        // ------------------------------------------------------------------

        function setStatus(message, kind) {
            ratingStatus.textContent = message;
            ratingStatus.className = 'spot-form-status' + (kind ? ' is-' + kind : '');
        }

        function setLoading(loading) {
            ratingSubmit.disabled = loading;
            ratingSubmit.textContent = loading ? 'Guardando...' : 'Guardar calificación';
        }

        if (ratingSubmit) {
            ratingSubmit.addEventListener('click', function () {
                if (!token) {
                    window.location.href = '/profile/';
                    return;
                }

                if (!score) {
                    setStatus('Elige cuántas estrellas le pones.', 'error');
                    return;
                }

                const comment = (ratingComment.value || '').trim();
                const previousScore = Number(spot.userScore) || 0;

                // The update is done first and it is corrected if the
                // answer of the server is not the one that was asked for.
                spot.userScore = score;
                spot.userComment = comment;
                paintCurrent();
                setStatus('');
                setLoading(true);

                fetch('/api/spots/' + spot.id + '/rate/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token,
                        'Accept': 'application/json',
                    },
                    body: JSON.stringify({ score: score, comment: comment }),
                })
                    .then(function (response) {
                        if (response.status === 401 || response.status === 403) {
                            localStorage.removeItem('access');
                            localStorage.removeItem('refresh');
                            window.location.href = '/profile/';
                            return null;
                        }
                        if (response.status === 400) {
                            return response.json().then(function (data) {
                                return { error: readError(data) };
                            });
                        }
                        if (!response.ok) {
                            return { error: 'No se pudo guardar la calificación.' };
                        }
                        return response.json().then(function (data) {
                            return { data: data };
                        });
                    })
                    .then(function (result) {
                        if (!result) {
                            return;
                        }
                        setLoading(false);

                        if (result.error) {
                            spot.userScore = previousScore;
                            paintCurrent();
                            setStatus(result.error, 'error');
                            return;
                        }

                        myRatingId = result.data && result.data.id ? result.data.id : myRatingId;
                        setStatus('Calificación guardada.', 'success');
                        refreshAverage();
                        loadRatings();
                    })
                    .catch(function () {
                        setLoading(false);
                        spot.userScore = previousScore;
                        paintCurrent();
                        setStatus('No se pudo guardar la calificación. Inténtalo de nuevo.', 'error');
                    });
            });
        }

        function readError(data) {
            if (!data) {
                return 'La calificación no es válida.';
            }
            if (data.detail) {
                return String(data.detail);
            }
            if (data.score) {
                return Array.isArray(data.score)
                    ? data.score[0]
                    : String(data.score);
            }
            if (data.comment) {
                return Array.isArray(data.comment)
                    ? data.comment[0]
                    : String(data.comment);
            }
            return 'La calificación no es válida.';
        }

        // ------------------------------------------------------------------
        // The average, without loading the page again
        // ------------------------------------------------------------------

        function refreshAverage() {
            fetch('/api/spots/' + spot.id + '/', {
                headers: { 'Accept': 'application/json' },
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('HTTP ' + response.status);
                    }
                    return response.json();
                })
                .then(function (data) {
                    spot.average = data.rating === null ? '' : data.rating;
                    spot.count = data.rating_count || 0;
                    paintAverage();
                })
                .catch(function () {
                    // The average stays as it was.
                });
        }

        // ------------------------------------------------------------------
        // Deleting the rating of the visitor
        // ------------------------------------------------------------------

        if (ratingDelete) {
            ratingDelete.addEventListener('click', function () {
                if (!token || !myRatingId) {
                    return;
                }

                ratingDelete.disabled = true;
                setStatus('Borrando...');

                fetch('/api/rating/' + myRatingId + '/', {
                    method: 'DELETE',
                    headers: {
                        'Authorization': 'Bearer ' + token,
                        'Accept': 'application/json',
                    },
                })
                    .then(function (response) {
                        ratingDelete.disabled = false;

                        if (response.status === 401 || response.status === 403) {
                            localStorage.removeItem('access');
                            localStorage.removeItem('refresh');
                            window.location.href = '/profile/';
                            return;
                        }

                        if (!response.ok && response.status !== 404) {
                            setStatus('No se pudo borrar la calificación.', 'error');
                            return;
                        }

                        myRatingId = null;
                        spot.userScore = '';
                        spot.userComment = '';
                        ratingComment.value = '';
                        score = 0;
                        stars.setScore(0);
                        paintCurrent();
                        setStatus('Calificación borrada.', 'success');
                        refreshAverage();
                        loadRatings();
                    })
                    .catch(function () {
                        ratingDelete.disabled = false;
                        setStatus('No se pudo borrar la calificación.', 'error');
                    });
            });
        }

        paintAverage();
        loadRatings();
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
