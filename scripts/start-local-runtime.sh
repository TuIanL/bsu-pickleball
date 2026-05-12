#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
RUNTIME_DIR="$REPO_ROOT/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"

BACKEND_HOST="${PICKLEBALL_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${PICKLEBALL_BACKEND_PORT:-8000}"
FRONTEND_HOST="${PICKLEBALL_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${PICKLEBALL_FRONTEND_PORT:-5173}"
PYTHON_BIN="${PICKLEBALL_PYTHON:-$BACKEND_DIR/.venv/bin/python}"
VITE_BIN="$REPO_ROOT/node_modules/.bin/vite"

RTMPOSE_CONFIG_DEFAULT="$REPO_ROOT/models/rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py"
RTMPOSE_CHECKPOINT_DEFAULT="$REPO_ROOT/models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

say() {
  printf '%s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_number() {
  local name="$1"
  local value="$2"

  case "$value" in
    ''|*[!0-9]*)
      die "$name must be a numeric port, got '$value'"
      ;;
  esac
}

pid_is_running() {
  local pid="$1"
  local err

  [[ -n "$pid" ]] || return 1
  err="$(/bin/kill -0 "$pid" 2>&1)" && return 0
  [[ "$err" == *"Operation not permitted"* ]]
}

read_pid_file() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  tr -d '[:space:]' < "$pid_file"
}

ensure_no_recorded_process() {
  local name="$1"
  local pid_file="$2"
  local pid

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  pid="$(read_pid_file "$pid_file" || true)"
  if pid_is_running "$pid"; then
    die "$name already appears to be running with pid $pid. Run 'npm run app:stop' first."
  fi

  rm -f "$pid_file"
}

port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

ensure_port_available() {
  local name="$1"
  local port="$2"

  if port_in_use "$port"; then
    say "$name port $port is already in use:"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
    die "free port $port or set ${name}_PORT before starting."
  fi
}

tail_log() {
  local log_file="$1"
  [[ -f "$log_file" ]] || return
  say ""
  say "Last log lines from $log_file:"
  tail -n 40 "$log_file" || true
}

process_from_file_is_running() {
  local pid_file="$1"
  local pid

  pid="$(read_pid_file "$pid_file" || true)"
  pid_is_running "$pid"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local pid_file="$3"
  local log_file="$4"

  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      say "$name is ready at $url"
      return 0
    fi

    if ! process_from_file_is_running "$pid_file"; then
      say "$name exited before becoming ready."
      tail_log "$log_file"
      return 1
    fi

    sleep 1
  done

  say "$name did not become ready at $url within 60 seconds."
  tail_log "$log_file"
  return 1
}

cleanup_started_processes() {
  "$SCRIPT_DIR/stop-local-runtime.sh" >/dev/null 2>&1 || true
}

require_number "PICKLEBALL_BACKEND_PORT" "$BACKEND_PORT"
require_number "PICKLEBALL_FRONTEND_PORT" "$FRONTEND_PORT"

command -v lsof >/dev/null 2>&1 || die "lsof is required for port checks."
command -v curl >/dev/null 2>&1 || die "curl is required for readiness checks."
[[ -x "$PYTHON_BIN" ]] || die "Backend Python not found at $PYTHON_BIN. Create backend/.venv and install requirements first."
[[ -x "$VITE_BIN" ]] || die "Vite binary not found at $VITE_BIN. Run npm install first."

mkdir -p "$PID_DIR" "$LOG_DIR" "$RUNTIME_DIR/matplotlib"

ensure_no_recorded_process "Backend" "$BACKEND_PID_FILE"
ensure_no_recorded_process "Frontend" "$FRONTEND_PID_FILE"
ensure_port_available "PICKLEBALL_BACKEND" "$BACKEND_PORT"
ensure_port_available "PICKLEBALL_FRONTEND" "$FRONTEND_PORT"

PICKLEBALL_ENABLE_POSE_INFERENCE="${PICKLEBALL_ENABLE_POSE_INFERENCE:-true}"
PICKLEBALL_ENABLE_MODEL_INFERENCE="${PICKLEBALL_ENABLE_MODEL_INFERENCE:-true}"
PICKLEBALL_RTMPOSE_CONFIG_PATH="${PICKLEBALL_RTMPOSE_CONFIG_PATH:-$RTMPOSE_CONFIG_DEFAULT}"
PICKLEBALL_RTMPOSE_CHECKPOINT_PATH="${PICKLEBALL_RTMPOSE_CHECKPOINT_PATH:-$RTMPOSE_CHECKPOINT_DEFAULT}"
PICKLEBALL_RTMPOSE_DEVICE="${PICKLEBALL_RTMPOSE_DEVICE:-cpu}"
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="${TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD:-1}"
VITE_ANALYSIS_API_URL="${VITE_ANALYSIS_API_URL:-http://localhost:$BACKEND_PORT}"

if [[ "$PICKLEBALL_ENABLE_POSE_INFERENCE" == "true" || "$PICKLEBALL_ENABLE_POSE_INFERENCE" == "1" || "$PICKLEBALL_ENABLE_POSE_INFERENCE" == "yes" ]]; then
  [[ -f "$PICKLEBALL_RTMPOSE_CONFIG_PATH" ]] || die "RTMPose config not found at $PICKLEBALL_RTMPOSE_CONFIG_PATH"
  [[ -f "$PICKLEBALL_RTMPOSE_CHECKPOINT_PATH" ]] || die "RTMPose checkpoint not found at $PICKLEBALL_RTMPOSE_CHECKPOINT_PATH"
fi

: > "$BACKEND_LOG"
: > "$FRONTEND_LOG"

say "Starting Pickleball local runtime..."
say "Logs: $LOG_DIR"

(
  cd "$BACKEND_DIR"
  export MPLCONFIGDIR="${MPLCONFIGDIR:-$RUNTIME_DIR/matplotlib}"
  export PICKLEBALL_ENABLE_MODEL_INFERENCE
  export PICKLEBALL_ENABLE_POSE_INFERENCE
  export PICKLEBALL_RTMPOSE_CONFIG_PATH
  export PICKLEBALL_RTMPOSE_CHECKPOINT_PATH
  export PICKLEBALL_RTMPOSE_DEVICE
  export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD
  exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload
) > "$BACKEND_LOG" 2>&1 &
echo "$!" > "$BACKEND_PID_FILE"

(
  cd "$REPO_ROOT"
  export VITE_ANALYSIS_API_URL
  exec "$VITE_BIN" --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort
) > "$FRONTEND_LOG" 2>&1 &
echo "$!" > "$FRONTEND_PID_FILE"

if ! wait_for_url "Backend" "http://localhost:$BACKEND_PORT/health" "$BACKEND_PID_FILE" "$BACKEND_LOG"; then
  cleanup_started_processes
  exit 1
fi

if ! wait_for_url "Frontend" "http://localhost:$FRONTEND_PORT" "$FRONTEND_PID_FILE" "$FRONTEND_LOG"; then
  cleanup_started_processes
  exit 1
fi

say ""
say "Ready."
say "Frontend: http://localhost:$FRONTEND_PORT"
say "Backend:  http://localhost:$BACKEND_PORT"
say "Stop:     npm run app:stop"
