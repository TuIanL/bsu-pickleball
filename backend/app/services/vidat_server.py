"""Start and verify the local Nginx service that hosts Vidat."""

from __future__ import annotations

import os
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


def _is_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.5) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


def ensure_vidat_service() -> dict[str, str | bool]:
    """Ensure Vidat is reachable, starting local Nginx when needed."""
    url = vidat_url()
    if _is_ready(url):
        return {"url": url, "started": False}

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
        subprocess.Popen(
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
            return {"url": url, "started": True}
        time.sleep(0.15)
    raise VidatServiceError("Vidat 服务启动超时，请检查 Nginx 错误日志。")
