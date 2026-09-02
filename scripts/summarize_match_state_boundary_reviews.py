#!/usr/bin/env python3
"""汇总人工复核后的比赛状态边界、历史误差和正负样本时长。"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


SCHEMA_VERSION = "match_state_boundary_review_summary.v1"
REVIEW_SCHEMA_VERSION = "match-state-boundary-review.v1"


def _latest_reviews(connection: sqlite3.Connection, take_ids: list[str]) -> dict[str, dict[str, Any]]:
    placeholders = ",".join("?" for _ in take_ids)
    rows = connection.execute(
        f"""
        SELECT id, capture_take_id, input_segment_ids, payload_json, created_at
        FROM segment_edit_operations
        WHERE operation_type = 'boundary_correction'
          AND capture_take_id IN ({placeholders})
        ORDER BY created_at ASC
        """,
        take_ids,
    ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        if payload.get("schema_version") != REVIEW_SCHEMA_VERSION:
            continue
        for segment_id in json.loads(row["input_segment_ids"] or "[]"):
            latest[str(segment_id)] = {
                **payload,
                "operation_id": row["id"],
                "reviewed_at": row["created_at"],
            }
    return latest


def _near_duplicate(first: sqlite3.Row, second: sqlite3.Row) -> bool:
    if first["end_ms"] is None or second["end_ms"] is None:
        return False
    if abs(first["start_ms"] - second["start_ms"]) <= 250 and abs(first["end_ms"] - second["end_ms"]) <= 250:
        return True
    overlap = max(0, min(first["end_ms"], second["end_ms"]) - max(first["start_ms"], second["start_ms"]))
    union = max(first["end_ms"], second["end_ms"]) - min(first["start_ms"], second["start_ms"])
    return union > 0 and overlap / union >= 0.95


def _preference(segment: sqlite3.Row, review: dict[str, Any]) -> tuple[int, ...]:
    review_rank = {"corrected": 4, "confirmed": 3, "pending": 2, "excluded": 1}.get(
        str(review.get("review_status") or "pending"), 0
    )
    source_rank = {"corrected": 4, "manual": 3, "vidat_import": 2, "algorithm": 1}.get(
        str(segment["source"]), 0
    )
    return (
        review_rank,
        source_rank,
        int(segment["annotation_package_id"] is None),
        int(segment["parent_segment_id"] is not None),
        int(segment["edit_version"] or 0),
    )


def _deduplicate(
    segments: list[sqlite3.Row], reviews: dict[str, dict[str, Any]]
) -> tuple[list[sqlite3.Row], list[str]]:
    kept: list[sqlite3.Row] = []
    suppressed: list[str] = []
    for segment in sorted(segments, key=lambda item: (item["start_ms"], item["end_ms"] or 2**63)):
        duplicate_index = next(
            (index for index, current in enumerate(kept) if _near_duplicate(current, segment)), None
        )
        if duplicate_index is None:
            kept.append(segment)
            continue
        current = kept[duplicate_index]
        if _preference(segment, reviews[segment["id"]]) > _preference(current, reviews[current["id"]]):
            kept[duplicate_index] = segment
            suppressed.append(current["id"])
        else:
            suppressed.append(segment["id"])
    return kept, suppressed


def _union_duration(intervals: list[tuple[int, int]]) -> int:
    total = 0
    current_start: int | None = None
    current_end: int | None = None
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if current_start is None:
            current_start, current_end = start, end
        elif start <= int(current_end):
            current_end = max(int(current_end), end)
        else:
            total += int(current_end) - current_start
            current_start, current_end = start, end
    if current_start is not None:
        total += int(current_end) - current_start
    return total


def _nearest_rank(values: list[int], proportion: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * proportion) - 1)]


def _round_up(value: int | None, step: int) -> int | None:
    return None if value is None else math.ceil(value / step) * step


def build_summary(database: Path, take_ids: list[str], corrected_buffer_ms: int) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    reviews = _latest_reviews(connection, take_ids)
    per_take: list[dict[str, Any]] = []
    start_deltas: list[int] = []
    end_deltas: list[int] = []

    for take_id in take_ids:
        take = connection.execute(
            "SELECT id, source_session_id, duration_ms FROM capture_takes WHERE id = ?", (take_id,)
        ).fetchone()
        if take is None:
            raise ValueError(f"CaptureTake 不存在: {take_id}")
        segments = connection.execute(
            """
            SELECT * FROM capture_segments
            WHERE capture_take_id = ? AND segment_type = 'rally' AND edit_status != 'superseded'
            ORDER BY start_ms
            """,
            (take_id,),
        ).fetchall()
        reviewed_segments = [segment for segment in segments if segment["id"] in reviews]
        reviewed_segments, suppressed = _deduplicate(reviewed_segments, reviews)
        retained: list[sqlite3.Row] = []
        excluded = 0
        confirmed = 0
        corrected = 0
        created = 0
        take_start_deltas: list[int] = []
        take_end_deltas: list[int] = []
        active_intervals: list[tuple[int, int]] = []
        expanded_active_intervals: list[tuple[int, int]] = []

        for segment in reviewed_segments:
            review = reviews[segment["id"]]
            status = str(review.get("review_status"))
            if status == "excluded":
                excluded += 1
                continue
            retained.append(segment)
            confirmed += int(status == "confirmed")
            corrected += int(status == "corrected")
            created += int(segment["created_by_operation_id"] is not None)
            start = int(review.get("reviewed_start_ms"))
            end = int(review.get("reviewed_end_ms"))
            if end <= start:
                raise ValueError(f"非法复核边界: {segment['id']} {start}..{end}")
            active_intervals.append((start, end))
            expanded_active_intervals.append(
                (
                    max(0, start - corrected_buffer_ms),
                    min(int(take["duration_ms"]), end + corrected_buffer_ms),
                )
            )
            if segment["created_by_operation_id"] is None and segment["source"] == "manual":
                start_delta = start - int(segment["start_ms"])
                end_delta = end - int(segment["end_ms"])
                take_start_deltas.append(start_delta)
                take_end_deltas.append(end_delta)
                start_deltas.append(start_delta)
                end_deltas.append(end_delta)

        duration_ms = int(take["duration_ms"])
        active_ms = _union_duration(active_intervals)
        high_confidence_active_ms = _union_duration(
            [(start + corrected_buffer_ms, end - corrected_buffer_ms) for start, end in active_intervals]
        )
        high_confidence_non_play_ms = max(0, duration_ms - _union_duration(expanded_active_intervals))
        transition_uncertain_ms = max(
            0, duration_ms - high_confidence_active_ms - high_confidence_non_play_ms
        )
        per_take.append(
            {
                "capture_take_id": take_id,
                "source_session_id": take["source_session_id"],
                "duration_ms": duration_ms,
                "reviewed_candidate_count": len(reviewed_segments),
                "retained_rally_count": len(retained),
                "corrected_count": corrected,
                "confirmed_count": confirmed,
                "excluded_count": excluded,
                "created_rally_count": created,
                "suppressed_duplicate_count": len(suppressed),
                "suppressed_duplicate_segment_ids": suppressed,
                "rally_active_duration_ms": active_ms,
                "non_play_duration_ms": max(0, duration_ms - active_ms),
                "high_confidence_rally_active_duration_ms": high_confidence_active_ms,
                "high_confidence_non_play_duration_ms": high_confidence_non_play_ms,
                "uncertain_duration_ms": transition_uncertain_ms,
                "legacy_boundary_comparison_count": len(take_start_deltas),
                "legacy_start_delta_median_ms": median(take_start_deltas) if take_start_deltas else None,
                "legacy_end_delta_median_ms": median(take_end_deltas) if take_end_deltas else None,
            }
        )

    total_duration = sum(item["duration_ms"] for item in per_take)
    total_active = sum(item["rally_active_duration_ms"] for item in per_take)
    p90_start = _nearest_rank([abs(value) for value in start_deltas], 0.9)
    p90_end = _nearest_rank([abs(value) for value in end_deltas], 0.9)
    connection.close()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "database_path": str(database.resolve()),
        "take_ids": take_ids,
        "all_takes_fully_reviewed": all(item["reviewed_candidate_count"] > 0 for item in per_take),
        "summary": {
            "take_count": len(per_take),
            "retained_rally_count": sum(item["retained_rally_count"] for item in per_take),
            "excluded_count": sum(item["excluded_count"] for item in per_take),
            "created_rally_count": sum(item["created_rally_count"] for item in per_take),
            "suppressed_duplicate_count": sum(item["suppressed_duplicate_count"] for item in per_take),
            "total_duration_ms": total_duration,
            "rally_active_duration_ms": total_active,
            "non_play_duration_ms": total_duration - total_active,
            "rally_active_fraction": round(total_active / total_duration, 6),
            "legacy_boundary_comparison_count": len(start_deltas),
            "legacy_start_delta_mean_ms": round(mean(start_deltas), 1),
            "legacy_start_delta_median_ms": median(start_deltas),
            "legacy_end_delta_mean_ms": round(mean(end_deltas), 1),
            "legacy_end_delta_median_ms": median(end_deltas),
            "legacy_start_abs_error_p90_ms": p90_start,
            "legacy_end_abs_error_p90_ms": p90_end,
        },
        "label_buffer_policy": {
            "reviewed_boundary_uncertain_radius_ms": corrected_buffer_ms,
            "reviewed_boundary_reason": "人工逐帧复核后仅屏蔽语义转换瞬间和帧级定位误差",
            "unreviewed_legacy_start_uncertain_radius_ms": _round_up(p90_start, 500),
            "unreviewed_legacy_end_uncertain_radius_ms": _round_up(p90_end, 500),
            "unreviewed_legacy_reason": "仅供未来未复核旧标注降级使用；当前7场不使用",
        },
        "per_take": per_take,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总比赛状态人工边界复核")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--take-id", action="append", required=True)
    parser.add_argument("--corrected-buffer-ms", type=int, default=250)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.database, args.take_id, max(0, args.corrected_buffer_ms))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
