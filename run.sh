#!/usr/bin/env bash
# ./run.sh        dev: backend (auto-reload) on :8787 + Vite on :5173; Ctrl+C stops both
# ./run.sh serve  build the frontend, then one process serving everything on :8787
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-dev}" in
  dev)
    trap 'kill 0' EXIT INT TERM
    (cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload) &
    (cd frontend && npm run dev) &
    wait
    ;;
  serve)
    (cd frontend && npm run build)
    cd backend && exec uv run python -m app
    ;;
  *)
    echo "usage: $0 [dev|serve]" >&2
    exit 1
    ;;
esac
