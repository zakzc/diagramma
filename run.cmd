@echo off
rem run.cmd        dev: backend (auto-reload) on :8787 + Vite on :5173, each in its own window
rem run.cmd serve  build the frontend, then one process serving everything on :8787
cd /d "%~dp0"
if /i "%~1"=="serve" goto serve
if not "%~1"=="" if /i not "%~1"=="dev" (
  echo usage: %~nx0 [dev^|serve]
  exit /b 1
)
start "diagramma backend" /d backend cmd /k uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
start "diagramma frontend" /d frontend cmd /k npm run dev
echo Open http://localhost:5173 - close the two windows to stop.
exit /b 0

:serve
pushd frontend
call npm run build
if errorlevel 1 exit /b 1
popd
cd backend
uv run python -m app
