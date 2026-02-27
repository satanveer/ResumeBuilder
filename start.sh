#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_PYTHON=""

cleanup() {
  echo
  echo "Stopping frontend and backend..."
  if [[ -f "$BACKEND_PID_FILE" ]]; then
    kill "$(cat "$BACKEND_PID_FILE")" 2>/dev/null || true
  fi
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    kill "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null || true
  fi
  jobs -pr | xargs -r kill 2>/dev/null || true
  wait || true
  rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"
}

trap cleanup EXIT INT TERM

mkdir -p "$RUN_DIR"

start_backend() {
  cd "$ROOT_DIR/backend"

  if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
    BACKEND_PYTHON="$ROOT_DIR/backend/.venv/bin/python"
  elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    BACKEND_PYTHON="$ROOT_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    BACKEND_PYTHON="$(command -v python3)"
  else
    echo "No Python interpreter found for backend."
    return 1
  fi

  if ! "$BACKEND_PYTHON" -c "import flask" >/dev/null 2>&1; then
    echo "Flask not found in selected Python environment. Installing backend requirements..."
    "$BACKEND_PYTHON" -m pip install -r requirements.txt
  fi

  PORT=5001 PYTHONUNBUFFERED=1 "$BACKEND_PYTHON" -u app.py
}

start_frontend() {
  cd "$ROOT_DIR/frontend"
  npm run dev
}

echo "Starting backend on http://localhost:5001 ..."
start_backend &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"

echo "Starting frontend on http://localhost:5173 ..."
start_frontend &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"

wait "$BACKEND_PID" "$FRONTEND_PID"
