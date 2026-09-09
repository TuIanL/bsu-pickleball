#!/usr/bin/env python3
"""从本地 CaptureTake 和人工边界复核结果生成单场 RGB 推理清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def latest_reviews(connection: sqlite3.Connection, take_id: str) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, input_segment_ids, payload_json, created_at
        FROM segment_edit_operations
        WHERE capture_take_id = ? AND operation_type = 'boundary_correction'
        ORDER BY created_at ASC, id ASC
        """,
        (take_id,),
    ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        if payload.get("schema_version") != "match-state-boundary-review.v1":
            continue
        for segment_id in json.loads(row["input_segment_ids"] or "[]"):
            latest[str(segment_id)] = {
                **payload,
                "operation_id": row["id"],
                "reviewed_at": row["created_at"],
            }
    return latest


def media_path(session: dict[str, Any], role: str, camera_id: str) -> Path:
    for segment in session.get("segments", []):
        for item in segment.get("files", []):
            if item.get("role") != role:
                continue
            source = Path(str(item.get("file_path", "")))
            merged = source.parent / f"{camera_id}_merged.mp4"
            if merged.is_file():
                return merged
            if source.is_file():
                return source
    raise FileNotFoundError(f"找不到 {role} 的视频文件")


def build_manifest(database: Path, session_json: Path, take_id: str) -> dict[str, Any]:
    session = json.loads(session_json.read_text(encoding="utf-8"))
    session_id = str(session["session_id"])
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    take = connection.execute(
        "SELECT id, source_session_id, duration_ms FROM capture_takes WHERE id = ?",
        (take_id,),
    ).fetchone()
    if take is None or take["duration_ms"] is None:
        raise ValueError(f"CaptureTake 不存在或缺少时长: {take_id}")
    reviews = latest_reviews(connection, take_id)
    segments = connection.execute(
        """
        SELECT id, ordinal, start_ms, end_ms, source, created_by_operation_id
        FROM capture_segments
        WHERE capture_take_id = ? AND segment_type = 'rally' AND edit_status != 'superseded'
        ORDER BY ordinal ASC
        """,
        (take_id,),
    ).fetchall()
    labels = []
    for segment in segments:
        review = reviews.get(str(segment["id"]))
        if not review or review.get("review_status") == "excluded":
            continue
        start_ms = int(review["reviewed_start_ms"])
        end_ms = int(review["reviewed_end_ms"])
        if end_ms <= start_ms:
            raise ValueError(f"非法人工边界: {segment['id']}")
        labels.append(
            {
                "segment_id": segment["id"],
                "ordinal": segment["ordinal"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "review_status": review["review_status"],
                "review_operation_id": review["operation_id"],
                "reviewed_at": review["reviewed_at"],
                "created_by_operation_id": segment["created_by_operation_id"],
            }
        )

    camera_slots = session.get("camera_slots", {})
    media = []
    for role in ("cam_1", "cam_2"):
        slot = camera_slots.get(role, {})
        camera_id = str(slot.get("camera_id") or "")
        path = media_path(session, role, camera_id)
        sidecar = Path(f"{path}.pts.jsonl")
        media.append(
            {
                "camera_role": role,
                "logical_uri": f"matchstate://2026-07-20/{session_id}/{role}",
                # prepare_match_state_rgb_cache.py 接受绝对路径；这样本地外接盘
                # 不需要复制到仓库或伪造远程相对路径。
                "remote_relative_path": str(path),
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "fingerprint_method": "size_bytes+mtime_ns",
                "take_time_mapping": {
                    "offset_ms": 0,
                    "offset_source": "manual",
                    "sync_quality": "good",
                    "timing_authority": "source_pts" if sidecar.is_file() else "video_pts",
                    "timing_sidecar_path": str(sidecar) if sidecar.is_file() else None,
                    "timing_failure_reason": None,
                },
            }
        )
    connection.close()

    payload = {
        "schema_version": "match_state_dataset_manifest.v1",
        "source": "local_capture_take_manual_boundary_review",
        "takes": [
            {
                "capture_take_id": take_id,
                "source_session_id": session_id,
                "duration_ms": int(take["duration_ms"]),
                "timebase": "capture_take_relative_ms",
                "media": media,
                "retained_rally_count": len(labels),
                "excluded_segment_ids": [],
                "suppressed_duplicate_segment_ids": [],
                "labels": labels,
            }
        ],
    }
    manifest_id = f"msd_local_{sha256_bytes(canonical_bytes(payload))[:16]}"
    return {
        **payload,
        "manifest_id": manifest_id,
        "take_count": 1,
        "rally_count": len(labels),
        "generated_at": datetime.now(UTC).isoformat(),
        "source_paths": {"database": str(database.resolve()), "session_json": str(session_json.resolve())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成单场本地 RGB 推理清单")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--session-json", type=Path, required=True)
    parser.add_argument("--take-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.database, args.session_json, args.take_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("manifest_id", "take_count", "rally_count")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
