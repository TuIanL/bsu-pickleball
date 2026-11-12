"""Shareable export, deep verification and required/optional separation.

Covers 3.2: reference integrity, shareable filtering, tampered digests, and the
difference between a missing optional asset and a missing required one.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.research_evidence.builder import (
    BuildError,
    export_shareable_package,
    verify_package,
)
from app.research_evidence.cli import EXIT_OK, main

MP4_HEADER = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"

BASELINE = {
    "selected_revision": {
        "label": "selected_baseline",
        "status": "known",
        "commit": "bd136d661bf391104b9193752f7c868878e63a48",
        "worktree_clean": True,
        "dirty_patch": {
            "status": "known",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        "note": None,
    },
    "reference_revisions": [],
}


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override the plugin factory: its numbered mkdir collides with the sandbox shim."""
    with tempfile.TemporaryDirectory(prefix="pe-share-") as tmp:
        yield Path(tmp)


def _write_config(tmp_path: Path, root: Path, assets: list[dict]) -> Path:
    config = {
        "package_id": "pkg_0123456789ab",
        "source_roots": [
            {
                "root_id": "root_captures",
                "path": str(root),
                "source_kind": "external_disk",
            }
        ],
        "assets": assets,
        "baseline": BASELINE,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def _default_assets() -> list[dict]:
    return [
        {
            "root_id": "root_captures",
            "relative_path": "clip.mp4",
            "kind": "source_video",
            "usage_kind": "real",
            "requirement": "required",
        }
    ]


def _build(tmp_path: Path, assets: list[dict] | None = None) -> tuple[Path, Path]:
    root = tmp_path / "source"
    root.mkdir()
    (root / "clip.mp4").write_bytes(MP4_HEADER + b"\x00" * 256)
    config = _write_config(tmp_path, root, assets or _default_assets())
    output = tmp_path / "out"
    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK
    return root, output


# --- shareable export -------------------------------------------------------


def test_publish_excludes_the_local_mapping(tmp_path):
    _root, package = _build(tmp_path)
    share = tmp_path / "share"

    export_shareable_package(package, share)

    assert (share / "manifest.json").is_file()
    assert (share / "checks.json").is_file()
    assert not (share / "locations.local.json").exists()


def test_shareable_package_verifies_without_a_local_mapping(tmp_path):
    _root, package = _build(tmp_path)
    share = tmp_path / "share"
    export_shareable_package(package, share)

    report = verify_package(share, require_locations=False)

    assert report.ok, [check for check in report.failures]


def test_local_package_requires_the_local_mapping(tmp_path):
    _root, package = _build(tmp_path)
    (package / "locations.local.json").unlink()

    report = verify_package(package)

    assert any(check.name == "locations_present" for check in report.failures)


def test_publish_refuses_a_manifest_with_an_absolute_path(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    poisoned = {
        "assets": [{"asset_id": "a_x", "notes": ["从 /Volumes/Elements/项目 复制"]}]
    }
    (package / "manifest.json").write_text(
        json.dumps(poisoned, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(BuildError, match="绝对路径"):
        export_shareable_package(package, tmp_path / "share")


def test_publish_refuses_to_overwrite(tmp_path):
    _root, package = _build(tmp_path)
    share = tmp_path / "share"
    export_shareable_package(package, share)

    with pytest.raises(BuildError, match="拒绝覆写"):
        export_shareable_package(package, share)


# --- deep verification ------------------------------------------------------


def test_deep_verify_passes_on_an_untouched_package(tmp_path):
    _root, package = _build(tmp_path)

    report = verify_package(package, deep=True)

    assert report.ok, [check for check in report.failures]


def test_deep_verify_detects_changed_content(tmp_path):
    root, package = _build(tmp_path)
    # 同长度不同内容：size 与 mtime 之外，只有摘要能发现改动。
    (root / "clip.mp4").write_bytes(MP4_HEADER + b"\xff" * 256)

    report = verify_package(package, deep=True)

    assert any(check.name == "deep_digest_match" for check in report.failures)


def test_deep_verify_separates_missing_files_from_changed_files(tmp_path):
    root, package = _build(tmp_path)
    (root / "clip.mp4").unlink()

    report = verify_package(package, deep=True)
    failed = {check.name for check in report.failures}

    assert "deep_assets_readable" in failed
    assert "deep_digest_match" not in failed


# --- reference integrity ----------------------------------------------------


def test_dangling_reference_is_reported(tmp_path):
    _root, package = _build(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_refs"] = [
        {
            "run_id": "job-0000000001",
            "origin": "product_job",
            "code_revision": BASELINE["selected_revision"],
            "consumes": ["a_missing_asset"],
            "range": {
                "start_seconds": 0,
                "end_seconds": 1,
                "frame_start": None,
                "frame_end": None,
                "time_base": "cfr_nominal",
            },
            "algorithm_verdict": {
                "result": "unknown",
                "scope": "test",
                "recorded_source": "none",
            },
        }
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    report = verify_package(package)

    assert any(check.name == "references_resolve" for check in report.failures)


# --- required versus optional ----------------------------------------------


def test_missing_required_asset_contradicts_a_complete_claim(tmp_path):
    assets = _default_assets() + [
        {
            "root_id": "root_captures",
            "relative_path": "absent.mp4",
            "kind": "job_artifact",
            "usage_kind": "unknown",
            "requirement": "required",
            "asset_id": "a_absent_required",
        }
    ]
    _root, package = _build(tmp_path, assets)

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completeness"] == "partial"

    # 手工把声明改成 complete，校验必须拒绝。
    manifest["completeness"] = "complete"
    manifest["limitations"] = []
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    report = verify_package(package)
    failed = {check.name for check in report.failures}

    assert "completeness_consistent" in failed


def test_missing_optional_asset_keeps_the_package_complete(tmp_path):
    assets = _default_assets() + [
        {
            "root_id": "root_captures",
            "relative_path": "absent-optional.mp4",
            "kind": "job_artifact",
            "usage_kind": "unknown",
            "requirement": "optional",
            "asset_id": "a_absent_optional",
        }
    ]
    _root, package = _build(tmp_path, assets)

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    report = verify_package(package)

    assert manifest["completeness"] == "complete"
    assert not any(
        check.name == "completeness_consistent" for check in report.failures
    )
