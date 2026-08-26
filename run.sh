#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
exec uvicorn backend.main:app --host 127.0.0.1 --port 8000
