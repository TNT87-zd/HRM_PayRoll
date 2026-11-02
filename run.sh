#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$project_dir"
exec "$project_dir/.venv/bin/python" -m uvicorn main:app --app-dir "$project_dir/app/backend/src" --host 127.0.0.1 --port 8000 --reload "$@"
