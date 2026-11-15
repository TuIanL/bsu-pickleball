"""Shareable export, deep verification and required/optional separation.

Covers 3.2: reference integrity, shareable filtering, tampered digests, and the
difference between a missing optional asset and a missing required one.
"""

from __future__ import annotations

import json
import subprocess
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

_MP4_CACHE: bytes | None = None


def _real_mp4_payload() -> bytes:
    global _MP4_CACHE
    if _MP4_CACHE is None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "probe.mp4"
            completed = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=160x120:d=1",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(target),
                ],
                capture_output=True,
            )
            if completed.returncode != 0:
                pytest.skip("ffmpeg 不可用，无法生成真实媒体夹具")
            _MP4_CACHE = target.read_bytes()
    return _MP4_CACHE


def _write_real_mp4(path: Path) -> Path:
    path.write_bytes(_real_mp4_payload())
    return path

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
    _write_real_mp4(root / "clip.mp4")
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


def test_duplicate_locator_across_assets_is_rejected(tmp_path):
    """同一位置不得被两个内容资产同时登记，否则引用无法唯一解析。"""
    _root, package = _build(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = manifest["assets"][0]
    clone = json.loads(json.dumps(first))
    clone["asset_id"] = "a_cloned_asset"
    manifest["assets"].append(clone)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    report = verify_package(package)

    assert any(check.name == "unique_locators" for check in report.failures)


def test_build_records_tooling_version_and_config_digest(tmp_path):
    """索引工具版本必须与科研基线分开记录，配置摘要不得含本机路径。"""
    _root, package = _build(tmp_path)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))

    tooling = manifest["tooling"]
    assert tooling["name"] == "research_evidence"
    assert tooling["revision"]["label"] == "tooling"
    assert tooling["revision"]["status"] in {"known", "unknown"}
    assert len(tooling["config_sha256"]) == 64
    # 工具版本与分析基线必须是两个不同的对象。
    assert tooling["revision"] is not manifest["baseline"]["selected_revision"]


