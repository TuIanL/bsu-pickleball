#!/usr/bin/env python3
"""从 match-state 审计报告生成少量人工边界复核清单。"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


def _version_key(item: dict[str, Any]) -> tuple[int, int, str]:
    path = str(item.get("annotation_path") or "")
    match = re.search(r"/v(\d+)-", path)
    version = int(match.group(1)) if match else -1
    revision = int(item.get("timeline_revision") or -1)
    return version, revision, str(item.get("package_id") or "")


def _selected_packages(report: dict[str, Any]) -> list[dict[str, Any]]:
    included_takes = {
        str(session.get("capture_take_id"))
        for session in report.get("sessions") or []
        if session.get("capture_take_id") and session.get("dataset_included", True)
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in report.get("annotations") or []:
        take = item.get("capture_take_id")
        if take and (not included_takes or str(take) in included_takes):
            grouped.setdefault(str(take), []).append(item)
    selected = []
    for values in grouped.values():
        usable = [
            item
            for item in values
            if item.get("status") == "usable"
            and not item.get("invalid_ranges")
            and not item.get("rally_overlap_count")
        ]
        selected.append(max(usable or values, key=_version_key))
    return sorted(selected, key=lambda item: str(item.get("capture_take_id")))


def _session_media_by_take(report: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for session in report.get("sessions") or []:
        take = session.get("capture_take_id")
        if not take:
            continue
        media_by_role: dict[str, str] = {}
        for media in session.get("media_files") or []:
            role = media.get("role")
            path = media.get("resolved_path") or media.get("declared_path")
            if role and path and media.get("exists"):
                media_by_role[str(role)] = str(path)
        result[str(take)] = media_by_role
    return result


def _sample_indexes(count: int, limit: int) -> list[int]:
    if count <= limit:
        return list(range(count))
    if limit <= 1:
        return [0]
    indexes = {round(index * (count - 1) / (limit - 1)) for index in range(limit)}
    return sorted(indexes)


def build_rows(report: dict[str, Any], *, sample_per_take: int, radius_ms: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    media_by_take = _session_media_by_take(report)
    for package in _selected_packages(report):
        take_id = str(package.get("capture_take_id"))
        media = media_by_take.get(take_id, {})
        rallies = [item for item in package.get("boundaries") or [] if item.get("event_type") == "rally_start"]
        duration_ms = round(float((package.get("video") or {}).get("duration_sec") or 0) * 1000)
        for sample_order, sample_index in enumerate(_sample_indexes(len(rallies), sample_per_take), start=1):
            boundary = rallies[sample_index]
            start_ms = int(round(float(boundary["start_ms"])))
            end_ms = int(round(float(boundary["end_ms"])))
            rows.append(
                {
                    "review_id": f"{take_id}:{package.get('package_id')}:{sample_index + 1}",
                    "capture_take_id": package.get("capture_take_id"),
                    "package_id": package.get("package_id"),
                    "annotation_path": package.get("annotation_path"),
                    "cam_1_video_path": media.get("cam_1", ""),
                    "cam_2_video_path": media.get("cam_2", ""),
                    "inferred_time_unit": package.get("inferred_time_unit"),
                    "sample_order": sample_order,
                    "rally_source_action_index": boundary.get("source_action_index", ""),
                    "rough_start_ms": start_ms,
                    "rough_end_ms": end_ms,
                    "start_review_from_ms": max(0, start_ms - radius_ms),
                    "start_review_to_ms": min(duration_ms, start_ms + radius_ms) if duration_ms else start_ms + radius_ms,
                    "end_review_from_ms": max(0, end_ms - radius_ms),
                    "end_review_to_ms": min(duration_ms, end_ms + radius_ms) if duration_ms else end_ms + radius_ms,
                    "exact_start_ms": "",
                    "exact_end_ms": "",
                    "review_status": "pending",
                    "review_note": "",
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="生成比赛状态人工边界复核清单")
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-per-take", type=int, default=6)
    parser.add_argument("--radius-ms", type=int, default=5000)
    args = parser.parse_args()
    report = json.loads(args.audit.read_text(encoding="utf-8"))
    rows = build_rows(report, sample_per_take=max(1, args.sample_per_take), radius_ms=max(1000, args.radius_ms))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["review_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"row_count": len(rows), "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
