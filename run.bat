@echo off
setlocal
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate
pip install -r backend\requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
