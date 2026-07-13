"""Capture recording storage planning and validation."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# 采集存储相关异常，当录制位置不可用时抛出
class CaptureStorageError(ValueError):
    """Raised when a requested capture location cannot be used safely."""


@dataclass(frozen=True)
class CaptureStoragePlan:
    # 采集存储规划：包含根目录、捕获目录、会话目录及所有子目录路径
    storage_root: Path
    captures_root: Path
    take_dir: Path
    media_dir: Path
    fragments_dir: Path
    metadata_dir: Path
    timeline_dir: Path
    analysis_dir: Path

    @property
    def logical_session_dir(self) -> str:
        # 返回采集会话目录的字符串路径
        return str(self.take_dir)


# 根据会话目录路径构造存储规划
def capture_storage_plan_from_dir(session_dir: str | os.PathLike[str]) -> CaptureStoragePlan:
    take_dir = _absolute(Path(session_dir))
    captures_root = take_dir.parent.parent
    storage_root = captures_root.parent
    return CaptureStoragePlan(
        storage_root=storage_root,
        captures_root=captures_root,
        take_dir=take_dir,
        media_dir=take_dir / "media",
        fragments_dir=take_dir / "fragments",
        metadata_dir=take_dir / "metadata",
        timeline_dir=take_dir / "timeline",
        analysis_dir=take_dir / "analysis",
    )


# 将路径转换为绝对路径并展开用户目录（~）
def _absolute(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


# 判断路径是否为有效的采集会话目录（父目录符合日期格式且祖父目录名为 captures）
def _is_take_dir(path: Path) -> bool:
    return bool(_DATE_RE.match(path.parent.name)) and path.parent.parent.name == "captures"


# 规范化存储根目录，返回 (根目录, captures 目录) 元组
def normalize_storage_root(storage_root: str | os.PathLike[str] | None, settings: Settings | None = None) -> tuple[Path, Path]:
    settings = settings or get_settings()
    selected = _absolute(Path(storage_root) if storage_root else settings.resolved_recordings_dir)
    if _is_take_dir(selected):
        raise CaptureStorageError("请选择录制根目录或 captures 目录，不能选择某次录制目录")

    if selected.name == "captures":
        captures_root = selected
        root = selected.parent
    else:
        root = selected
        captures_root = selected / "captures"
    return root, captures_root


# 检查目录是否可写，不可写则抛出 CaptureStorageError
def _check_writable_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".capture-write-test-", dir=path, delete=True):
            pass
    except OSError as exc:
        raise CaptureStorageError(f"录制位置不可写：{path} ({exc})") from exc


# 验证存储根目录：检查可写性及剩余空间是否充足
def validate_storage_root(
    storage_root: str | os.PathLike[str] | None,
    *,
    min_free_space_bytes: int | None = None,
    settings: Settings | None = None,
) -> tuple[Path, Path]:
    settings = settings or get_settings()
    root, captures_root = normalize_storage_root(storage_root, settings)
    _check_writable_directory(root)
    _check_writable_directory(captures_root)
    required = settings.capture_min_free_space_bytes if min_free_space_bytes is None else min_free_space_bytes
    try:
        free = shutil.disk_usage(captures_root).free
    except OSError as exc:
        raise CaptureStorageError(f"无法读取录制位置剩余空间：{captures_root} ({exc})") from exc
    if free < required:
        raise CaptureStorageError(
            f"录制位置剩余空间不足：可用 {free // (1024 * 1024)} MB，至少需要 {required // (1024 * 1024)} MB"
        )
    return root, captures_root


# 创建采集会话的完整存储规划：验证根目录、生成日期目录及所有子目录
def create_capture_storage_plan(
    capture_take_id: str,
    storage_root: str | os.PathLike[str] | None,
    *,
    started_at: datetime | None = None,
    settings: Settings | None = None,
) -> CaptureStoragePlan:
    root, captures_root = validate_storage_root(storage_root, settings=settings)
    date_name = (started_at or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d")
    take_dir = captures_root / date_name / capture_take_id
    if take_dir.exists() and any(take_dir.iterdir()):
        raise CaptureStorageError(f"录制会话目录已存在且非空：{take_dir}")
    directories = {
        "media": take_dir / "media",
        "fragments": take_dir / "fragments",
        "metadata": take_dir / "metadata",
        "timeline": take_dir / "timeline",
        "analysis": take_dir / "analysis",
    }
    try:
        for directory in directories.values():
            directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CaptureStorageError(f"无法创建录制会话目录：{take_dir} ({exc})") from exc
    return CaptureStoragePlan(
        storage_root=root,
        captures_root=captures_root,
        take_dir=take_dir,
        media_dir=directories["media"],
        fragments_dir=directories["fragments"],
        metadata_dir=directories["metadata"],
        timeline_dir=directories["timeline"],
        analysis_dir=directories["analysis"],
    )


# 原子写入 JSON 文件：先写入临时文件再重命名为目标路径
def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(temp_path, path)


# 写入采集会话元数据（清单 manifest + 会话信息 session）
def write_capture_metadata(plan: CaptureStoragePlan, *, manifest: dict[str, Any], session: dict[str, Any] | None = None) -> None:
    write_json_atomic(plan.take_dir / "manifest.json", manifest)
    if session is not None:
        write_json_atomic(plan.metadata_dir / "recording_session.json", session)


# 检查采集会话目录是否可用（存在且可写）
def capture_storage_is_available(session_dir: str | None) -> bool:
    if not session_dir:
        return True
    path = Path(session_dir)
    try:
        if not path.is_dir():
            return False
        with tempfile.NamedTemporaryFile(prefix=".capture-health-", dir=path, delete=True):
            pass
        return True
    except OSError:
        return False
