#!/usr/bin/env sh
# Mac / Linux: installs the Excel/PDF packages if missing, then starts the backend (which also serves the frontend).
set -e
cd "$(dirname "$0")"
python3 -c "import openpyxl, reportlab" 2>/dev/null || python3 -m pip install --user -r backend/requirements.txt || python3 -m pip install --user --break-system-packages -r backend/requirements.txt
exec python3 backend/app.py --open "$@"
