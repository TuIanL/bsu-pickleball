#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
RUNTIME_DIR="${PICKLEBALL_RUNTIME_DIR:-$REPO_ROOT/.runtime}"
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
COURT_LINE_MODEL_DEFAULT="$REPO_ROOT/models/court-line/best.pt"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
WORKER_PID_FILE="$PID_DIR/analysis-worker.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
WORKER_LOG="$LOG_DIR/analysis-worker.log"
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

python_has_cuda() {
  "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
try:
    import torch
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if torch.cuda.is_available() else 1)
PY
}

python_has_mps() {
  "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
try:
    import torch
except Exception:
    raise SystemExit(1)
backend = getattr(torch.backends, "mps", None)
raise SystemExit(0 if backend is not None and backend.is_available() else 1)
PY
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

wait_for_process() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"

  for _ in $(seq 1 20); do
    if process_from_file_is_running "$pid_file"; then
      say "$name is running"
      return 0
    fi
    sleep 0.25
  done

  say "$name exited during startup."
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
ensure_no_recorded_process "Analysis worker" "$WORKER_PID_FILE"
ensure_no_recorded_process "Frontend" "$FRONTEND_PID_FILE"
ensure_port_available "PICKLEBALL_BACKEND" "$BACKEND_PORT"
ensure_port_available "PICKLEBALL_FRONTEND" "$FRONTEND_PORT"

PICKLEBALL_ENABLE_POSE_INFERENCE="${PICKLEBALL_ENABLE_POSE_INFERENCE:-false}"
PICKLEBALL_ENABLE_MODEL_INFERENCE="${PICKLEBALL_ENABLE_MODEL_INFERENCE:-false}"
PICKLEBALL_ANALYSIS_WORKER_MODE="${PICKLEBALL_ANALYSIS_WORKER_MODE:-external}"
PICKLEBALL_RTMPOSE_CONFIG_PATH="${PICKLEBALL_RTMPOSE_CONFIG_PATH:-$RTMPOSE_CONFIG_DEFAULT}"
PICKLEBALL_RTMPOSE_CHECKPOINT_PATH="${PICKLEBALL_RTMPOSE_CHECKPOINT_PATH:-$RTMPOSE_CHECKPOINT_DEFAULT}"
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="${TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD:-1}"
VITE_ANALYSIS_API_URL="${VITE_ANALYSIS_API_URL:-http://localhost:$BACKEND_PORT}"

if python_has_cuda; then
  DEFAULT_COURT_LINE_DEVICE="0"
  DEFAULT_RTMPOSE_DEVICE="cuda:0"
else
  DEFAULT_COURT_LINE_DEVICE="cpu"
  DEFAULT_RTMPOSE_DEVICE="cpu"
fi

PICKLEBALL_COURT_LINE_MODEL_PATH="${PICKLEBALL_COURT_LINE_MODEL_PATH:-}"
PICKLEBALL_COURT_LINE_DEVICE="${PICKLEBALL_COURT_LINE_DEVICE:-$DEFAULT_COURT_LINE_DEVICE}"
PICKLEBALL_RTMPOSE_DEVICE="${PICKLEBALL_RTMPOSE_DEVICE:-$DEFAULT_RTMPOSE_DEVICE}"
PICKLEBALL_ENABLE_PROJECTION_DEBUG_JSONL="${PICKLEBALL_ENABLE_PROJECTION_DEBUG_JSONL:-false}"
PICKLEBALL_ENABLE_PROJECTION_DEBUG_OVERLAY="${PICKLEBALL_ENABLE_PROJECTION_DEBUG_OVERLAY:-false}"
PICKLEBALL_MAX_UPLOAD_BYTES="${PICKLEBALL_MAX_UPLOAD_BYTES:-$((20 * 1024 * 1024 * 1024))}"
PICKLEBALL_MODEL_DIR="${PICKLEBALL_MODEL_DIR:-$REPO_ROOT/models}"
PICKLEBALL_DEFAULT_DETECTOR_MODEL="${PICKLEBALL_DEFAULT_DETECTOR_MODEL:-yolo11n.pt}"
PICKLEBALL_MATCH_STATE_CANDIDATE_DIR="${PICKLEBALL_MATCH_STATE_CANDIDATE_DIR:-$REPO_ROOT/data/match_state_candidates}"
PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR="${PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR:-$REPO_ROOT/models/match_state}"
PICKLEBALL_MATCH_STATE_SEGMENTATION_REQUIRED_PROFILE="${PICKLEBALL_MATCH_STATE_SEGMENTATION_REQUIRED_PROFILE:-match_default}"
PICKLEBALL_MATCH_STATE_SEGMENTATION_BATCH_SIZE="${PICKLEBALL_MATCH_STATE_SEGMENTATION_BATCH_SIZE:-8}"
if [[ -z "${PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED+x}" ]]; then
  if [[ -f "$PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR/model_package.json" ]]; then
    PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED="true"
  else
    PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED="false"
  fi
fi
if [[ -z "${PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE+x}" ]]; then
  if python_has_cuda; then
    PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE="cuda:0"
  elif python_has_mps; then
    PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE="mps"
  else
    PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE="cpu"
  fi
fi

# CORS 白名单：默认允许 localhost / 127.0.0.1，并自动把本机局域网 IP 加进去，
# 否则通过局域网 IP 访问前端时浏览器预检被拒（表现为 fetch "Failed to fetch"）。
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
CORS_DEFAULT="http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
if [[ -n "$LAN_IP" ]]; then
  CORS_DEFAULT="$CORS_DEFAULT,http://$LAN_IP:$FRONTEND_PORT"
fi
PICKLEBALL_CORS_ORIGINS="${PICKLEBALL_CORS_ORIGINS:-$CORS_DEFAULT}"

if [[ "$PICKLEBALL_ENABLE_POSE_INFERENCE" == "true" || "$PICKLEBALL_ENABLE_POSE_INFERENCE" == "1" || "$PICKLEBALL_ENABLE_POSE_INFERENCE" == "yes" ]]; then
  [[ -f "$PICKLEBALL_RTMPOSE_CONFIG_PATH" ]] || die "RTMPose config not found at $PICKLEBALL_RTMPOSE_CONFIG_PATH"
  [[ -f "$PICKLEBALL_RTMPOSE_CHECKPOINT_PATH" ]] || die "RTMPose checkpoint not found at $PICKLEBALL_RTMPOSE_CHECKPOINT_PATH"
  "$PYTHON_BIN" - <<'PY' || die "RTMPose dependencies are not installed; install the optional pose environment first."
import importlib.util
missing = [name for name in ("torch", "mmpose", "mmengine") if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
fi

if [[ "$PICKLEBALL_ENABLE_MODEL_INFERENCE" == "true" || "$PICKLEBALL_ENABLE_MODEL_INFERENCE" == "1" || "$PICKLEBALL_ENABLE_MODEL_INFERENCE" == "yes" ]]; then
  "$PYTHON_BIN" - <<'PY' || die "Ultralytics is not installed; install the optional vision environment first."
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("ultralytics") else 1)
PY
  DETECTOR_MODEL_PATH="$PICKLEBALL_MODEL_DIR/$PICKLEBALL_DEFAULT_DETECTOR_MODEL"
  [[ -f "$DETECTOR_MODEL_PATH" ]] || die "Detector checkpoint not found at $DETECTOR_MODEL_PATH"
fi

if [[ -f "$PICKLEBALL_MODEL_DIR/MODEL_MANIFEST.json" ]]; then
  "$PYTHON_BIN" - "$PICKLEBALL_MODEL_DIR" <<'PY' || die "A local model checksum does not match MODEL_MANIFEST.json"
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / "MODEL_MANIFEST.json").read_text(encoding="utf-8"))
for entry in manifest.get("models", []):
    path = root / entry["path"]
    if not path.is_file():
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(f"checksum mismatch: {path}")
PY
fi

