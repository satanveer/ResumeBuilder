#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"

stop_pid() {
  local pid="$1"
  local name="$2"

  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 0.3
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    return 0
  fi

  return 1
}

stop_pid_file() {
  local pid_file="$1"
  local name="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name PID file not found."
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"

  if [[ -z "$pid" ]]; then
    echo "$name PID file is empty."
    rm -f "$pid_file"
    return 0
  fi

  if ! stop_pid "$pid" "$name"; then
    echo "$name process is not running (stale PID $pid)."
  fi

  rm -f "$pid_file"
}

stop_port() {
  local port="$1"
  local name="$2"

  local pids
  pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 1
  fi

  local stopped_any=1
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    stop_pid "$pid" "$name:$port"
    stopped_any=0
  done <<< "$pids"

  return "$stopped_any"
}

stop_pid_file "$BACKEND_PID_FILE" "Backend"
stop_pid_file "$FRONTEND_PID_FILE" "Frontend"

backend_port_stopped=1
frontend_port_stopped=1

if stop_port 5001 "Backend"; then
  backend_port_stopped=0
fi
if stop_port 5173 "Frontend"; then
  frontend_port_stopped=0
fi

if [[ "$backend_port_stopped" -eq 1 ]]; then
  echo "No backend listener found on port 5001."
fi
if [[ "$frontend_port_stopped" -eq 1 ]]; then
  echo "No frontend listener found on port 5173."
fi

echo "Done."
