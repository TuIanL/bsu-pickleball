#!/usr/bin/env python3
"""生成由人工复核边界锁定的第一版不可变比赛状态数据清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from summarize_match_state_boundary_reviews import _deduplicate, _latest_reviews


SCHEMA_VERSION = "match_state_dataset_manifest.v1"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_manifest(
    database: Path,
    audit_path: Path,
    review_summary_path: Path,
    label_profile_path: Path,
) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    review_summary = json.loads(review_summary_path.read_text(encoding="utf-8"))
    take_ids = list(review_summary["take_ids"])
    reviews: dict[str, dict[str, Any]]
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    reviews = _latest_reviews(connection, take_ids)
    sessions_by_take = {
        str(item["capture_take_id"]): item
        for item in audit.get("sessions") or []
        if item.get("dataset_included") and item.get("capture_take_id")
    }
    takes: list[dict[str, Any]] = []
    label_snapshot: list[dict[str, Any]] = []

    for take_id in take_ids:
        session = sessions_by_take.get(take_id)
        if session is None:
            raise ValueError(f"审计报告缺少 included session: {take_id}")
        take = connection.execute(
            "SELECT duration_ms FROM capture_takes WHERE id = ?", (take_id,)
        ).fetchone()
        if take is None or take["duration_ms"] is None:
            raise ValueError(f"CaptureTake 缺少时长: {take_id}")
        track_rows = connection.execute(
            """
            SELECT slot, offset_ms, offset_source, sync_quality, timing_authority,
                   timing_sidecar_path, timing_failure_reason
            FROM capture_tracks
            WHERE capture_take_id = ?
            ORDER BY slot
            """,
            (take_id,),
        ).fetchall()
        track_by_slot = {str(row["slot"]): row for row in track_rows}
        segments = connection.execute(
            """
            SELECT * FROM capture_segments
            WHERE capture_take_id = ? AND segment_type = 'rally' AND edit_status != 'superseded'
            ORDER BY start_ms
            """,
            (take_id,),
        ).fetchall()
        reviewed = [segment for segment in segments if segment["id"] in reviews]
        reviewed, suppressed = _deduplicate(reviewed, reviews)
        retained_labels: list[dict[str, Any]] = []
        excluded_ids: list[str] = []
        for segment in reviewed:
            review = reviews[segment["id"]]
            if review.get("review_status") == "excluded":
                excluded_ids.append(segment["id"])
                continue
            label = {
                "segment_id": segment["id"],
                "ordinal": segment["ordinal"],
                "start_ms": int(review["reviewed_start_ms"]),
                "end_ms": int(review["reviewed_end_ms"]),
                "review_status": review["review_status"],
                "review_operation_id": review["operation_id"],
                "reviewed_at": review["reviewed_at"],
                "created_by_operation_id": segment["created_by_operation_id"],
            }
            retained_labels.append(label)
            label_snapshot.append({"capture_take_id": take_id, **label})

        media: list[dict[str, Any]] = []
        for item in session.get("media_files") or []:
            if item.get("role") not in {"cam_1", "cam_2"}:
                continue
            resolved_path = Path(str(item.get("resolved_path") or item.get("declared_path")))
            stat = resolved_path.stat()
            track = track_by_slot.get(str(item["role"]))
            media.append(
                {
                    "camera_role": item["role"],
                    "logical_uri": (
                        f"matchstate://2026-07-20/{session['session_id']}/{item['role']}"
                    ),
                    "remote_relative_path": f"media/{session['session_id']}/{item['role']}.ts",
                    "path": str(resolved_path),
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "fingerprint_method": "size_bytes+mtime_ns",
                    "take_time_mapping": {
                        "offset_ms": int(track["offset_ms"]) if track is not None else 0,
                        "offset_source": track["offset_source"] if track is not None else "missing",
                        "sync_quality": track["sync_quality"] if track is not None else "unknown",
                        "timing_authority": track["timing_authority"] if track is not None else "missing",
                        "timing_sidecar_path": track["timing_sidecar_path"] if track is not None else None,
                        "timing_failure_reason": track["timing_failure_reason"] if track is not None else "track_missing",
                    },
                }
            )
        if {item["camera_role"] for item in media} != {"cam_1", "cam_2"}:
            raise ValueError(f"双摄媒体不完整: {take_id}")
        takes.append(
            {
                "capture_take_id": take_id,
                "source_session_id": session["session_id"],
                "duration_ms": int(take["duration_ms"]),
                "timebase": "capture_take_relative_ms",
                "media": sorted(media, key=lambda item: item["camera_role"]),
                "retained_rally_count": len(retained_labels),
                "excluded_segment_ids": excluded_ids,
                "suppressed_duplicate_segment_ids": suppressed,
                "labels": retained_labels,
            }
        )

    connection.close()
    label_snapshot_sha256 = _sha256_bytes(_canonical_bytes(label_snapshot))
    immutable_payload = {
        "schema_version": SCHEMA_VERSION,
        "source_audit_sha256": _sha256_file(audit_path),
        "boundary_review_summary_sha256": _sha256_file(review_summary_path),
        "label_profile_sha256": _sha256_file(label_profile_path),
        "label_snapshot_sha256": label_snapshot_sha256,
        "take_count": len(takes),
        "rally_count": len(label_snapshot),
        "takes": takes,
    }
    manifest_id = f"msd_20260720_{_sha256_bytes(_canonical_bytes(immutable_payload))[:16]}"
    return {
        **immutable_payload,
        "manifest_id": manifest_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_paths": {
            "audit": str(audit_path.resolve()),
            "boundary_review_summary": str(review_summary_path.resolve()),
            "label_profile": str(label_profile_path.resolve()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成比赛状态不可变数据清单")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--review-summary", type=Path, required=True)
    parser.add_argument("--label-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.database, args.audit, args.review_summary, args.label_profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest_id": manifest["manifest_id"],
                "take_count": manifest["take_count"],
                "rally_count": manifest["rally_count"],
                "label_snapshot_sha256": manifest["label_snapshot_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
