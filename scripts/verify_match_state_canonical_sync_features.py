#!/usr/bin/env python3
"""校验 canonical-sync v2 特征缓存的完整性、单调性和同步门控。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "match_state_canonical_sync_manifest.v2"
FEATURE_SCHEMA_VERSION = "match_state_canonical_sync_feature.v2"
STATUSES = {"authoritative", "degraded", "extrapolated", "unavailable"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 3)


def verify(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    root = manifest_path.parent
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    total_records = 0
    total_authoritative = 0
    total_view_records = Counter()
    total_statuses = Counter()
    all_source_errors: list[float] = []
    all_feature_errors: list[float] = []
    identity = manifest.get("identity") or {}
    source_limit_ms = float(identity.get("max_source_selection_error_ms", 33.333))
    feature_limit_ms = float(identity.get("max_feature_selection_gap_ms", 60.0))

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"manifest schema 不正确: {manifest.get('schema_version')}")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        errors.append("manifest entries 为空或不是数组")
        raw_entries = []

    for item in raw_entries:
        if not isinstance(item, dict):
            errors.append("manifest entry 不是对象")
            continue
        relative_path = str(item.get("path", ""))
        path = root / relative_path
        entry_report: dict[str, Any] = {
            "path": str(path),
            "source_session_id": item.get("source_session_id"),
            "expected_record_count": item.get("record_count"),
            "status": "failed",
        }
        if not path.is_file():
            errors.append(f"缺少 v2 特征文件: {path}")
            entries.append(entry_report)
            continue

        previous_timestamp: float | None = None
        previous_source_frame: dict[str, int] = {}
        record_count = 0
        authoritative_count = 0
        statuses = Counter()
        view_records = Counter()
        source_errors: list[float] = []
        feature_errors: list[float] = []
        first_timestamp: float | None = None
        last_timestamp: float | None = None
        parse_failed = False
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{line_number}: JSON 无法解析: {exc}")
                    parse_failed = True
                    continue
                if not isinstance(record, dict):
                    errors.append(f"{path}:{line_number}: 记录不是对象")
                    parse_failed = True
                    continue
                record_count += 1
                if record.get("schema_version") != FEATURE_SCHEMA_VERSION:
                    errors.append(f"{path}:{line_number}: 特征 schema 不正确")
                timestamp = record.get("canonical_timestamp_ms")
                if not isinstance(timestamp, (int, float)):
                    errors.append(f"{path}:{line_number}: canonical_timestamp_ms 缺失")
                    continue
                timestamp = float(timestamp)
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    errors.append(f"{path}:{line_number}: canonical 时间未严格递增")
                if first_timestamp is None:
                    first_timestamp = timestamp
                last_timestamp = timestamp
                previous_timestamp = timestamp
                sync = record.get("sync") or {}
                if record.get("sync_revision") != item.get("sync_revision"):
                    errors.append(f"{path}:{line_number}: sync_revision 与 manifest 不一致")
                status = str(sync.get("status", "unavailable"))
                if status not in STATUSES:
                    errors.append(f"{path}:{line_number}: 非法 sync status={status}")
                statuses[status] += 1
                if bool(record.get("quality", {}).get("authoritative_joint_eligible")):
                    authoritative_count += 1
                    if status != "authoritative":
                        errors.append(f"{path}:{line_number}: authoritative 标志与 sync status 冲突")
                views = record.get("views") or {}
                if set(views) != {"cam_1", "cam_2"}:
                    errors.append(f"{path}:{line_number}: views 必须精确包含 cam_1/cam_2")
                for role in ("cam_1", "cam_2"):
                    view = views.get(role) or {}
                    source = view.get("source") or {}
                    view_status = str(source.get("sync_status", "unavailable"))
                    view_records[role] += int(bool(view.get("quality", {}).get("structured_available")))
                    if source.get("sync_revision") != record.get("sync_revision"):
                        errors.append(f"{path}:{line_number}: {role} sync_revision 不一致")
                    source_frame = source.get("source_frame_index")
                    if source_frame is not None:
                        source_frame = int(source_frame)
                        if source_frame <= previous_source_frame.get(role, -1):
                            errors.append(f"{path}:{line_number}: {role} source frame 未严格递增")
                        previous_source_frame[role] = source_frame
                    source_error = source.get("alignment_error_ms")
                    if source_error is not None:
                        source_error = abs(float(source_error))
                        source_errors.append(source_error)
                        if source_error > source_limit_ms + 0.01:
                            errors.append(f"{path}:{line_number}: {role} source 对齐误差超过门槛")
                    feature_error = source.get("feature_alignment_error_ms")
                    if feature_error is not None:
                        feature_error = abs(float(feature_error))
                        feature_errors.append(feature_error)
                        if feature_error > feature_limit_ms + 0.01:
                            errors.append(f"{path}:{line_number}: {role} feature 对齐误差超过门槛")
                    if view_status != "unavailable":
                        if source_frame is None:
                            errors.append(f"{path}:{line_number}: {role} 可用但缺少 source_frame_index")
                        if source.get("source_pts_ms") is None:
                            errors.append(f"{path}:{line_number}: {role} 可用但缺少 source_pts_ms")
                    if (
                        view.get("quality", {}).get("structured_available")
                        and source.get("feature_source_frame_index") is None
                    ):
                        errors.append(f"{path}:{line_number}: {role} structured 可用但缺少 feature_source_frame_index")
                    if view_status == "unavailable" and view.get("quality", {}).get("view_missing") is not True:
                        errors.append(f"{path}:{line_number}: {role} unavailable 却未设置 view_missing")
                total_statuses[status] += 1

        expected_count = int(item.get("record_count", -1))
        if record_count != expected_count:
            errors.append(f"{path}: 行数 {record_count} != manifest {expected_count}")
        if first_timestamp != item.get("timestamp_start_ms"):
            errors.append(f"{path}: 起始时间与 manifest 不一致")
        if last_timestamp != item.get("timestamp_end_ms"):
            errors.append(f"{path}: 结束时间与 manifest 不一致")
        if authoritative_count != int(item.get("authoritative_joint_record_count", -1)):
            errors.append(f"{path}: authoritative 行数与 manifest 不一致")
        if dict(statuses) != dict(item.get("sync_status_counts", {})):
            errors.append(f"{path}: sync_status_counts 与 manifest 不一致")
        actual_sha = sha256_file(path)
        if actual_sha != item.get("sha256"):
            errors.append(f"{path}: SHA-256 与 manifest 不一致")
        if path.stat().st_size != int(item.get("size_bytes", -1)):
            errors.append(f"{path}: 文件大小与 manifest 不一致")
        entry_report.update(
            {
                "status": "failed" if parse_failed else "complete",
                "record_count": record_count,
                "authoritative_joint_record_count": authoritative_count,
                "sync_status_counts": dict(statuses),
                "structured_record_counts": dict(view_records),
                "source_alignment_error_ms": {
                    "max": round(max(source_errors), 3) if source_errors else None,
                    "p95": percentile(source_errors, 0.95),
                },
                "feature_alignment_error_ms": {
                    "max": round(max(feature_errors), 3) if feature_errors else None,
                    "p95": percentile(feature_errors, 0.95),
                },
                "actual_record_count": record_count,
                "sha256": actual_sha,
                "size_bytes": path.stat().st_size,
                "first_timestamp_ms": first_timestamp,
                "last_timestamp_ms": last_timestamp,
            }
        )
        entries.append(entry_report)
        total_records += record_count
        total_authoritative += authoritative_count
        all_source_errors.extend(source_errors)
        all_feature_errors.extend(feature_errors)
        for role, count in view_records.items():
            total_view_records[role] += count

    partials = sorted(path.name for path in root.iterdir() if path.is_file() and path.name.endswith(".partial"))
    if partials:
        errors.append(f"存在未封口 partial 文件: {partials}")
    expected_sessions = {str(item.get("source_session_id")) for item in raw_entries}
    if len(expected_sessions) != len(raw_entries):
        errors.append("manifest 中 source_session_id 重复")
    if any(not item.get("sync_revision") for item in raw_entries if isinstance(item, dict)):
        errors.append("manifest entry 缺少 sync_revision")

    return {
        "schema_version": "match_state_canonical_sync_feature_integrity.v1",
        "status": "passed" if not errors else "failed",
        "verified_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "manifest_schema_version": manifest.get("schema_version"),
        "entry_count": len(raw_entries),
        "record_count": total_records,
        "authoritative_joint_record_count": total_authoritative,
        "structured_record_counts": dict(total_view_records),
        "sync_status_counts": dict(total_statuses),
        "alignment_error_ms": {
            "source_max": round(max(all_source_errors), 3) if all_source_errors else None,
            "source_p95": percentile(all_source_errors, 0.95),
            "feature_max": round(max(all_feature_errors), 3) if all_feature_errors else None,
            "feature_p95": percentile(all_feature_errors, 0.95),
            "source_limit": source_limit_ms,
            "feature_limit": feature_limit_ms,
        },
        "entries": entries,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 canonical-sync v2 对齐缓存")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.manifest)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