def test_verify_requires_a_tooling_record(tmp_path):
    _root, package = _build(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("tooling", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    report = verify_package(package)

    assert any(check.name == "tooling_recorded" for check in report.failures)


# --- 评审四项缺陷的回归 ------------------------------------------------


def _asset(
    relative_path: str,
    *,
    kind: str = "source_video",
    usage_kind: str = "real",
    requirement: str = "required",
    view_role: str = "cam1",
) -> dict:
    return {
        "root_id": "root_captures",
        "relative_path": relative_path,
        "kind": kind,
        "usage_kind": usage_kind,
        "requirement": requirement,
        "view_role": view_role,
    }


def test_dedup_keeps_each_usage_semantics(tmp_path):
    """同一内容的两处使用，用途与必需性必须各自保留，不得由 locator 排序决定。"""
    root = tmp_path / "source"
    root.mkdir()
    _write_real_mp4(root / "a.mp4")
    (root / "b.mp4").write_bytes((root / "a.mp4").read_bytes())
    config = _write_config(
        tmp_path,
        root,
        [
            _asset("a.mp4", usage_kind="real", requirement="required", view_role="cam1"),
            _asset("b.mp4", usage_kind="fixture", requirement="optional", view_role="cam2"),
        ],
    )
    output = tmp_path / "out"

    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert len(manifest["assets"]) == 1
    pairs = {
        (usage["usage_kind"], usage["requirement"])
        for usage in manifest["assets"][0]["usages"]
    }
    assert pairs == {("real", "required"), ("fixture", "optional")}


def test_fake_video_optional_is_not_marked_verified(tmp_path):
    """optional 不阻断完整性，但伪视频绝不能被标为已验证的有效媒体。"""
    root = tmp_path / "source"
    root.mkdir()
    (root / "fake.mp4").write_text("this is not a video", encoding="utf-8")
    (root / "roster.json").write_text('{"players": 4}', encoding="utf-8")
    config = _write_config(
        tmp_path,
        root,
        [
            _asset("roster.json", kind="roster", requirement="required", view_role="unspecified"),
            _asset("fake.mp4", kind="source_video", requirement="optional", view_role="unspecified"),
        ],
    )
    output = tmp_path / "out"

    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    fake = next(
        asset for asset in manifest["assets"] if asset["kind"] == "source_video"
    )
    codes = {
        (limit["code"], limit["block_completeness"])
        for limit in manifest["limitations"]
    }

    assert fake["verification"] == "mismatch"
    assert ("content_type_mismatch", False) in codes
    # optional 使用关系不阻断完整性
    assert manifest["completeness"] == "complete"


def test_deep_verify_covers_every_usage_location(tmp_path):
    """去重后的每个副本都要参与摘要核验，改掉副本必须被发现。"""
    root = tmp_path / "source"
    root.mkdir()
    _write_real_mp4(root / "a.mp4")
    (root / "b.mp4").write_bytes((root / "a.mp4").read_bytes())
    config = _write_config(
        tmp_path,
        root,
        [
            _asset("a.mp4", view_role="cam1"),
            _asset("b.mp4", view_role="cam2"),
        ],
    )
    output = tmp_path / "out"
    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    tampered = bytearray((root / "b.mp4").read_bytes())
    tampered[-1] ^= 0xFF
    (root / "b.mp4").write_bytes(bytes(tampered))

    report = verify_package(output, deep=True)
    failed = {check.name for check in report.failures}

    assert "deep_digest_match" in failed


def test_shareable_deep_is_not_reported_as_passed(tmp_path):
    """便携包没有本机映射，深度核验不可执行，不得记成通过。"""
    _root, package = _build(tmp_path)
    share = tmp_path / "share"
    export_shareable_package(package, share)

    report = verify_package(share, deep=True, require_locations=False)
    failed = {check.name for check in report.failures}

    assert "deep_possible" in failed


def test_readonly_violation_prevents_verified(tmp_path, monkeypatch):
    """读取期间文件被改动时，摘要不能作为稳定基准，结论不得为 verified。"""
    from app.research_evidence import builder as builder_mod
    from app.research_evidence.hashing import FileInspection

    root = tmp_path / "source"
    root.mkdir()
    _write_real_mp4(root / "clip.mp4")
    config = _write_config(tmp_path, root, [_asset("clip.mp4")])
    output = tmp_path / "out"

    real_inspect = builder_mod.inspect_file

    def fake_inspect(path, **kwargs):
        result = real_inspect(path, **kwargs)
        return FileInspection(
            availability=result.availability,
            verification=result.verification,
            sha256=result.sha256,
            size_bytes=result.size_bytes,
            detail=result.detail,
            input_unchanged=False,
        )

    monkeypatch.setattr(builder_mod, "inspect_file", fake_inspect)
    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    asset = manifest["assets"][0]
    codes = {limit["code"] for limit in manifest["limitations"]}

    assert asset["verification"] == "not_checked"
    assert "readonly_violation" in codes
    assert manifest["completeness"] == "partial"


def test_missing_ffprobe_is_reported_as_unavailable(tmp_path, monkeypatch):
    """环境缺少 ffprobe 是「未核验」，与「探测失败」区分，且文案说明原因。"""
    from app.research_evidence import builder as builder_mod
    from app.research_evidence.media_probe import MediaProbe

    root = tmp_path / "source"
    root.mkdir()
    _write_real_mp4(root / "clip.mp4")
    config = _write_config(tmp_path, root, [_asset("clip.mp4")])
    output = tmp_path / "out"

    monkeypatch.setattr(
        builder_mod,
        "probe_media",
        lambda *_args, **_kwargs: MediaProbe(
            status="skipped", detail="环境中没有 ffprobe"
        ),
    )
    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    codes = {
        (limit["code"], limit["block_completeness"])
        for limit in manifest["limitations"]
    }

    assert manifest["assets"][0]["verification"] == "not_checked"
    assert ("media_probe_unavailable", True) in codes


def test_each_usage_gets_its_own_check_records(tmp_path):
    """每个使用位置都要留痕，包括同机位的两个副本，不能被合并成一条。"""
    root = tmp_path / "source"
    root.mkdir()
    (root / "a.jsonl").write_text('{"same":"bytes"}', encoding="utf-8")
    (root / "b.jsonl").write_text('{"same":"bytes"}', encoding="utf-8")
    config = _write_config(
        tmp_path,
        root,
        [
            _asset("a.jsonl", kind="pts_sidecar", view_role="unspecified"),
            _asset("b.jsonl", kind="pts_sidecar", view_role="unspecified"),
        ],
    )
    output = tmp_path / "out"

    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    usage_count = sum(len(asset["usages"]) for asset in manifest["assets"])
    existence = [
        check for check in manifest["checks"] if check["kind"] == "existence"
    ]

    assert usage_count == 2
    assert len(existence) == usage_count
    assert len({check["check_id"] for check in existence}) == usage_count
