@echo off
REM First run: creates a virtual environment, installs dependencies, starts the site.
cd /d "%~dp0"
if not exist .venv (py -3 -m venv .venv || python -m venv .venv)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist app\static\fonts\KodeMono.ttf python tools\fetch_fonts.py
if not exist instance\admin.json python manage.py create-admin
python manage.py run
pause
