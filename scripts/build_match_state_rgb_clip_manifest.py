#!/usr/bin/env python3
"""生成 metadata-only 双摄 RGB 时序窗口清单；不读取或解码视频。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "match_state_rgb_clip_manifest.v1"
CLIP_SCHEMA_VERSION = "match_state_rgb_clip.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _label_at(timestamp_ms: int, rallies: list[dict[str, Any]], buffer_ms: int) -> tuple[str, str, str | None]:
    for rally in rallies:
        start = int(rally["start_ms"])
        end = int(rally["end_ms"])
        if start - buffer_ms <= timestamp_ms < start + buffer_ms:
            return "uncertain", "uncertain", rally["segment_id"]
        if end - buffer_ms <= timestamp_ms < end + buffer_ms:
            return "uncertain", "uncertain", rally["segment_id"]
        if start + buffer_ms <= timestamp_ms < end - buffer_ms:
            return "rally_active", "high_confidence", rally["segment_id"]
    return "non_play", "high_confidence", None


def _centers(duration_ms: int, stride_ms: int) -> Iterable[int]:
    center = 0
    while center <= duration_ms:
        yield center
        center += stride_ms
    if duration_ms % stride_ms:
        yield duration_ms


def build_clips(
    dataset: dict[str, Any],
    *,
    clip_duration_ms: int,
    stride_ms: int,
    rgb_fps: float,
    label_step_ms: int,
    uncertain_radius_ms: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    half = clip_duration_ms // 2
    target_frame_count = round(clip_duration_ms * rgb_fps / 1000)
    clips: list[dict[str, Any]] = []
    counts = {"rally_active": 0, "non_play": 0, "uncertain": 0}

    for take in dataset["takes"]:
        duration_ms = int(take["duration_ms"])
        rallies = sorted(take["labels"], key=lambda item: (item["start_ms"], item["end_ms"]))
        views = sorted(take["media"], key=lambda item: item["camera_role"])
        for center_ms in _centers(duration_ms, stride_ms):
            requested_start = center_ms - half
            requested_end = requested_start + clip_duration_ms
            take_start = max(0, requested_start)
            take_end = min(duration_ms, requested_end)
            left_padding = max(0, -requested_start)
            right_padding = max(0, requested_end - duration_ms)
            center_label, center_quality, center_rally_id = _label_at(
                center_ms, rallies, uncertain_radius_ms
            )
            counts[center_label] += 1
            timeline_labels: list[dict[str, Any]] = []
            tick = requested_start
            while tick < requested_end:
                if tick < 0 or tick >= duration_ms:
                    timeline_labels.append(
                        {
                            "take_timestamp_ms": max(0, min(duration_ms, tick)),
                            "label": "padding",
                            "quality": "excluded",
                            "loss_mask": 0,
                            "rally_segment_id": None,
                        }
                    )
                else:
                    label, quality, rally_id = _label_at(tick, rallies, uncertain_radius_ms)
                    timeline_labels.append(
                        {
                            "take_timestamp_ms": tick,
                            "label": label,
                            "quality": quality,
                            "loss_mask": int(quality == "high_confidence"),
                            "rally_segment_id": rally_id,
                        }
                    )
                tick += label_step_ms

            clip_identity = {
                "dataset_manifest_id": dataset["manifest_id"],
                "capture_take_id": take["capture_take_id"],
                "center_ms": center_ms,
                "clip_duration_ms": clip_duration_ms,
                "rgb_fps": rgb_fps,
            }
            clip_id = f"rgbc_{_sha256_bytes(_canonical_bytes(clip_identity))[:20]}"
            clip_views: list[dict[str, Any]] = []
            for view in views:
                mapping = view.get("take_time_mapping") or {}
                portable_mapping = {
                    key: value for key, value in mapping.items() if key != "timing_sidecar_path"
                }
                portable_mapping["timing_sidecar_available"] = bool(mapping.get("timing_sidecar_path"))
                portable_mapping["timing_sidecar_remote_relative_path"] = (
                    f"timing/{take['source_session_id']}/{view['camera_role']}.pts.jsonl"
                    if mapping.get("timing_sidecar_path")
                    else None
                )
                sync_validated = (
                    mapping.get("sync_quality") in {"good", "excellent"}
                    and mapping.get("offset_source") not in {"assumed", "missing"}
                )
                clip_views.append(
                    {
                        "camera_role": view["camera_role"],
                        "logical_media_uri": view["logical_uri"],
                        "remote_relative_path": view["remote_relative_path"],
                        "take_start_ms": take_start,
                        "take_end_ms": take_end,
                        "target_rgb_fps": rgb_fps,
                        "target_frame_count": target_frame_count,
                        "left_padding_ms": left_padding,
                        "right_padding_ms": right_padding,
                        "take_time_mapping": portable_mapping,
                        "sync_validation_status": "validated" if sync_validated else "pending_validation",
                    }
                )
            clips.append(
                {
                    "schema_version": CLIP_SCHEMA_VERSION,
                    "clip_id": clip_id,
                    "dataset_manifest_id": dataset["manifest_id"],
                    "capture_take_id": take["capture_take_id"],
                    "source_session_id": take["source_session_id"],
                    "timebase": "capture_take_relative_ms",
                    "requested_start_ms": requested_start,
                    "requested_end_ms": requested_end,
                    "take_start_ms": take_start,
                    "take_end_ms": take_end,
                    "center_ms": center_ms,
                    "center_label": center_label,
                    "center_quality": center_quality,
                    "center_rally_segment_id": center_rally_id,
                    "timeline_label_step_ms": label_step_ms,
                    "timeline_labels": timeline_labels,
                    "views": clip_views,
                    "split": "unassigned",
                }
            )
    return clips, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="生成远程可解析的 RGB clip 元数据清单")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--label-profile", type=Path, required=True)
    parser.add_argument("--remote-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clip-duration-ms", type=int, default=4000)
    parser.add_argument("--stride-ms", type=int, default=500)
    parser.add_argument("--rgb-fps", type=float, default=12.0)
    parser.add_argument("--label-step-ms", type=int, default=250)
    args = parser.parse_args()

    if args.clip_duration_ms <= 0 or args.clip_duration_ms % 2:
        raise ValueError("clip-duration-ms 必须是正偶数")
    if min(args.stride_ms, args.label_step_ms) <= 0 or args.rgb_fps <= 0:
        raise ValueError("stride、label step 和 RGB FPS 必须为正数")

    dataset = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    label_profile = json.loads(args.label_profile.read_text(encoding="utf-8"))
    remote_profile = json.loads(args.remote_profile.read_text(encoding="utf-8"))
    uncertain_radius_ms = int(label_profile["reviewed_boundary_policy"]["uncertain_radius_ms"])
    clips, counts = build_clips(
        dataset,
        clip_duration_ms=args.clip_duration_ms,
        stride_ms=args.stride_ms,
        rgb_fps=args.rgb_fps,
        label_step_ms=args.label_step_ms,
        uncertain_radius_ms=uncertain_radius_ms,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    clips_path = args.output.with_suffix(".clips.jsonl")
    with clips_path.open("w", encoding="utf-8") as handle:
        for clip in clips:
            handle.write(json.dumps(clip, ensure_ascii=False, separators=(",", ":")) + "\n")

    config = {
        "clip_duration_ms": args.clip_duration_ms,
        "stride_ms": args.stride_ms,
        "target_rgb_fps_per_view": args.rgb_fps,
        "target_frame_count_per_view": round(args.clip_duration_ms * args.rgb_fps / 1000),
        "timeline_label_step_ms": args.label_step_ms,
        "uncertain_radius_ms": uncertain_radius_ms,
        "materialize_video_clips_locally": False,
        "execution_stage": "remote_required",
    }
    immutable = {
        "schema_version": SCHEMA_VERSION,
        "dataset_manifest_id": dataset["manifest_id"],
        "dataset_manifest_sha256": _sha256_file(args.dataset_manifest),
        "label_profile_sha256": _sha256_file(args.label_profile),
        "remote_profile_sha256": _sha256_file(args.remote_profile),
        "config": config,
        "clip_count": len(clips),
        "center_label_counts": counts,
        "clips_jsonl_sha256": _sha256_file(clips_path),
    }
    manifest_id = f"rgbm_{_sha256_bytes(_canonical_bytes(immutable))[:20]}"
    index = {
        **immutable,
        "manifest_id": manifest_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "clips_file": clips_path.name,
        "media_root_env": remote_profile["media_contract"]["remote_dataset_root_env"],
        "sync_validation_status": "pending_task_2.4",
        "split_status": "unassigned_pending_task_2.5",
    }
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest_id": manifest_id,
                "clip_count": len(clips),
                "center_label_counts": counts,
                "clips_file": str(clips_path),
                "clips_size_bytes": clips_path.stat().st_size,
                "video_decode_performed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
