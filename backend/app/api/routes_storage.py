"""Local storage directory picker and validation endpoints."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.capture_storage_service import CaptureStorageError, validate_storage_root

router = APIRouter(prefix="/api/storage", tags=["storage"])


class StoragePathRequest(BaseModel):
    """存储路径验证请求体。"""

    path: str


# 调用系统原生目录选择器，返回用户选择的路径（失败返回 None）
def _run_picker() -> str | None:
    system = platform.system()
    if system == "Darwin":
        result = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose folder with prompt "选择录制保存位置")'],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
    if system == "Windows":
        script = "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; if($d.ShowDialog() -eq 'OK'){ $d.SelectedPath }"  # noqa: E501
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=120, check=False
        )
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
    for command in ("zenity", "kdialog"):
        if shutil.which(command):
            args = (
                [command, "--file-selection", "--directory", "--title=选择录制保存位置"]
                if command == "zenity"
                else [command, "--getexistingdirectory", str(Path.home())]
            )
            result = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)
            return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
    raise RuntimeError("当前系统没有可用的原生目录选择器")


@router.get("/default")
def get_default_storage() -> dict[str, str]:
    """获取系统默认存储根目录。"""
    from app.core.config import get_settings

    return {"storage_root": str(get_settings().resolved_recordings_dir), "source": "default"}


@router.post("/pick")
def pick_storage() -> dict[str, str | bool]:
    """打开系统原生目录选择器让用户选择存储路径。"""
    try:
        selected = _run_picker()
        if not selected:
            return {"canceled": True, "storage_root": ""}
        root, captures = validate_storage_root(selected)
        return {"canceled": False, "storage_root": str(root), "captures_root": str(captures)}
    except (CaptureStorageError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=503, detail=f"无法打开本地目录选择器：{exc}") from exc


@router.post("/validate")
def validate_storage(payload: StoragePathRequest) -> dict[str, str]:
    """验证指定存储路径是否有效。"""
    try:
        root, captures = validate_storage_root(payload.path)
        return {"storage_root": str(root), "captures_root": str(captures)}
    except CaptureStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
