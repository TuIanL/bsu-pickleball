#!/usr/bin/env python3
"""建立比赛状态实验使用的权威同步资产清单。

该脚本只读取已有的 session metadata、PTS sidecar 和 sync calibration，不解码视频。
camera role 与旧系统 camera id 的绑定必须来自 session metadata，不能依靠文件名猜测。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "match_state_sync_asset_manifest.v1"
SYNC_SCHEMA_VERSION = "dual_camera_sync_calibration.v1"


def resolve_system_sync_core() -> Path:
    path = Path(__file__).resolve().parents[1] / "backend" / "app" / "services" / "dual_camera_sync.py"
    if not path.is_file():
        raise ValueError(f"找不到旧系统同步核心: {path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def inspect_pts(path: Path) -> dict[str, Any]:
    first_pts: float | None = None
    last_pts: float | None = None
    previous_index = -1
    previous_pts: float | None = None
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            index = int(row["frame_index"])
            pts = float(row["pts_seconds"])
            if index <= previous_index:
                raise ValueError(f"{path}:{line_number}: frame_index 必须严格递增")
            if not math.isfinite(pts) or (previous_pts is not None and pts < previous_pts):
                raise ValueError(f"{path}:{line_number}: PTS 必须有限且单调不降")
            first_pts = pts if first_pts is None else first_pts
            last_pts = pts
            previous_index = index
            previous_pts = pts
            count += 1
    if count == 0 or first_pts is None or last_pts is None:
        raise ValueError(f"PTS sidecar 为空: {path}")
    duration = last_pts - first_pts
    return {
        "frame_count": count,
        "first_pts_seconds": first_pts,
        "last_pts_seconds": last_pts,
        "duration_seconds": max(0.0, duration),
        "estimated_fps": (count - 1) / duration if count > 1 and duration > 0 else None,
    }


def find_pts_sidecar(take_dir: Path, camera_id: str) -> Path:
    preferred = take_dir / f"{camera_id}_merged.mp4.pts.jsonl"
    if preferred.is_file():
        return preferred
    candidates = sorted(
        path
        for path in take_dir.glob(f"{camera_id}*.pts.jsonl")
        if not path.name.startswith("._") and ".bak" not in path.name and path.is_file()
    )
    if len(candidates) != 1:
        raise ValueError(f"无法唯一确定 camera_id={camera_id} 的 PTS sidecar: {candidates}")
    return candidates[0]


def build_manifest(
    *,
    dataset_manifest_path: Path,
    audit_path: Path,
    capture_root: Path,
) -> dict[str, Any]:
    sync_core_path = resolve_system_sync_core()
    sync_core_sha256 = sha256_file(sync_core_path)
    dataset = load_json(dataset_manifest_path)
    audit = load_json(audit_path)
    sessions = {
        str(item["session_id"]): item
        for item in audit.get("sessions", [])
        if isinstance(item, dict) and item.get("dataset_included") is True
    }
    entries: list[dict[str, Any]] = []
    for take in dataset.get("takes", []):
        session_id = str(take["source_session_id"])
        session = sessions.get(session_id)
        if session is None:
            raise ValueError(f"audit 缺少 dataset_included session: {session_id}")
        camera_slots = session.get("camera_slots")
        if not isinstance(camera_slots, dict):
            raise ValueError(f"session 缺少 camera_slots: {session_id}")
        calibration_path = capture_root / f"take_{session_id}" / "timeline" / "sync_calibration.json"
        anchors_path = capture_root / f"take_{session_id}" / "timeline" / "sync_anchors.v1.json"
        confirmation_path = capture_root / f"take_{session_id}" / "timeline" / "sync_anchor_confirmation.json"
        calibration = load_json(calibration_path)
        if calibration.get("schema_version") != SYNC_SCHEMA_VERSION:
            raise ValueError(f"同步校准 schema 不匹配: {calibration_path}")
        reference_camera_id = str(calibration.get("reference_camera", ""))
        if not reference_camera_id:
            raise ValueError(f"同步校准缺少 reference_camera: {calibration_path}")
        mappings = calibration.get("mappings")
        if not isinstance(mappings, dict):
            raise ValueError(f"同步校准缺少 mappings: {calibration_path}")

        camera_entries: list[dict[str, Any]] = []
        revision_inputs: dict[str, Any] = {
            "schema_version": SYNC_SCHEMA_VERSION,
            "source_session_id": session_id,
            "sync_core_sha256": sync_core_sha256,
            "calibration_sha256": sha256_file(calibration_path),
            "anchors_sha256": sha256_file(anchors_path) if anchors_path.is_file() else None,
            "confirmation_sha256": sha256_file(confirmation_path) if confirmation_path.is_file() else None,
            "cameras": {},
        }
        for media in sorted(take.get("media", []), key=lambda item: str(item.get("camera_role"))):
            role = str(media["camera_role"])
            slot = camera_slots.get(role)
            if not isinstance(slot, dict) or not slot.get("camera_id"):
                raise ValueError(f"session metadata 缺少 {role} camera_id: {session_id}")
            camera_id = str(slot["camera_id"])
            pts_path = find_pts_sidecar(capture_root / f"take_{session_id}", camera_id)
            pts_summary = inspect_pts(pts_path)
            mapping = mappings.get(camera_id)
            if not isinstance(mapping, dict):
                raise ValueError(f"同步校准缺少 camera_id={camera_id}: {calibration_path}")
            if (
                str(mapping.get("reference_camera")) != reference_camera_id
                or str(mapping.get("camera_id")) != camera_id
            ):
                raise ValueError(f"同步校准 camera identity 不一致: {calibration_path} / {camera_id}")
            timing = {
                "authority": "source_pts",
                "source_path": str(pts_path),
                "remote_relative_path": f"timing/{session_id}/{role}.pts.jsonl",
                "sha256": sha256_file(pts_path),
                **pts_summary,
            }
            camera_entry = {
                "camera_role": role,
                "camera_id": camera_id,
                "reference_camera_id": reference_camera_id,
                "logical_media_uri": media.get("logical_uri"),
                "remote_media_relative_path": media.get("remote_relative_path"),
                "timing": timing,
                "mapping": mapping,
            }
            camera_entries.append(camera_entry)
            revision_inputs["cameras"][role] = {
                "camera_id": camera_id,
                "pts_sha256": timing["sha256"],
                "mapping": mapping,
            }
        if {item["camera_role"] for item in camera_entries} != {"cam_1", "cam_2"}:
            raise ValueError(f"同步资产必须包含 cam_1/cam_2: {session_id}")
        sync_revision = f"syncv2_{canonical_sha256(revision_inputs)[:24]}"
        entries.append(
            {
                "capture_take_id": take["capture_take_id"],
                "source_session_id": session_id,
                "reference_camera_id": reference_camera_id,
                "sync_revision": sync_revision,
                "sync_quality": max(
                    (str(item["mapping"].get("quality", "unknown")) for item in camera_entries),
                    key=lambda value: {"good": 0, "degraded": 1, "unknown": 2}.get(value, 2),
                ),
                "source": str(calibration.get("source", "unknown")),
                "anchor_count": calibration.get("anchor_count"),
                "calibration": {
                    "source_path": str(calibration_path),
                    "remote_relative_path": f"sync/{session_id}/sync_calibration.json",
                    "sha256": revision_inputs["calibration_sha256"],
                },
                "anchors": {
                    "source_path": str(anchors_path) if anchors_path.is_file() else None,
                    "remote_relative_path": f"sync/{session_id}/sync_anchors.v1.json"
                    if anchors_path.is_file()
                    else None,
                    "sha256": revision_inputs["anchors_sha256"],
                },
                "confirmation": {
                    "source_path": str(confirmation_path) if confirmation_path.is_file() else None,
                    "remote_relative_path": f"sync/{session_id}/sync_anchor_confirmation.json"
                    if confirmation_path.is_file()
                    else None,
                    "sha256": revision_inputs["confirmation_sha256"],
                },
                "cameras": camera_entries,
                "sync_core_sha256": sync_core_sha256,
            }
        )
    identity = {
        "dataset_manifest_id": dataset.get("manifest_id"),
        "dataset_manifest_sha256": sha256_file(dataset_manifest_path),
        "audit_sha256": sha256_file(audit_path),
        "camera_role_mapping_source": "audit.sessions.camera_slots",
        "timing_authority_policy": "source_pts_required_for_authoritative_joint",
        "mapping_formula_source": "backend.app.services.dual_camera_sync",
        "canonical_clock_source": "backend.app.vision.multiview.analysis_clock_contract",
        "sync_core_sha256": sync_core_sha256,
        "sync_core_relative_path": "backend/app/services/dual_camera_sync.py",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": f"syncassets_{canonical_sha256(identity)[:24]}",
        "generated_at": datetime.now(UTC).isoformat(),
        "identity": identity,
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成比赛状态实验权威同步资产清单")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        dataset_manifest_path=args.dataset_manifest,
        audit_path=args.audit,
        capture_root=args.capture_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "manifest_id": manifest["manifest_id"],
                "take_count": len(manifest["entries"]),
                "sync_revisions": [item["sync_revision"] for item in manifest["entries"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
