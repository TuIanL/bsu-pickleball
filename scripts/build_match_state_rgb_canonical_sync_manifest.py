#!/usr/bin/env python3
"""为现有 RGB clip 生成使用 canonical sync 映射的 v2 manifest。

该脚本只重写 clip 元数据，不重新抽取 RGB 帧。v1 nominal-sync manifest 和
训练结果保持不变，v2 loader 根据每个 view 的 mapped_start_ms 与 rate 取缓存帧。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .build_match_state_aligned_features import load_json
    from .match_state_sync_authority import calibration_from_dict, map_reference_time
except ImportError:
    from build_match_state_aligned_features import load_json
    from match_state_sync_authority import calibration_from_dict, map_reference_time


SCHEMA_VERSION = "match_state_rgb_canonical_sync_manifest.v2"
CLIP_SCHEMA_VERSION = "match_state_rgb_clip_canonical_sync.v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def window_status(
    *,
    camera_id: str,
    reference_camera_id: str,
    mapping: Any,
    duration_ms: float,
    requested_start_ms: float,
    requested_end_ms: float,
) -> str:
    effective_start = max(0.0, requested_start_ms)
    effective_end = min(duration_ms, requested_end_ms)
    if effective_end < effective_start:
        return "unavailable"
    mapped_start = map_reference_time(mapping, effective_start / 1000.0)
    mapped_end = map_reference_time(mapping, effective_end / 1000.0)
    local_start = min(mapped_start, mapped_end)
    local_end = max(mapped_start, mapped_end)
    if local_end < 0.0 or local_start > duration_ms / 1000.0:
        return "unavailable"
    if camera_id == reference_camera_id:
        return "authoritative"
    in_valid_span = (
        mapping.valid_start_seconds is None or effective_start / 1000.0 >= mapping.valid_start_seconds
    ) and (mapping.valid_end_seconds is None or effective_end / 1000.0 <= mapping.valid_end_seconds)
    return "authoritative" if in_valid_span and mapping.quality == "good" else "extrapolated"


def build_manifest(base_path: Path, sync_path: Path, output_path: Path) -> dict[str, Any]:
    base = load_json(base_path)
    sync = load_json(sync_path)
    sync_entries = {str(item["source_session_id"]): item for item in sync.get("entries", [])}
    base_clips_path = base_path.parent / str(base["clips_file"])
    clips = load_jsonl(base_clips_path)
    output_clips: list[dict[str, Any]] = []
    status_counts = Counter()
    for clip in clips:
        session_id = str(clip["source_session_id"])
        sync_entry = sync_entries.get(session_id)
        if sync_entry is None:
            raise ValueError(f"sync manifest 缺少 session: {session_id}")
        cameras = {str(item["camera_role"]): item for item in sync_entry["cameras"]}
        output_views: list[dict[str, Any]] = []
        view_statuses: dict[str, str] = {}
        for base_view in sorted(clip["views"], key=lambda item: str(item["camera_role"])):
            role = str(base_view["camera_role"])
            camera = cameras.get(role)
            if camera is None:
                raise ValueError(f"{session_id} 缺少 {role} sync camera")
            mapping = calibration_from_dict(dict(camera["mapping"]))
            requested_start = float(clip["requested_start_ms"])
            requested_end = float(clip["requested_end_ms"])
            mapped_start_ms = map_reference_time(mapping, requested_start / 1000.0) * 1000.0
            mapped_end_ms = map_reference_time(mapping, requested_end / 1000.0) * 1000.0
            status = window_status(
                camera_id=str(camera["camera_id"]),
                reference_camera_id=str(sync_entry["reference_camera_id"]),
                mapping=mapping,
                duration_ms=float(camera["timing"]["duration_seconds"]) * 1000.0,
                requested_start_ms=requested_start,
                requested_end_ms=requested_end,
            )
            status_counts[status] += 1
            view_statuses[role] = status
            output_views.append(
                {
                    **base_view,
                    "camera_id": camera["camera_id"],
                    "canonical_start_ms": requested_start,
                    "canonical_end_ms": requested_end,
                    "mapped_start_ms": round(mapped_start_ms, 6),
                    "mapped_end_ms": round(mapped_end_ms, 6),
                    "canonical_to_local_rate": float(mapping.rate),
                    "timing_authority": "source_pts",
                    "sync_quality": mapping.quality,
                    "sync_status": status,
                    "sync_revision": sync_entry["sync_revision"],
                    "sync_calibration_sha256": sync_entry["calibration"]["sha256"],
                    "timing_sidecar_sha256": camera["timing"]["sha256"],
                    "sync_training_eligible": status in {"authoritative", "extrapolated"},
                }
            )
        clip_status = max(
            view_statuses.values(),
            key=lambda value: {"authoritative": 0, "extrapolated": 1, "unavailable": 2}[value],
        )
        output_clips.append(
            {
                **clip,
                "schema_version": CLIP_SCHEMA_VERSION,
                "base_clip_manifest_id": base["manifest_id"],
                "timebase": "reference_camera_source_pts",
                "sync_revision": sync_entry["sync_revision"],
                "sync": {
                    "status": clip_status,
                    "reference_camera_id": sync_entry["reference_camera_id"],
                    "camera_status": view_statuses,
                    "authoritative_joint_eligible": all(value == "authoritative" for value in view_statuses.values()),
                },
                "views": output_views,
            }
        )

    identity = {
        "base_rgb_manifest_id": base["manifest_id"],
        "base_rgb_manifest_sha256": sha256_file(base_path),
        "base_clips_jsonl_sha256": sha256_file(base_clips_path),
        "sync_assets_manifest_id": sync["manifest_id"],
        "sync_assets_manifest_sha256": sha256_file(sync_path),
        "sync_core_sha256": sync.get("identity", {}).get("sync_core_sha256"),
        "clip_count": len(output_clips),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clips_path = output_path.with_suffix(".clips.jsonl")
    with clips_path.open("w", encoding="utf-8") as handle:
        for clip in output_clips:
            handle.write(json.dumps(clip, ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": f"rgbcs_{canonical_hash(identity)[:20]}",
        "generated_at": datetime.now(UTC).isoformat(),
        "clips_file": clips_path.name,
        "clip_count": len(output_clips),
        "identity": identity,
        "sync_status_counts": dict(status_counts),
        "sync_validation_status": "complete",
        "split_status": base.get("split_status"),
        "clips_jsonl_sha256": sha256_file(clips_path),
    }
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 RGB canonical-sync v2 clip manifest")
    parser.add_argument("--rgb-manifest", type=Path, required=True)
    parser.add_argument("--sync-assets-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.rgb_manifest, args.sync_assets_manifest, args.output)
    print(
        json.dumps(
            {
                "schema_version": manifest["schema_version"],
                "manifest_id": manifest["manifest_id"],
                "clip_count": manifest["clip_count"],
                "sync_status_counts": manifest["sync_status_counts"],
                "clips_file": str(args.output.with_suffix(".clips.jsonl")),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
