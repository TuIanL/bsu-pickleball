#!/usr/bin/env python3
"""校验结构化视觉序列 manifest 的封口、窗口契约和严格同步门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "match_state_structured_sequence_manifest.v1"
SEQUENCE_SCHEMA_VERSION = "match_state_structured_sequence.v1"


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


def _source_feature_path(feature_root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"source feature path 不是安全相对路径: {relative_path}")
    return feature_root / path


def _validate_source_ranges(
    *,
    feature_root: Path,
    sequences_by_file: dict[str, list[tuple[int, dict[str, Any]]]],
    errors: list[str],
) -> None:
    """每个 feature JSONL 只读取一遍，同时验证所有重叠窗口。"""

    for feature_file, sequence_items in sequences_by_file.items():
        try:
            path = _source_feature_path(feature_root, feature_file)
        except ValueError as exc:
            errors.append(f"source feature path 非法: {exc}")
            continue
        if not path.is_file():
            errors.append(f"source feature 文件不存在: {path}")
            continue
        expected_hashes = {str(sequence.get("source", {}).get("feature_sha256", "")) for _, sequence in sequence_items}
        if len(expected_hashes) != 1:
            errors.append(f"{path}: 同一 source feature 被声明了多个 SHA-256")
        expected_hash = next(iter(expected_hashes), "")
        expected_sizes = {
            int(sequence.get("source", {}).get("feature_size_bytes", -1))
            for _, sequence in sequence_items
        }
        if len(expected_sizes) != 1:
            errors.append(f"{path}: 同一 source feature 被声明了多个文件大小")
        expected_size = next(iter(expected_sizes), -1)
        if expected_size >= 0 and path.stat().st_size != expected_size:
            errors.append(f"{path}: source feature 文件大小不匹配")

        starts: dict[int, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        for sequence_line, sequence in sequence_items:
            source = sequence.get("source") or {}
            start = int(source.get("record_start_index", -1))
            end = int(source.get("record_end_index", -1))
            count = int(sequence.get("record_count", -1))
            if start < 0 or end - start + 1 != count:
                errors.append(f"sequence:{sequence_line}: source record range 与 record_count 不一致")
                continue
            starts[start].append((sequence_line, sequence))

        active: list[tuple[int, dict[str, Any], int]] = []
        record_index = 0
        line_number = 0
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                byte_offset = handle.tell()
                raw_line = handle.readline()
                if not raw_line:
                    break
                line_number += 1
                digest.update(raw_line)
                if not raw_line.strip():
                    continue
                for sequence_line, sequence in starts.get(record_index, []):
                    end = int(sequence["source"]["record_end_index"])
                    active.append((sequence_line, sequence, end))
                    source = sequence["source"]
                    if int(source["line_start"]) != line_number or int(source["byte_offset_start"]) != byte_offset:
                        errors.append(f"sequence:{sequence_line}: source 起点行号或 byte offset 不一致")
                if active:
                    try:
                        record = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        errors.append(f"{path}:{line_number}: source JSON 无法解析: {exc}")
                        record_index += 1
                        continue
                    next_active: list[tuple[int, dict[str, Any], int]] = []
                    for sequence_line, sequence, end in active:
                        if record.get("schema_version") != "match_state_canonical_sync_feature.v2":
                            errors.append(f"sequence:{sequence_line}: source record schema 不正确")
                        if (record.get("sync") or {}).get("status") != "authoritative":
                            errors.append(f"sequence:{sequence_line}: strict sequence 引用了非 authoritative record")
                        if (record.get("quality") or {}).get("authoritative_joint_eligible") is not True:
                            errors.append(f"sequence:{sequence_line}: strict sequence record gate 不成立")
                        source = sequence["source"]
                        if record_index == int(source["record_start_index"]):
                            if float(record.get("canonical_timestamp_ms", -1)) != float(sequence["canonical_start_ms"]):
                                errors.append(f"sequence:{sequence_line}: sequence 起点与 source record 不一致")
                        if record_index == end:
                            if int(source["line_end"]) != line_number or int(source["byte_offset_end"]) != byte_offset:
                                errors.append(f"sequence:{sequence_line}: source 终点行号或 byte offset 不一致")
                            if float(record.get("canonical_timestamp_ms", -1)) != float(
                                sequence["last_observed_timestamp_ms"]
                            ):
                                errors.append(f"sequence:{sequence_line}: sequence 末帧与 source record 不一致")
                        else:
                            next_active.append((sequence_line, sequence, end))
                    active = next_active
                record_index += 1
        actual_hash = digest.hexdigest()
        if expected_hash and actual_hash != expected_hash:
            errors.append(f"{path}: source feature SHA-256 不匹配")
        if active:
            errors.extend(
                f"sequence:{sequence_line}: source record range 超出文件范围"
                for sequence_line, _, _ in active
            )


def verify(manifest_path: Path, feature_root: Path | None = None, verify_source: bool = False) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    root = manifest_path.parent
    errors: list[str] = []
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"manifest schema 不正确: {manifest.get('schema_version')}")
    sequence_path = root / str(manifest.get("sequence_file", ""))
    if not sequence_path.is_file():
        errors.append(f"sequence 文件不存在: {sequence_path}")
        return {
            "schema_version": "match_state_structured_sequence_integrity.v1",
            "status": "failed",
            "verified_at": datetime.now(UTC).isoformat(),
            "manifest": str(manifest_path),
            "sequence_count": 0,
            "errors": errors,
        }
    expected_hash = str(manifest.get("sequence_file_sha256", ""))
    actual_hash = sha256_file(sequence_path)
    if expected_hash != actual_hash:
        errors.append("sequence_file_sha256 与实际文件不一致")

    sequence_count = 0
    unique_ids: set[str] = set()
    split_counts: Counter[str] = Counter()
    center_labels: Counter[str] = Counter()
    center_qualities: Counter[str] = Counter()
    take_counts: Counter[str] = Counter()
    source_sequences: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    last_start_by_feature_file: dict[str, int] = {}
    with sequence_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                sequence = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{sequence_path}:{line_number}: JSON 无法解析: {exc}")
                continue
            sequence_count += 1
            if sequence.get("schema_version") != SEQUENCE_SCHEMA_VERSION:
                errors.append(f"{sequence_path}:{line_number}: sequence schema 不正确")
            sequence_id = str(sequence.get("sequence_id", ""))
            if not sequence_id or sequence_id in unique_ids:
                errors.append(f"{sequence_path}:{line_number}: sequence_id 缺失或重复")
            unique_ids.add(sequence_id)
            if sequence.get("split") not in {"train", "validation", "test"}:
                errors.append(f"{sequence_path}:{line_number}: split 非法")
            for key, expected in (("record_count", 48), ("sampling_fps", 12), ("window_duration_ms", 4000)):
                if sequence.get(key) != expected:
                    errors.append(f"{sequence_path}:{line_number}: {key} 不符合固定训练契约")
            if sequence.get("timebase") != "reference_camera_source_pts":
                errors.append(f"{sequence_path}:{line_number}: timebase 不正确")
            if sequence.get("dataset_manifest_id") != manifest.get("identity", {}).get("dataset_manifest_id"):
                errors.append(f"{sequence_path}:{line_number}: dataset manifest provenance 不一致")
            if sequence.get("canonical_feature_manifest_id") != manifest.get("identity", {}).get(
                "canonical_feature_manifest_id"
            ):
                errors.append(f"{sequence_path}:{line_number}: canonical feature provenance 不一致")
            gate = sequence.get("strict_gate") or {}
            if gate.get("authoritative_joint_eligible") is not True or gate.get("authoritative_record_count") != 48:
                errors.append(f"{sequence_path}:{line_number}: strict authoritative gate 不成立")
            if gate.get("sync_status_counts") != {"authoritative": 48}:
                errors.append(f"{sequence_path}:{line_number}: sync status counts 不正确")
            label = sequence.get("label") or {}
            timeline = label.get("timeline_labels") or []
            if len(timeline) != 48:
                errors.append(f"{sequence_path}:{line_number}: timeline_labels 必须为 48 个")
            if label.get("center_quality") == "high_confidence" and label.get("center_loss_mask") != 1:
                errors.append(f"{sequence_path}:{line_number}: high_confidence center 必须参与 loss")
            if label.get("center_quality" ) != "high_confidence" and label.get("center_loss_mask") != 0:
                errors.append(f"{sequence_path}:{line_number}: uncertain/excluded center 不得参与 loss")
            source = sequence.get("source") or {}
            feature_file = str(source.get("feature_file", ""))
            start = int(source.get("record_start_index", -1))
            end = int(source.get("record_end_index", -1))
            if start < 0 or end - start + 1 != 48:
                errors.append(f"{sequence_path}:{line_number}: source record range 不是连续 48 帧")
            previous_start = last_start_by_feature_file.get(feature_file)
            if previous_start is not None and start < previous_start:
                errors.append(f"{sequence_path}:{line_number}: 同一 source feature 内 sequence 未按起点排序")
            last_start_by_feature_file[feature_file] = start
            source_sequences[feature_file].append((line_number, sequence))
            split_counts[str(sequence.get("split"))] += 1
            center_labels[str(label.get("center_label"))] += 1
            center_qualities[str(label.get("center_quality"))] += 1
            take_counts[str(sequence.get("capture_take_id"))] += 1

    if verify_source:
        if feature_root is None:
            errors.append("verify_source=true 但未提供 feature_root")
        else:
            try:
                _validate_source_ranges(
                    feature_root=feature_root,
                    sequences_by_file=dict(source_sequences),
                    errors=errors,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"source feature 校验失败: {exc}")

    if sequence_count != int(manifest.get("sequence_count", -1)):
        errors.append("sequence_count 与实际行数不一致")
    if dict(split_counts) != manifest.get("split_counts", {}):
        errors.append("split_counts 与实际行数不一致")
    if dict(center_labels) != manifest.get("center_label_counts", {}):
        errors.append("center_label_counts 与实际行数不一致")
    if dict(center_qualities) != manifest.get("center_quality_counts", {}):
        errors.append("center_quality_counts 与实际行数不一致")
    partials = sorted(path.name for path in root.iterdir() if path.is_file() and path.name.endswith(".partial"))
    if partials:
        errors.append(f"存在未封口 partial 文件: {partials}")
    return {
        "schema_version": "match_state_structured_sequence_integrity.v1",
        "status": "passed" if not errors else "failed",
        "verified_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "sequence_count": sequence_count,
        "split_counts": dict(split_counts),
        "center_label_counts": dict(center_labels),
        "center_quality_counts": dict(center_qualities),
        "take_count": len(take_counts),
        "source_file_count": len(source_sequences),
        "source_verified": verify_source,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验结构化视觉序列 manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--canonical-feature-root", type=Path)
    parser.add_argument("--verify-source", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.manifest, args.canonical_feature_root, args.verify_source)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
