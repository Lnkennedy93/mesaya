@echo off
rem Desarrollo local: backend en backend\ con SQLite y la demo. Nunca usa la base de produccion del .env.
cd /d %~dp0
if not exist .venv ( python -m venv .venv && .venv\Scripts\pip install -r backend\requirements.txt )
cd backend
set "MESAYA_DATABASE_URL= "
if not exist data\mesaya.db ..\.venv\Scripts\python seed.py
set MESAYA_DEMO=1
start http://localhost:8000
..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
