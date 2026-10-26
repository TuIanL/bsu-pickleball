"""Manage the local Windows API, worker and Vite processes.

Run with the repository's .venv/Scripts/python.exe. Configuration and credentials
are stored in ignored .env.local; process records and logs live in .runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import psutil
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
STATE = RUNTIME / "windows-processes.json"
ENV_FILE = ROOT / ".env.local"


def configuration() -> dict[str, str]:
    defaults = {
        "PICKLEBALL_API_TOKEN": secrets.token_urlsafe(32),
        "PICKLEBALL_API_PROXY_TARGET": "http://127.0.0.1:8000",
        "VITE_ANALYSIS_API_URL": "/__analysis_api",
        "PICKLEBALL_AUTH_DISABLED": "false",
        "PICKLEBALL_LOCAL_DOCS": "true",
        "PICKLEBALL_RUNTIME_DIR": RUNTIME.as_posix(),
        "PICKLEBALL_ANALYSIS_WORKER_MODE": "external",
        "PICKLEBALL_ENABLE_JOB_WORKER": "false",
        "PICKLEBALL_ANALYSIS_JOB_LOGS_ENABLED": "true",
        "PICKLEBALL_MODEL_DIR": (ROOT / "models").as_posix(),
        "PICKLEBALL_DEFAULT_DETECTOR_MODEL": (ROOT / "models/yolo11n.pt").as_posix(),
        "PICKLEBALL_ENABLE_MODEL_INFERENCE": "true",
        "PICKLEBALL_DETECTOR_DEVICE": "0",
        "PICKLEBALL_ENABLE_POSE_INFERENCE": "false",
        "PICKLEBALL_RTMPOSE_DEVICE": "cuda:0",
        "PICKLEBALL_RTMPOSE_CONFIG_PATH": (ROOT / "models/rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py").as_posix(),
        "PICKLEBALL_RTMPOSE_CHECKPOINT_PATH": (ROOT / "models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth").as_posix(),
        "PICKLEBALL_COURT_LINE_MODEL_PATH": (ROOT / "models/court-line/best.pt").as_posix(),
        "PICKLEBALL_COURT_LINE_DEVICE": "0",
        "PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED": "false",
        "PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR": (ROOT / "models/match_state").as_posix(),
        "PICKLEBALL_MATCH_STATE_SEGMENTATION_DEVICE": "cuda:0",
        "PICKLEBALL_OVERLAY_FRAME_STRIDE": "5",
        "MPLCONFIGDIR": (RUNTIME / "matplotlib").as_posix(),
        "YOLO_CONFIG_DIR": (RUNTIME / "ultralytics").as_posix(),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
    }
    if not ENV_FILE.exists():
        ENV_FILE.write_text(
            "# Local Windows settings; ignored by Git. Never put the API token in VITE_* variables.\n"
            + "\n".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in defaults.items())
            + "\n", encoding="utf-8",
        )
    configured = {key: value for key, value in dotenv_values(ENV_FILE).items() if value is not None}
    env = {**os.environ, **defaults, **configured}
    if not env["PICKLEBALL_API_TOKEN"].strip():
        raise RuntimeError("Set a nonempty PICKLEBALL_API_TOKEN in .env.local.")
    if env.get("VITE_PICKLEBALL_API_TOKEN"):
        raise RuntimeError("Remove VITE_PICKLEBALL_API_TOKEN from your local environment.")
    for name in ("logs", "matplotlib", "ultralytics"):
        (RUNTIME / name).mkdir(parents=True, exist_ok=True)
    return env


def records() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def owned_process(record: dict) -> psutil.Process | None:
    try:
        process = psutil.Process(record["pid"])
        if abs(process.create_time() - record["created"]) < 0.01:
            return process
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return None


def stop() -> None:
    for name, record in reversed(list(records().items())):
        process = owned_process(record)
        if process:
            processes = process.children(recursive=True) + [process]
            for child in reversed(processes):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(processes, timeout=5)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            print(f"Stopped {name}.")
    STATE.unlink(missing_ok=True)


def check_assets(env: dict[str, str]) -> None:
    manifest = ROOT / "models/MODEL_MANIFEST.json"
    if manifest.exists():
        for entry in json.loads(manifest.read_text(encoding="utf-8")).get("models", []):
            path = ROOT / "models" / entry["path"]
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError(f"Model checksum mismatch: {path}")
    enabled = lambda key: env.get(key, "").lower() in {"true", "1", "yes"}
    if enabled("PICKLEBALL_ENABLE_MODEL_INFERENCE"):
        path = Path(env["PICKLEBALL_DEFAULT_DETECTOR_MODEL"])
        if not path.is_file():
            raise RuntimeError(f"Detector weights missing: {path}")
        subprocess.run([sys.executable, "-c", "from ultralytics import YOLO; import torch; assert torch.cuda.is_available() or 'cpu' == __import__('os').environ.get('PICKLEBALL_DETECTOR_DEVICE'), 'CUDA unavailable; configure cpu'"] , env=env, check=True)
    if enabled("PICKLEBALL_ENABLE_POSE_INFERENCE"):
        report = subprocess.run([sys.executable, str(ROOT / "backend/scripts/validate_rtmpose.py"), "--check-only"], cwd=ROOT / "backend", env=env, capture_output=True, text=True, encoding="utf-8")
        (RUNTIME / "logs/pose-preflight.json").write_text(report.stdout, encoding="utf-8")
        state = json.loads(report.stdout)
        ready = state.get("python", {}).get("ok") and bool(state.get("dependencies")) and all(
            item.get("installed") for item in state.get("dependencies", {}).values()
        ) and state.get("assets", {}).get("config_exists") and state.get("assets", {}).get("checkpoint_exists")
        if report.returncode or not ready:
            raise RuntimeError("Pose runtime validation failed; see .runtime/logs/pose-preflight.json.")
        subprocess.run([sys.executable, "-c", "from mmpose.apis import init_model, inference_topdown"], env=env, check=True)
    if enabled("PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED"):
        report = subprocess.run([sys.executable, str(ROOT / "scripts/verify_match_state_model_package.py"), "--package-dir", env["PICKLEBALL_MATCH_STATE_SEGMENTATION_PACKAGE_DIR"], "--schema", str(ROOT / "backend/app/resources/match_state_model_package.schema.v1.json"), "--strict"], env=env, capture_output=True, text=True, encoding="utf-8")
        (RUNTIME / "logs/model-preflight.json").write_text(report.stdout, encoding="utf-8")
        if report.returncode:
            raise RuntimeError("Match-state model validation failed; see .runtime/logs/model-preflight.json.")


def start(env: dict[str, str]) -> None:
    existing = records()
    if set(existing) == {"backend", "analysis-worker", "frontend"} and all(owned_process(record) for record in existing.values()):
        print("Already running: http://127.0.0.1:5173")
        return
    if any(owned_process(record) for record in existing.values()):
        raise RuntimeError("A recorded service is running. Stop it before starting again.")
    for port in (8000, 5173):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(f"Port {port} is in use. Stop the existing service first.") from exc
    check_assets(env)
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is not on PATH.")
    commands = {
        "backend": ([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload", "--reload-dir", "app"], ROOT / "backend"),
        "analysis-worker": ([sys.executable, "-m", "app.analysis_worker"], ROOT / "backend"),
        "frontend": ([node, str(ROOT / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], ROOT),
    }
    started = {}
    try:
        for name, (command, cwd) in commands.items():
            child_env = {**env, "PICKLEBALL_ENABLE_JOB_WORKER": "true" if name == "analysis-worker" else "false"}
            if name == "frontend":
                # Vite otherwise treats a detached process's closed stdin as
                # the parent exiting and shuts down the development server.
                child_env["CI"] = "true"
            with (RUNTIME / "logs" / f"{name}.log").open("ab") as log:
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
                process = subprocess.Popen(command, cwd=cwd, env=child_env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
            started[name] = {"pid": process.pid, "created": psutil.Process(process.pid).create_time()}
            STATE.write_text(json.dumps(started, indent=2), encoding="utf-8")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for name, url in (("backend", "http://127.0.0.1:8000/health"), ("frontend", "http://127.0.0.1:5173/__analysis_api/health")):
            deadline = time.monotonic() + 60
            while True:
                if not all(owned_process(record) for record in started.values()):
                    raise RuntimeError("A service exited. See .runtime/logs/.")
                try:
                    with opener.open(url, timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"{name} did not become ready. See .runtime/logs/.")
                time.sleep(0.5)
        print("Ready: http://127.0.0.1:5173")
        print("API docs: http://127.0.0.1:8000/docs")
        print("Logs: .runtime/logs/; settings: .env.local")
        print("Worker changes require a stop/start; API and frontend reload automatically.")
    except BaseException:
        stop()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "prepare"))
    parser.add_argument("--no-models", action="store_true", help="Start the base application while model dependencies are being installed.")
    args = parser.parse_args()
    if args.action == "stop":
        stop()
    elif args.action == "status":
        for name, record in records().items():
            print(f"{name}: {'running' if owned_process(record) else 'stopped'}")
    else:
        env = configuration()
        if args.no_models:
            env.update(PICKLEBALL_ENABLE_MODEL_INFERENCE="false", PICKLEBALL_ENABLE_POSE_INFERENCE="false", PICKLEBALL_COURT_LINE_MODEL_PATH="", PICKLEBALL_MATCH_STATE_SEGMENTATION_ENABLED="false")
        if args.action == "start":
            start(env)
        else:
            print("Prepared .env.local for Windows and VS Code.")


if __name__ == "__main__":
    main()
