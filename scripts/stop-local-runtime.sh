#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_DIR="$REPO_ROOT/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"

BACKEND_PORT="${PICKLEBALL_BACKEND_PORT:-8000}"
FRONTEND_PORT="${PICKLEBALL_FRONTEND_PORT:-5173}"

say() {
  printf '%s\n' "$*"
}

pid_is_running() {
  local pid="$1"
  local err

  [[ -n "$pid" ]] || return 1
  err="$(/bin/kill -0 "$pid" 2>&1)" && return 0
  [[ "$err" == *"Operation not permitted"* ]]
}

send_signal() {
  local signal="$1"
  local pid="$2"
  local err

  [[ -n "$pid" ]] || return 0
  err="$(/bin/kill "-$signal" "$pid" 2>&1)" && return 0
  say "Could not send $signal to pid $pid: $err"
  return 1
}

read_pid_file() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  tr -d '[:space:]' < "$pid_file"
}

listener_pids() {
  local port="$1"
  lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

wait_until_stopped() {
  local pid="$1"

  for _ in $(seq 1 20); do
    if ! pid_is_running "$pid"; then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

child_pids() {
  local pid="$1"
  pgrep -P "$pid" 2>/dev/null || true
}

descendant_pids() {
  local pid="$1"
  local child

  for child in $(child_pids "$pid"); do
    descendant_pids "$child"
    printf '%s\n' "$child"
  done
}

stop_recorded_process() {
  local name="$1"
  local pid_file="$2"
  local pid
  local descendants

  if [[ ! -f "$pid_file" ]]; then
    say "$name: no recorded process."
    return
  fi

  pid="$(read_pid_file "$pid_file" || true)"
  if ! pid_is_running "$pid"; then
    say "$name: stale pid $pid removed."
    rm -f "$pid_file"
    return
  fi

  say "$name: stopping pid $pid..."
  descendants="$(descendant_pids "$pid")"
  send_signal TERM "$pid" || true
  for child_pid in $descendants; do
    send_signal TERM "$child_pid" || true
  done

  if ! wait_until_stopped "$pid"; then
    say "$name: pid $pid did not stop cleanly; forcing shutdown."
    send_signal KILL "$pid" || true
    for child_pid in $descendants; do
      send_signal KILL "$child_pid" || true
    done
  fi

  if pid_is_running "$pid"; then
    say "$name: pid $pid is still running; keeping $pid_file for the next stop attempt."
    return
  fi

  rm -f "$pid_file"
}

stop_port_listeners() {
  local name="$1"
  local port="$2"
  local pid
  local pids

  if ! command -v lsof >/dev/null 2>&1; then
    return
  fi

  pids="$(listener_pids "$port")"
  # An unused port is the normal case after a clean shutdown. Explicitly
  # return success so `set -e` does not abort before checking the other port.
  [[ -n "$pids" ]] || return 0

  say "$name: stopping remaining listener(s) on port $port..."
  for pid in $pids; do
    send_signal TERM "$pid" || true
  done

  sleep 0.5
  pids="$(listener_pids "$port")"
  [[ -n "$pids" ]] || return 0

  say "$name: forcing remaining listener(s) on port $port..."
  for pid in $pids; do
    send_signal KILL "$pid" || true
  done
}

report_remaining_listener() {
  local name="$1"
  local port="$2"

  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    say "$name port $port still has a listener that was not stopped from recorded runtime state:"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
  fi
}

say "Stopping Pickleball local runtime..."
stop_recorded_process "Frontend" "$PID_DIR/frontend.pid"
stop_recorded_process "Backend" "$PID_DIR/backend.pid"

stop_port_listeners "Frontend" "$FRONTEND_PORT"
stop_port_listeners "Backend" "$BACKEND_PORT"

report_remaining_listener "Frontend" "$FRONTEND_PORT"
report_remaining_listener "Backend" "$BACKEND_PORT"

say "Done. Logs remain in $LOG_DIR"
