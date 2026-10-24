#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$PROJECT_ROOT/backend/.venv/bin/python" ]]; then
  echo "Backend dependencies are missing. See README.md to install them." >&2
  exit 1
fi
if [[ ! -x "$PROJECT_ROOT/frontend/node_modules/.bin/vite" ]]; then
  echo "Frontend dependencies are missing. See README.md to install them." >&2
  exit 1
fi

(cd "$PROJECT_ROOT/backend" && exec "$PROJECT_ROOT/backend/.venv/bin/python" -m app) &
BACKEND_PID=$!
(cd "$PROJECT_ROOT/frontend" && exec ./node_modules/.bin/vite --host 127.0.0.1) &
FRONTEND_PID=$!

cleanup() {
  trap - EXIT INT TERM
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting TrustVault. Keep this terminal open."
echo "When Vite says it is ready, open http://127.0.0.1:5173"
wait -n "$BACKEND_PID" "$FRONTEND_PID"
