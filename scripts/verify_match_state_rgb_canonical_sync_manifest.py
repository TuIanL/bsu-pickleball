#!/usr/bin/env python3
"""校验 RGB canonical-sync v2 manifest 的映射字段和文件封口。"""

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


def verify(manifest_path: Path, sync_manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    sync_manifest = load_json(sync_manifest_path)
    root = manifest_path.parent
    errors: list[str] = []
    clips_path = root / str(manifest.get("clips_file", ""))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"manifest schema 不正确: {manifest.get('schema_version')}")
    if manifest.get("identity", {}).get("sync_assets_manifest_sha256") != sha256_file(sync_manifest_path):
        errors.append("sync assets manifest SHA-256 与 RGB v2 provenance 不一致")
    sync_entries = {str(item["source_session_id"]): item for item in sync_manifest.get("entries", [])}
    clip_count = 0
    unique_ids: set[str] = set()
    status_counts = Counter()
    authoritative_count = 0
    with clips_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            clip = json.loads(line)
            clip_count += 1
            clip_id = str(clip.get("clip_id", ""))
            if not clip_id or clip_id in unique_ids:
                errors.append(f"{clips_path}:{line_number}: clip_id 缺失或重复")
            unique_ids.add(clip_id)
            if clip.get("schema_version") != CLIP_SCHEMA_VERSION:
                errors.append(f"{clips_path}:{line_number}: clip schema 不正确")
            session_id = str(clip.get("source_session_id"))
            sync_entry = sync_entries.get(session_id)
            if sync_entry is None:
                errors.append(f"{clips_path}:{line_number}: sync session 缺失: {session_id}")
                continue
            if clip.get("sync_revision") != sync_entry.get("sync_revision"):
                errors.append(f"{clips_path}:{line_number}: sync_revision 不一致")
            view_statuses: dict[str, str] = {}
            for view in clip.get("views", []):
                role = str(view.get("camera_role"))
                camera = next((item for item in sync_entry["cameras"] if item["camera_role"] == role), None)
                if camera is None:
                    errors.append(f"{clips_path}:{line_number}: 未知 camera role={role}")
                    continue
                mapping = calibration_from_dict(dict(camera["mapping"]))
                canonical_start = float(view["canonical_start_ms"])
                canonical_end = float(view["canonical_end_ms"])
                expected_start = map_reference_time(mapping, canonical_start / 1000.0) * 1000.0
                expected_end = map_reference_time(mapping, canonical_end / 1000.0) * 1000.0
                if abs(float(view["mapped_start_ms"]) - expected_start) > 0.01:
                    errors.append(f"{clips_path}:{line_number}: {role} mapped_start_ms 不匹配旧同步核心")
                if abs(float(view["mapped_end_ms"]) - expected_end) > 0.01:
                    errors.append(f"{clips_path}:{line_number}: {role} mapped_end_ms 不匹配旧同步核心")
                if view.get("timing_authority") != "source_pts":
                    errors.append(f"{clips_path}:{line_number}: {role} timing authority 不是 source_pts")
                status = str(view.get("sync_status"))
                view_statuses[role] = status
                status_counts[status] += 1
            expected_joint = (
                all(status == "authoritative" for status in view_statuses.values()) and len(view_statuses) == 2
            )
            if bool(clip.get("sync", {}).get("authoritative_joint_eligible")) != expected_joint:
                errors.append(f"{clips_path}:{line_number}: authoritative_joint_eligible 不一致")
            authoritative_count += int(expected_joint)
    if clip_count != int(manifest.get("clip_count", -1)):
        errors.append("clip_count 与 manifest 不一致")
    if sha256_file(clips_path) != manifest.get("clips_jsonl_sha256"):
        errors.append("clips JSONL SHA-256 与 manifest 不一致")
    if dict(status_counts) != manifest.get("sync_status_counts", {}):
        errors.append("sync_status_counts 与 manifest 不一致")
    return {
        "schema_version": "match_state_rgb_canonical_sync_integrity.v1",
        "status": "passed" if not errors else "failed",
        "verified_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "sync_manifest": str(sync_manifest_path),
        "clip_count": clip_count,
        "authoritative_joint_clip_count": authoritative_count,
        "sync_status_counts": dict(status_counts),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 RGB canonical-sync v2 manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sync-assets-manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.manifest, args.sync_assets_manifest)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