if [[ "$PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED" == "true" || "$PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED" == "1" || "$PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED" == "yes" ]]; then
  [[ -f "$PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR/model_package.json" ]] || die "Formal match-state package not found at $PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR"
  "$PYTHON_BIN" "$REPO_ROOT/scripts/verify_match_state_model_package.py" \
    --package-dir "$PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR" \
    --schema "$BACKEND_DIR/app/resources/match_state_model_package.schema.v1.json" \
    --strict >/dev/null || die "Formal match-state package validation failed"
  "$PYTHON_BIN" - <<'PY' || die "Formal match-state runtime dependencies are not installed."
import importlib.util
missing = [name for name in ("torch", "torchvision", "cv2", "numpy") if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
  case "$PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE" in
    cuda:*) python_has_cuda || die "Configured match-state device $PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE is unavailable" ;;
    mps) python_has_mps || die "Configured match-state device mps is unavailable" ;;
    cpu) : ;;
    *) die "Unsupported match-state device: $PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE" ;;
  esac
fi

if [[ -n "$PICKLEBALL_COURT_LINE_MODEL_PATH" ]]; then
  [[ -f "$PICKLEBALL_COURT_LINE_MODEL_PATH" ]] || die "Court-line model not found at $PICKLEBALL_COURT_LINE_MODEL_PATH"
