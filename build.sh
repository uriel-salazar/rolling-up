#!/usr/bin/env bash
# Build script for Render.
#
# Render runs this on every deploy, before the web service starts:
# it installs the dependencies, collects the static files and applies
# the database migrations.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# The static files (CSS, JavaScript, images) are collected into
# "staticfiles" and served by WhiteNoise.
python manage.py collectstatic --no-input

# The migrations of the database are applied.
python manage.py migrate --no-input
