#!/bin/sh
# First run: creates a virtual environment, installs dependencies, starts the site.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f app/static/fonts/KodeMono.ttf ] || python tools/fetch_fonts.py || true
[ -f instance/admin.json ] || python manage.py create-admin
python manage.py run
