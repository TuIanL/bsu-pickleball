from pathlib import Path

import pytest

from app.services.capture_storage_service import (
    CaptureStorageError,
    create_capture_storage_plan,
    normalize_storage_root,
)


def test_existing_captures_directory_is_reused(tmp_path: Path):
    captures = tmp_path / "captures"
    root, normalized = normalize_storage_root(str(captures))
    assert root == tmp_path
    assert normalized == captures

    plan = create_capture_storage_plan("take_001", str(captures))
    assert plan.captures_root == captures
    assert plan.take_dir.parent.parent == captures
    assert (plan.take_dir / "media").is_dir()
    assert (plan.take_dir / "timeline").is_dir()


def test_take_directory_is_rejected(tmp_path: Path):
    take_dir = tmp_path / "captures" / "2026-07-12" / "take_old"
    take_dir.mkdir(parents=True)
    with pytest.raises(CaptureStorageError, match="不能选择某次录制目录"):
        normalize_storage_root(str(take_dir))


def test_same_take_id_cannot_overwrite_non_empty_directory(tmp_path: Path):
    plan = create_capture_storage_plan("take_001", str(tmp_path))
    (plan.take_dir / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CaptureStorageError, match="非空"):
        create_capture_storage_plan("take_001", str(tmp_path))
