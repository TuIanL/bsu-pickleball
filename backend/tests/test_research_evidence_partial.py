"""Missing required sources and historical failures must degrade, not disappear.

Covers 4.2: a missing Windows artifact blocks a complete claim and points at
PB-004, while historical failures are preserved as run refs instead of being
promoted, erased, or allowed to contaminate index completeness.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

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
    with tempfile.TemporaryDirectory(prefix="pe-partial-") as tmp:
        yield Path(tmp)


def _write_config(
    tmp_path: Path,
    root: Path,
    *,
    assets: list[dict],
    historical_jobs: list[dict] | None = None,
) -> Path:
    config = {
        "package_id": "pkg_0123456789ab",
        "source_roots": [
            {"root_id": "root_captures", "path": str(root), "source_kind": "external_disk"}
        ],
        "assets": assets,
        "baseline": BASELINE,
        "historical_jobs": historical_jobs or [],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def _video_asset() -> dict:
    return {
        "root_id": "root_captures",
        "relative_path": "clip.mp4",
        "kind": "source_video",
        "usage_kind": "real",
        "requirement": "required",
    }


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    _write_real_mp4(root / "clip.mp4")
    return root


def _make_job(
    root: Path, job_id: str, *, verdict: str = "fail", with_tracks: bool = True
) -> Path:
    job = root / job_id
    job.mkdir()
    tracks = (
        [{"timestamp_seconds": 1.0}, {"timestamp_seconds": 58.8}]
        if with_tracks
        else []
    )
    (job / "result.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": "completed",
                "match_context": {
                    "schema_version": "match-analysis-context.v1",
                    "match_format": "doubles",
                    "expected_player_count": 4,
                    "players_per_side": 2,
                },
                "tracks": tracks,
            }
        ),
        encoding="utf-8",
    )
    (job / "four_player_identification_quality.json").write_text(
        json.dumps(
            {
                "schema_version": "four-player-identification-quality.v1",
                "job_id": job_id,
                "verdict": verdict,
                "duration_seconds": 58.8,
                "attempted_ticks": 100,
                "confirmed_roster_count": 4,
                "algorithm_version": "motion-aware-v1",
                "config_signature": None,
                "baseline_job_id": None,
                "failure_reasons": [] if verdict == "pass" else ["Player_1.longest_gap"],
            }
        ),
        encoding="utf-8",
    )
    return job


def _build(tmp_path: Path, root: Path, **kwargs) -> dict:
    config = _write_config(tmp_path, root, **kwargs)
    output = tmp_path / "out"
    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK
    return json.loads((output / "manifest.json").read_text(encoding="utf-8"))


# --- missing required source ------------------------------------------------


def test_missing_windows_artifact_blocks_completeness_and_links_the_task(tmp_path):
    root = _source(tmp_path)
    manifest = _build(
        tmp_path,
        root,
        assets=[
            _video_asset(),
            {
                "root_id": "root_captures",
                "relative_path": "windows-job-0d8ec77a76",
                "kind": "job_artifact",
                "usage_kind": "unknown",
                "requirement": "required",
                "asset_id": "a_windows_job",
                "notion_task": "PB-004",
            },
        ],
    )

    assert manifest["completeness"] == "partial"
    blocking = [
        limit
        for limit in manifest["limitations"]
        if limit["block_completeness"] and limit["notion_task"] == "PB-004"
    ]
    assert blocking, manifest["limitations"]
    assert any("a_windows_job" in limit["affects"] for limit in blocking)


def test_missing_optional_source_does_not_block(tmp_path):
    root = _source(tmp_path)
    manifest = _build(
        tmp_path,
        root,
        assets=[
            _video_asset(),
            {
                "root_id": "root_captures",
                "relative_path": "absent-optional",
                "kind": "job_artifact",
                "usage_kind": "unknown",
                "requirement": "optional",
                "asset_id": "a_optional_gap",
            },
        ],
    )

    assert manifest["completeness"] == "complete"


# --- historical verdicts ----------------------------------------------------


def test_historical_failure_is_preserved_as_a_run_ref(tmp_path):
    root = _source(tmp_path)
    _make_job(root, "job-43e7475fd8", verdict="fail")

    manifest = _build(
        tmp_path,
        root,
        assets=[_video_asset()],
        historical_jobs=[
            {"root_id": "root_captures", "relative_path": "job-43e7475fd8"}
        ],
    )

    assert len(manifest["run_refs"]) == 1
    run = manifest["run_refs"][0]
    assert run["run_id"] == "job-43e7475fd8"
    assert run["algorithm_verdict"]["result"] == "fail"
    assert run["code_revision"]["status"] == "unknown"
    assert run["range"]["start_seconds"] == 1.0
    assert run["range"]["end_seconds"] == 58.8

    # 历史失败不改变索引完整性，但必须被显式记录。
    assert manifest["completeness"] == "complete"
    assert any(
        limit["code"] == "historical_run_failed" for limit in manifest["limitations"]
    )


def test_historical_pass_is_recorded_without_a_failure_limitation(tmp_path):
    root = _source(tmp_path)
    _make_job(root, "job-7ab0b2ea60", verdict="pass")

    manifest = _build(
        tmp_path,
        root,
        assets=[_video_asset()],
        historical_jobs=[
            {"root_id": "root_captures", "relative_path": "job-7ab0b2ea60"}
        ],
    )

    assert manifest["run_refs"][0]["algorithm_verdict"]["result"] == "pass"
    assert not any(
        limit["code"] == "historical_run_failed" for limit in manifest["limitations"]
    )


def test_job_without_tracks_gets_no_invented_range(tmp_path):
    root = _source(tmp_path)
    _make_job(root, "job-e97318f10c", verdict="fail", with_tracks=False)

    manifest = _build(
        tmp_path,
        root,
        assets=[_video_asset()],
        historical_jobs=[
            {"root_id": "root_captures", "relative_path": "job-e97318f10c"}
        ],
    )

    assert manifest["run_refs"] == []
    assert any(
        limit["code"] == "historical_run_range_unknown"
        for limit in manifest["limitations"]
    )


def test_historical_job_without_result_blocks_completeness(tmp_path):
    root = _source(tmp_path)
    (root / "job-absent").mkdir()

    manifest = _build(
        tmp_path,
        root,
        assets=[_video_asset()],
        historical_jobs=[{"root_id": "root_captures", "relative_path": "job-absent"}],
    )

    assert manifest["completeness"] == "partial"
    assert any(
        limit["code"] == "historical_run_missing" and limit["block_completeness"]
        for limit in manifest["limitations"]
    )


def test_quality_report_for_another_job_is_not_applied(tmp_path):
    """质量报告必须与运行的 job_id 精确匹配；不匹配时不得生成质量结论。"""
    root = _source(tmp_path)
    job = root / "job-aaaaaaaaaa"
    job.mkdir()
    (job / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job-aaaaaaaaaa",
                "status": "completed",
                "match_context": {
                    "schema_version": "match-analysis-context.v1",
                    "match_format": "doubles",
                    "expected_player_count": 4,
                    "players_per_side": 2,
                },
                "tracks": [
                    {"timestamp_seconds": 1.0},
                    {"timestamp_seconds": 10.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    (job / "four_player_identification_quality.json").write_text(
        json.dumps(
            {
                "schema_version": "four-player-identification-quality.v1",
                "job_id": "job-bbbbbbbbbb",
                "verdict": "pass",
                "duration_seconds": 9.0,
                "attempted_ticks": 10,
                "confirmed_roster_count": 4,
                "algorithm_version": "motion-aware-v1",
                "config_signature": None,
                "baseline_job_id": None,
                "failure_reasons": [],
            }
        ),
        encoding="utf-8",
    )

    manifest = _build(
        tmp_path,
        root,
        assets=[_video_asset()],
        historical_jobs=[
            {"root_id": "root_captures", "relative_path": "job-aaaaaaaaaa"}
        ],
    )

    run = manifest["run_refs"][0]
    assert run["run_id"] == "job-aaaaaaaaaa"
    assert run["algorithm_verdict"]["result"] == "unknown"
    assert run["algorithm_verdict"]["recorded_source"] == "none"
    assert any(
        limit["code"] == "historical_quality_unmatched"
        for limit in manifest["limitations"]
    )
