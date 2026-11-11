"""Attach local photographs to the spots that do not have one.

The command reads a folder of images, compares the name of every file
with the name of the spots and, when they match, uploads the file and
saves it as the cover photograph of the spot.

The comparison ignores the accents, the punctuation and the words that
do not describe a place, so ``unidad_deportiva_tabachines.jpg`` matches
``SkatePark Tabachines`` and ``skatepark_roar.jpg`` matches
``Skatepark ROAR``.

Usage::

    python manage.py assign_spot_images --folder static/images
    python manage.py assign_spot_images --folder static/images --dry-run
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from skate.models import Spots

# The words that are too common to identify a place.
IGNORED_WORDS = {
    'skate', 'skatepark', 'skateparks', 'parque', 'park', 'spot',
    'spots', 'de', 'del', 'la', 'las', 'los', 'el', 'y', 'and',
    'the', 'gdl', 'guadalajara', 'mexico', 'mx', 'by', 'image',
    'photo', 'foto', 'fotos', 'img', 'dsc', 'jpg', 'jpeg', 'png',
    'webp',
}

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def normalise(text: str) -> List[str]:
    """Return the meaningful words of a text, without accents."""
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(char for char in text if not unicodedata.combining(char))
    words = []
    for word in ''.join(char if char.isalnum() else ' ' for char in text.lower()).split():
        if word in IGNORED_WORDS or len(word) < 3:
            continue
        words.append(word)
    return words


def best_match(file_name: str, spots: List[Spots]) -> Optional[Tuple[Spots, int]]:
    """Return the spot whose name matches the name of the file best.

    Every meaningful word of the name of the spot has to be found in
    the name of the file, either as a word or inside it, so the words
    that the file adds, like ``unidad_deportiva``, do not stop the
    match and the photographs are never mixed up.
    """
    stem = Path(file_name).stem
    file_words = set(normalise(stem))
    file_text = ''.join(file_words)
    if not file_words:
        return None

    matches: List[Tuple[Spots, int]] = []

    for spot in spots:
        spot_words = set(normalise(spot.name_spot))
        if not spot_words:
            continue

        score = 0
        for word in spot_words:
            if word in file_words or word in file_text:
                score += 1

        if score == len(spot_words):
            matches.append((spot, score))

    if not matches:
        return None

    # Two spots with the same name would share the photograph, so the
    # ambiguous files are left alone.
    best_score = max(score for _spot, score in matches)
    best = [spot for spot, score in matches if score == best_score]
    if len(best) != 1:
        return None

    return best[0], best_score


class Command(BaseCommand):
    help = 'Attach the local photographs to the spots with the same name.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--folder',
            default='static/images',
            help='Folder with the photographs, relative to the project.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without changing anything.',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Replace the photograph of the spots that already have one.',
        )

    def handle(self, *args, **options):
        folder = Path(options['folder'])
        if not folder.is_dir():
            raise CommandError('The folder %s does not exist.' % folder)

        files = sorted(
            path for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not files:
            self.stdout.write('There are no photographs in %s.' % folder)
            return

        spots = list(Spots.objects.all())

        created = 0
        skipped = 0
        unmatched: List[str] = []

        for path in files:
            match = best_match(path.name, spots)
            if match is None:
                unmatched.append(path.name)
                continue

            spot, _score = match
            if spot.image_url and not options['overwrite']:
                self.stdout.write(
                    'Skipped %s: %s already has a photograph.' % (path.name, spot.name_spot)
                )
                skipped += 1
                continue

            if options['dry_run']:
                self.stdout.write(
                    'Would attach %s to %s.' % (path.name, spot.name_spot)
                )
                continue

            data = path.read_bytes()
            name = default_storage.save(
                'media/' + path.name,
                ContentFile(data),
            )
            spot.image_url.name = name
            spot.save(update_fields=['image_url'])
            created += 1
            self.stdout.write(
                self.style.SUCCESS(
                    'Attached %s to %s.' % (path.name, spot.name_spot)
                )
            )

        self.stdout.write('')
        self.stdout.write('Attached: %d, skipped: %d.' % (created, skipped))
        if unmatched:
            self.stdout.write(
                'Without a matching spot: %s' % ', '.join(unmatched)
            )