fi

: > "$BACKEND_LOG"
: > "$WORKER_LOG"
: > "$FRONTEND_LOG"

say "Starting Pickleball local runtime..."
say "Logs: $LOG_DIR"
say "Analysis worker mode: $PICKLEBALL_ANALYSIS_WORKER_MODE"
say "Court-line model: $PICKLEBALL_COURT_LINE_MODEL_PATH"
say "Court-line device: $PICKLEBALL_COURT_LINE_DEVICE"
say "RTMPose device:    $PICKLEBALL_RTMPOSE_DEVICE"
say "Match-state package: $PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR"
say "Match-state enabled: $PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED"
say "Match-state device:  $PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE"

(
  cd "$BACKEND_DIR"
  export MPLCONFIGDIR="${MPLCONFIGDIR:-$RUNTIME_DIR/matplotlib}"
  export PICKLEBALL_ENABLE_MODEL_INFERENCE
  export PICKLEBALL_ENABLE_POSE_INFERENCE
  export PICKLEBALL_ANALYSIS_WORKER_MODE
  # API reload must never create an in-process analysis worker.
  export PICKLEBALL_ENABLE_JOB_WORKER=false
  export PICKLEBALL_ENABLE_PROJECTION_DEBUG_JSONL
  export PICKLEBALL_ENABLE_PROJECTION_DEBUG_OVERLAY
  export PICKLEBALL_MAX_UPLOAD_BYTES
  export PICKLEBALL_MODEL_DIR
  export PICKLEBALL_DEFAULT_DETECTOR_MODEL
  export PICKLEBALL_MATCH_STATE_CANDIDATE_DIR
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_REQUIRED_PROFILE
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_BATCH_SIZE
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE
  export PICKLEBALL_COURT_LINE_MODEL_PATH
  export PICKLEBALL_COURT_LINE_DEVICE
  export PICKLEBALL_RTMPOSE_CONFIG_PATH
  export PICKLEBALL_RTMPOSE_CHECKPOINT_PATH
  export PICKLEBALL_RTMPOSE_DEVICE
  export PICKLEBALL_COURT_VIEW_MATCH_THRESHOLD="${PICKLEBALL_COURT_VIEW_MATCH_THRESHOLD:-0.5}"
  export PICKLEBALL_CORS_ORIGINS
  export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD
  exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload --reload-exclude "data/*" --reload-exclude ".venv/*" --reload-exclude "yolo11n.pt"
) > "$BACKEND_LOG" 2>&1 &
echo "$!" > "$BACKEND_PID_FILE"

(
  cd "$BACKEND_DIR"
  export MPLCONFIGDIR="${MPLCONFIGDIR:-$RUNTIME_DIR/matplotlib}"
  export PICKLEBALL_ENABLE_MODEL_INFERENCE
  export PICKLEBALL_ENABLE_POSE_INFERENCE
  export PICKLEBALL_ANALYSIS_WORKER_MODE
  export PICKLEBALL_ENABLE_JOB_WORKER=true
  export PICKLEBALL_ENABLE_PROJECTION_DEBUG_JSONL
  export PICKLEBALL_ENABLE_PROJECTION_DEBUG_OVERLAY
  export PICKLEBALL_MAX_UPLOAD_BYTES
  export PICKLEBALL_MODEL_DIR
  export PICKLEBALL_DEFAULT_DETECTOR_MODEL
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_REQUIRED_PROFILE
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_BATCH_SIZE
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED
  export PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE
  export PICKLEBALL_COURT_LINE_MODEL_PATH
  export PICKLEBALL_COURT_LINE_DEVICE
  export PICKLEBALL_RTMPOSE_CONFIG_PATH
  export PICKLEBALL_RTMPOSE_CHECKPOINT_PATH
  export PICKLEBALL_RTMPOSE_DEVICE
  export PICKLEBALL_COURT_VIEW_MATCH_THRESHOLD="${PICKLEBALL_COURT_VIEW_MATCH_THRESHOLD:-0.5}"
  export PICKLEBALL_CORS_ORIGINS
  export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD
  exec "$PYTHON_BIN" -m app.analysis_worker
) > "$WORKER_LOG" 2>&1 &
echo "$!" > "$WORKER_PID_FILE"

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

if ! wait_for_process "Analysis worker" "$WORKER_PID_FILE" "$WORKER_LOG"; then
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
