@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co .venv. Xem README_HOAN_THIEN.md de cai dat.
  pause
  exit /b 1
)
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir app/backend/src --host 127.0.0.1 --port 8000 --reload
pause
