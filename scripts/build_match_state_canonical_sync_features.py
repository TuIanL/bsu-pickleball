#!/usr/bin/env python3
"""使用旧系统同步 authority 重建比赛状态 v2 对齐层。

该 runner 只读取 RGB frame cache、结构化视觉 cache、PTS sidecar 和同步 artifact。
它不重新解码视频，也不重新运行 RTMPose、球检测或场地线模型。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .build_match_state_aligned_features import index_structured_cache, load_json, load_jsonl
    from .match_state_sync_authority import (
        DEFAULT_FEATURE_SELECTION_GAP_MS,
        DEFAULT_SOURCE_SELECTION_ERROR_MS,
        CanonicalFeatureClock,
        SourceTiming,
        feature_timings,
        joint_sync_status,
    )
    from .match_state_temporal_features import (
        FEATURE_SCHEMA_VERSION,
        BallFeatureState,
        PlayerFeatureState,
        TimestampIndex,
        derive_ball_features,
        derive_player_features,
        rgb_frame_reference,
    )
except ImportError:  # 允许远程 python scripts/... 直接运行
    from build_match_state_aligned_features import index_structured_cache, load_json, load_jsonl
    from match_state_sync_authority import (
        DEFAULT_FEATURE_SELECTION_GAP_MS,
        DEFAULT_SOURCE_SELECTION_ERROR_MS,
        CanonicalFeatureClock,
        SourceTiming,
        feature_timings,
        joint_sync_status,
    )
    from match_state_temporal_features import (
        FEATURE_SCHEMA_VERSION,
        BallFeatureState,
        PlayerFeatureState,
        TimestampIndex,
        derive_ball_features,
        derive_player_features,
        rgb_frame_reference,
    )


V2_SCHEMA_VERSION = "match_state_canonical_sync_feature.v2"
MANIFEST_SCHEMA_VERSION = "match_state_canonical_sync_manifest.v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 3)


def _missing_features() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "players": [],
            "formation": {"player_count": 0},
            "pose_usable": False,
            "four_players_observed": False,
            "pose_visible_ratio": 0.0,
            "structured_loss_mask": 0,
        },
        {
            "candidate_count": 0,
            "candidate_track_ids": [],
            "observed": False,
            "missing_semantics": "unknown_not_no_ball",
            "track_id": None,
            "center_xy_norm": None,
            "velocity_xy_norm_per_s": None,
            "speed_norm_per_s": None,
            "direction_rad": None,
            "acceleration_norm_per_s2": None,
            "stationary": None,
            "visibility": 0.0,
        },
    )


def _court_view(
    court_index: TimestampIndex,
    target_source_pts_seconds: float,
) -> tuple[dict[str, Any] | None, float | None]:
    return court_index.nearest(target_source_pts_seconds * 1000.0, 30_000.0)


def build_synced_view(
    *,
    role: str,
    canonical_seconds: float,
    clock: CanonicalFeatureClock,
    rgb_entry: dict[str, Any] | None,
    court_index: TimestampIndex,
    player_state: PlayerFeatureState,
    ball_state: BallFeatureState,
) -> dict[str, Any]:
    selection, record = clock.select(role, canonical_seconds)
    pose, ball = _missing_features()
    if record is not None:
        feature_record = {**record, "take_timestamp_ms": canonical_seconds * 1000.0}
        pose = derive_player_features(feature_record, player_state)
        ball = derive_ball_features(feature_record, ball_state)
    court_target = selection.target_source_pts_seconds
    court, court_delta = _court_view(court_index, court_target)
    rgb = None
    if rgb_entry is not None:
        rgb = rgb_frame_reference(
            rgb_entry,
            court_target * 1000.0,
            float((rgb_entry.get("identity") or {}).get("fps", 12.0)),
        )
        rgb["target_timestamp_ms"] = _round(court_target * 1000.0)
        rgb["timing_authority"] = "legacy_nominal_fps"
        rgb["source_pts_binding"] = "target_only_no_output_source_frame_binding"
    structured = (
        None
        if record is None
        else {
            "available": True,
            "source_frame_index": selection.feature_source_frame_index,
            "source_pts_ms": _round(
                selection.feature_pts_seconds * 1000.0 if selection.feature_pts_seconds is not None else None
            ),
            "alignment_error_ms": _round(
                selection.feature_alignment_error_seconds * 1000.0
                if selection.feature_alignment_error_seconds is not None
                else None
            ),
            "schema_version": record.get("schema_version"),
            "camera_role": record.get("camera_role"),
        }
    )
    if record is None:
        structured = {
            "available": False,
            "source_frame_index": None,
            "source_pts_ms": None,
            "alignment_error_ms": _round(
                selection.feature_alignment_error_seconds * 1000.0
                if selection.feature_alignment_error_seconds is not None
                else None
            ),
            "schema_version": None,
            "camera_role": role,
        }
    return {
        "camera_role": role,
        "camera_id": selection.camera_id,
        "canonical_timestamp_ms": _round(canonical_seconds * 1000.0),
        "source": {
            "source_frame_index": selection.source_frame_index,
            "source_pts_ms": _round(
                selection.source_pts_seconds * 1000.0 if selection.source_pts_seconds is not None else None
            ),
            "mapped_target_pts_ms": _round(selection.target_source_pts_seconds * 1000.0),
            "alignment_error_ms": _round(
                selection.source_alignment_error_seconds * 1000.0
                if selection.source_alignment_error_seconds is not None
                else None
            ),
            "feature_source_frame_index": selection.feature_source_frame_index,
            "feature_pts_ms": _round(
                selection.feature_pts_seconds * 1000.0 if selection.feature_pts_seconds is not None else None
            ),
            "feature_alignment_error_ms": _round(
                selection.feature_alignment_error_seconds * 1000.0
                if selection.feature_alignment_error_seconds is not None
                else None
            ),
            "timing_authority": selection.timing_authority,
            "sync_quality": selection.sync_quality,
            "sync_status": selection.sync_status,
            "mapping_mode": selection.mapping_mode,
            "sync_revision": clock.sync_revision,
            "reason": selection.reason,
        },
        "rgb": rgb,
        "structured": structured,
        "court_line": {
            "available": court is not None,
            "timestamp_ms": None if court is None else court.get("timestamp_ms"),
            "alignment_error_ms": _round(court_delta),
            "geometry": court,
            "projection_available": False,
        },
        "features": {"pose": pose, "ball": ball},
        "quality": {
            "rgb_available": bool(rgb and rgb.get("available")),
            "structured_available": record is not None,
            "court_line_available": court is not None,
            "pose_usable": bool(pose.get("pose_usable", False)),
            "ball_observed": bool(ball.get("observed", False)),
            "ball_missing_semantics": ball.get("missing_semantics"),
            "timing_authority": selection.timing_authority,
            "sync_quality": selection.sync_quality,
            "sync_status": selection.sync_status,
            "view_missing": record is None or selection.sync_status == "unavailable",
        },
    }


def iter_synced_records(
    *,
    clock: CanonicalFeatureClock,
    rgb_entries: dict[str, dict[str, Any]],
    structured_views: dict[str, dict[str, Any]],
    fps: float,
    take_id: str,
    session_id: str,
) -> Iterator[dict[str, Any]]:
    states = {role: (PlayerFeatureState(), BallFeatureState()) for role in ("cam_1", "cam_2")}
    court_indexes = {
        role: TimestampIndex(view["court"], timestamp_key="timestamp_ms") for role, view in structured_views.items()
    }
    for canonical_seconds, reference_frame_index in clock.canonical_ticks(fps):
        views: dict[str, Any] = {}
        selections = []
        for role in ("cam_1", "cam_2"):
            selection, _ = clock.select(role, canonical_seconds)
            selections.append(selection)
            view = structured_views.get(role)
            rgb_entry = None
            if view is not None:
                rgb_entry = rgb_entries.get(str(view["uri"]))
            if view is None:
                pose, ball = _missing_features()
                views[role] = {
                    "camera_role": role,
                    "camera_id": None,
                    "canonical_timestamp_ms": _round(canonical_seconds * 1000.0),
                    "source": {"timing_authority": "missing", "sync_status": "unavailable"},
                    "rgb": None,
                    "structured": {"available": False},
                    "court_line": {"available": False, "geometry": None},
                    "features": {"pose": pose, "ball": ball},
                    "quality": {"view_missing": True, "timing_authority": "missing", "sync_status": "unavailable"},
                }
                continue
            views[role] = build_synced_view(
                role=role,
                canonical_seconds=canonical_seconds,
                clock=clock,
                rgb_entry=rgb_entry,
                court_index=court_indexes[role],
                player_state=states[role][0],
                ball_state=states[role][1],
            )
        status = joint_sync_status(selections)
        authoritative = status == "authoritative" and all(item.usable for item in selections)
        yield {
            "schema_version": V2_SCHEMA_VERSION,
            "feature_schema": FEATURE_SCHEMA_VERSION,
            "capture_take_id": take_id,
            "source_session_id": session_id,
            "timebase": "reference_camera_source_pts",
            "canonical_timestamp_ms": _round(canonical_seconds * 1000.0),
            "reference_source_frame_index": reference_frame_index,
            "sync_revision": clock.sync_revision,
            "sync": {
                "reference_camera_id": clock.reference_camera_id,
                "status": status,
                "authoritative_joint_eligible": authoritative,
                "camera_status": {item.camera_role: item.sync_status for item in selections},
            },
            "views": views,
            "quality": {
                "dual_view_available": all(item.usable for item in selections),
                "authoritative_joint_eligible": authoritative,
                "sync_status": status,
                "pose_view_count": sum(bool(view["quality"].get("pose_usable")) for view in views.values()),
                "ball_view_count": sum(bool(view["quality"].get("ball_observed")) for view in views.values()),
                "view_missing_mask": {role: bool(view["quality"].get("view_missing")) for role, view in views.items()},
            },
        }


def _remote_asset_path(dataset_root: Path, relative: str | None) -> Path | None:
    if not relative:
        return None
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"远程 artifact 路径必须是安全相对路径: {relative}")
    return dataset_root / path


def _verify_remote_hash(path: Path, expected: str | None) -> None:
    if not path.is_file():
        raise ValueError(f"远程同步 artifact 缺失: {path}")
    if expected and sha256_file(path) != expected:
        raise ValueError(f"同步 artifact SHA-256 不匹配: {path}")


def _verify_sync_artifacts(dataset_root: Path, sync_entry: dict[str, Any]) -> dict[str, Any]:
    calibration_path = _remote_asset_path(dataset_root, str(sync_entry["calibration"].get("remote_relative_path")))
    if calibration_path is None:
        raise ValueError("同步校准 artifact 路径为空")
    _verify_remote_hash(calibration_path, str(sync_entry["calibration"].get("sha256")))
    calibration = load_json(calibration_path)
    if calibration.get("schema_version") != "dual_camera_sync_calibration.v1":
        raise ValueError(f"同步校准 schema 不匹配: {calibration_path}")
    if str(calibration.get("reference_camera")) != str(sync_entry["reference_camera_id"]):
        raise ValueError(f"同步校准 reference_camera 与 manifest 不一致: {calibration_path}")
    mappings = calibration.get("mappings")
    if not isinstance(mappings, dict):
        raise ValueError(f"同步校准 mappings 必须是对象: {calibration_path}")
    for camera in sync_entry["cameras"]:
        camera_id = str(camera["camera_id"])
        if mappings.get(camera_id) != camera.get("mapping"):
            raise ValueError(f"同步校准 mapping 与资产清单不一致: {calibration_path} / {camera_id}")
    for name in ("anchors", "confirmation"):
        artifact = sync_entry.get(name) or {}
        relative = artifact.get("remote_relative_path")
        if relative:
            path = _remote_asset_path(dataset_root, str(relative))
            _verify_remote_hash(path, str(artifact.get("sha256")))
    return calibration


def main() -> int:
    parser = argparse.ArgumentParser(description="基于旧系统 authority 生成比赛状态 canonical-sync v2 特征")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-cache-manifest", type=Path, required=True)
    parser.add_argument("--structured-cache-root", type=Path, required=True)
    parser.add_argument("--sync-assets-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--max-source-selection-error-ms", type=float, default=DEFAULT_SOURCE_SELECTION_ERROR_MS)
    parser.add_argument("--max-feature-selection-gap-ms", type=float, default=DEFAULT_FEATURE_SELECTION_GAP_MS)
    parser.add_argument("--only-session")
    parser.add_argument("--max-takes", type=int)
    args = parser.parse_args()
    if args.fps <= 0 or args.max_source_selection_error_ms <= 0 or args.max_feature_selection_gap_ms <= 0:
        raise SystemExit("fps 和两个 selection gap 必须为正数")
    rgb_manifest = load_json(args.rgb_cache_manifest)
    rgb_entries = rgb_manifest.get("entries", {})
    if not isinstance(rgb_entries, dict):
        raise SystemExit("RGB cache manifest entries 必须是对象")
    sync_manifest = load_json(args.sync_assets_manifest)
    sync_entries = {str(item["source_session_id"]): item for item in sync_manifest.get("entries", [])}
    structured_index = index_structured_cache(args.structured_cache_root)
    dataset = load_json(args.dataset_manifest)
    selected = [
        take
        for take in dataset.get("takes", [])
        if not args.only_session or take.get("source_session_id") == args.only_session
    ]
    if args.max_takes is not None:
        selected = selected[: args.max_takes]
    args.output_root.mkdir(parents=True, exist_ok=True)
    output_entries: list[dict[str, Any]] = []
    for take in selected:
        session_id = str(take["source_session_id"])
        sync_entry = sync_entries.get(session_id)
        if sync_entry is None:
            raise ValueError(f"sync assets manifest 缺少 session: {session_id}")
        _verify_sync_artifacts(args.dataset_root, sync_entry)
        structured_views: dict[str, dict[str, Any]] = {}
        source_timings: dict[str, SourceTiming] = {}
        feature_timings_by_role: dict[str, list[Any]] = {}
        for camera in sync_entry["cameras"]:
            role = str(camera["camera_role"])
            uri = str(camera["logical_media_uri"])
            cache = structured_index.get(uri)
            if cache is None:
                raise ValueError(f"结构化缓存缺少 logical_media_uri: {uri}")
            timing_path = _remote_asset_path(args.dataset_root, str(camera["timing"]["remote_relative_path"]))
            _verify_remote_hash(timing_path, str(camera["timing"].get("sha256")))
            timing = SourceTiming.from_sidecar(str(camera["camera_id"]), timing_path)
            frames = load_jsonl(cache["frames_path"])
            court = load_jsonl(cache["court_path"])
            source_timings[role] = timing
            feature_timings_by_role[role] = feature_timings(frames, timing)
            structured_views[role] = {"uri": uri, "frames": frames, "court": court}
        clock = CanonicalFeatureClock(
            sync_entry=sync_entry,
            source_timings=source_timings,
            feature_timings_by_role=feature_timings_by_role,
            max_source_selection_error_ms=args.max_source_selection_error_ms,
            max_feature_selection_gap_ms=args.max_feature_selection_gap_ms,
        )
        output_path = args.output_root / f"{session_id}.canonical-sync.jsonl"
        fd, temp_name = tempfile.mkstemp(prefix=f".{session_id}.", suffix=".partial", dir=args.output_root)
        record_count = 0
        authoritative_count = 0
        first_timestamp_ms: float | None = None
        last_timestamp_ms: float | None = None
        status_counts: dict[str, int] = defaultdict(int)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                for record in iter_synced_records(
                    clock=clock,
                    rgb_entries=rgb_entries,
                    structured_views=structured_views,
                    fps=args.fps,
                    take_id=str(take["capture_take_id"]),
                    session_id=session_id,
                ):
                    output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                    record_count += 1
                    timestamp_ms = float(record["canonical_timestamp_ms"])
                    if first_timestamp_ms is None:
                        first_timestamp_ms = timestamp_ms
                    last_timestamp_ms = timestamp_ms
                    authoritative_count += int(record["quality"]["authoritative_joint_eligible"])
                    status_counts[record["sync"]["status"]] += 1
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_name, output_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        output_entries.append(
            {
                "capture_take_id": take["capture_take_id"],
                "source_session_id": session_id,
                "path": output_path.name,
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "status": "complete",
                "record_count": record_count,
                "authoritative_joint_record_count": authoritative_count,
                "sync_status_counts": dict(status_counts),
                "sha256": sha256_file(output_path),
                "size_bytes": output_path.stat().st_size,
                "timestamp_start_ms": first_timestamp_ms,
                "timestamp_end_ms": last_timestamp_ms,
                "sync_revision": clock.sync_revision,
                "fps": args.fps,
            }
        )
        print(json.dumps(output_entries[-1], ensure_ascii=False))
    identity = {
        "builder_sha256": sha256_file(Path(__file__).resolve()),
        "sync_adapter_sha256": sha256_file(Path(__file__).resolve().with_name("match_state_sync_authority.py")),
        "temporal_feature_code_sha256": sha256_file(
            Path(__file__).resolve().with_name("match_state_temporal_features.py")
        ),
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "rgb_cache_manifest_sha256": sha256_file(args.rgb_cache_manifest),
        "sync_assets_manifest_sha256": sha256_file(args.sync_assets_manifest),
        "sync_assets_manifest_id": sync_manifest.get("manifest_id"),
        "sync_core_sha256": sync_manifest.get("identity", {}).get("sync_core_sha256"),
        "structured_cache_keys": sorted(item["summary"]["cache_key"] for item in structured_index.values()),
        "fps": args.fps,
        "max_source_selection_error_ms": args.max_source_selection_error_ms,
        "max_feature_selection_gap_ms": args.max_feature_selection_gap_ms,
        "timebase": "reference_camera_source_pts",
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_id": f"csync_{hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]}",
        "generated_at": datetime.now(UTC).isoformat(),
        "identity": identity,
        "entries": output_entries,
    }
    (args.output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"schema_version": MANIFEST_SCHEMA_VERSION, "status": "complete", "take_count": len(output_entries)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
