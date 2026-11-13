@echo off
rem Starts the portfolio dashboard at http://localhost:8420 (local only).
cd /d "%~dp0"
"%~dp0..\.venv\Scripts\python.exe" -m uvicorn app:app --app-dir "%~dp0" --host 127.0.0.1 --port 8420
