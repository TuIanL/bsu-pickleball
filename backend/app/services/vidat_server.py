"""Start and verify the local Nginx service that hosts Vidat."""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


class VidatServiceError(RuntimeError):
    pass


def vidat_url() -> str:
    return os.getenv("PICKLEBALL_VIDAT_URL", "http://localhost:8888").rstrip("/")


def _state_path() -> Path:
    from app.core.config import get_settings

    return get_settings().resolve_path(get_settings().data_dir) / "vidat-service-state.json"


def _read_state() -> dict | None:
    path = _state_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _write_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_state() -> None:
    try:
        _state_path().unlink()
    except FileNotFoundError:
        pass


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_file_path(config_path: Path) -> Path:
    configured = os.getenv("PICKLEBALL_VIDAT_NGINX_PID")
    if configured:
        return Path(configured).expanduser()
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        config_text = ""
    match = re.search(r"^\s*pid\s+([^;]+);", config_text, re.MULTILINE)
    if match:
        candidate = Path(match.group(1).strip()).expanduser()
        return candidate if candidate.is_absolute() else config_path.parent / candidate
    if config_path.parts[:3] == ("/", "opt", "homebrew"):
        return Path("/opt/homebrew/var/run/nginx.pid")
    return config_path.with_suffix(".pid")


def _find_master_pid(config_path: Path) -> int | None:
    pid_file = _pid_file_path(config_path)
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if _pid_alive(pid):
            return pid
    except (OSError, ValueError):
        pass
    try:
        output = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    config_text = str(config_path)
    for line in output.splitlines():
        if "nginx: master process" not in line or config_text not in line:
            continue
        try:
            return int(line.strip().split(maxsplit=1)[0])
        except (IndexError, ValueError):
            return None
    return None


def _controlled_state(state: dict | None, config_path: Path | None = None) -> bool:
    if not state:
        return False
    path = config_path or Path(str(state.get("config_path", ""))).expanduser()
    pid = state.get("pid")
    if not isinstance(pid, int) or not _pid_alive(pid):
        return False
    try:
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return False
    return "nginx" in output and str(path) in output


def _is_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.5) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


def get_vidat_service_status() -> dict[str, str | bool | int | None]:
    url = vidat_url()
    state = _read_state()
    config = Path(str(state.get("config_path", ""))).expanduser() if state else None
    controlled = _controlled_state(state, config) if state else False
    ready = _is_ready(url)
    if controlled and ready:
        return {
            "url": url,
            "status": "running",
            "running": True,
            "controlled": True,
            "pid": state.get("pid"),
            "started_at": state.get("started_at"),
        }
    if ready:
        return {"url": url, "status": "uncontrolled", "running": True, "controlled": False, "pid": None}
    if state and state.get("pid") and not _pid_alive(state.get("pid")):
        return {"url": url, "status": "unknown", "running": False, "controlled": False, "pid": state.get("pid")}
    return {"url": url, "status": "stopped", "running": False, "controlled": False, "pid": None}


def ensure_vidat_service() -> dict[str, str | bool | int | None]:
    """Ensure Vidat is reachable, starting local Nginx when needed."""
    url = vidat_url()
    status = get_vidat_service_status()
    if status["status"] == "running":
        return {**status, "started": False}
    if status["status"] == "uncontrolled":
        return {**status, "started": False}

    nginx = os.getenv("PICKLEBALL_VIDAT_NGINX_BIN", "/opt/homebrew/opt/nginx/bin/nginx")
    nginx_path = Path(nginx).expanduser() if os.path.isabs(nginx) else Path(shutil.which(nginx) or "")
    if not nginx_path.is_file():
        raise VidatServiceError("未找到 Nginx。请先安装 Nginx，或配置 PICKLEBALL_VIDAT_NGINX_BIN。")

    config_path = Path(os.getenv("PICKLEBALL_VIDAT_NGINX_CONF", "/opt/homebrew/etc/nginx/nginx.conf")).expanduser()
    if not config_path.is_file():
        raise VidatServiceError(f"未找到 Vidat 服务配置：{config_path}")

    checked = subprocess.run(
        [str(nginx_path), "-t", "-c", str(config_path)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if checked.returncode != 0:
        detail = (checked.stderr or checked.stdout).strip().splitlines()
        raise VidatServiceError(f"Vidat 服务配置检查失败：{detail[-1] if detail else 'Nginx 配置无效'}")

    try:
        process = subprocess.Popen(
            [str(nginx_path), "-c", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VidatServiceError(f"Vidat 服务启动失败：{exc}") from exc

    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        if _is_ready(url):
            pid = _find_master_pid(config_path) or process.pid
            _write_state(
                {
                    "service": "pickleball-vidat",
                    "pid": pid,
                    "config_path": str(config_path),
                    "url": url,
                    "started_at": time.time(),
                }
            )
            return {
                "url": url,
                "started": True,
                "running": True,
                "controlled": True,
                "status": "running",
                "pid": pid,
            }
        time.sleep(0.15)
    raise VidatServiceError("Vidat 服务启动超时，请检查 Nginx 错误日志。")


def stop_vidat_service() -> dict[str, str | bool | int | None]:
    url = vidat_url()
    state = _read_state()
    if not state:
        return {"url": url, "status": "uncontrolled" if _is_ready(url) else "stopped", "stopped": False}
    config_path = Path(str(state.get("config_path", ""))).expanduser()
    if not _controlled_state(state, config_path):
        return {"url": url, "status": "uncontrolled" if _is_ready(url) else "unknown", "stopped": False}
    nginx = os.getenv("PICKLEBALL_VIDAT_NGINX_BIN", "/opt/homebrew/opt/nginx/bin/nginx")
    nginx_path = Path(nginx).expanduser() if os.path.isabs(nginx) else Path(shutil.which(nginx) or "")
    if not nginx_path.is_file():
        raise VidatServiceError("未找到 Nginx，无法停止 Vidat 服务")
    result = subprocess.run(
        [str(nginx_path), "-s", "stop", "-c", str(config_path)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise VidatServiceError(f"Vidat 服务停止失败：{detail or 'Nginx 返回非零状态'}")
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        if not _is_ready(url):
            _clear_state()
            return {"url": url, "status": "stopped", "stopped": True, "pid": state.get("pid")}
        time.sleep(0.15)
    raise VidatServiceError("Vidat 服务停止超时，请检查 Nginx 进程和错误日志")
