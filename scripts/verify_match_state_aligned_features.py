#!/usr/bin/env python3
"""校验统一时间基准特征缓存的封口、行数、首尾时间和文件哈希。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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


def line_count(path: Path) -> int:
    return int(subprocess.check_output(["wc", "-l", str(path)], text=True).split()[0])


def verify(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    root = manifest_path.parent
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    for item in manifest.get("entries", []):
        path = root / str(item.get("path", ""))
        entry = {"path": str(path), "expected_record_count": item.get("record_count")}
        if not path.is_file():
            errors.append(f"缺少特征文件: {path}")
            entries.append(entry)
            continue
        actual_lines = line_count(path)
        with path.open(encoding="utf-8") as handle:
            first = json.loads(handle.readline())
        last = json.loads(subprocess.check_output(["tail", "-n", "1", str(path)], text=True))
        entry.update(
            {
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "actual_record_count": actual_lines,
                "first_timestamp_ms": first.get("take_timestamp_ms"),
                "last_timestamp_ms": last.get("take_timestamp_ms"),
                "schema_version": first.get("schema_version"),
            }
        )
        if actual_lines != item.get("record_count"):
            errors.append(f"{path}: 行数 {actual_lines} != manifest {item.get('record_count')}")
        if first.get("schema_version") != "match_state_aligned_feature.v1":
            errors.append(f"{path}: 首条记录 schema_version 不正确")
        if first.get("take_timestamp_ms") != 0:
            errors.append(f"{path}: 起始时间不是 0")
        if last.get("take_timestamp_ms") != item.get("timestamp_end_ms"):
            errors.append(f"{path}: 结束时间与 manifest 不一致")
        entries.append(entry)
    partials = sorted(path.name for path in root.glob("*.partial"))
    if partials:
        errors.append(f"存在未封口 partial 文件: {partials}")
    return {
        "schema_version": "match_state_aligned_feature_integrity.v1",
        "status": "passed" if not errors else "failed",
        "verified_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "manifest_schema_version": manifest.get("schema_version"),
        "entry_count": len(manifest.get("entries", [])),
        "record_count": sum(int(item.get("actual_record_count", 0)) for item in entries),
        "entries": entries,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验统一时间基准结构化特征缓存")
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
