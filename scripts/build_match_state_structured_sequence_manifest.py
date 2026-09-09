#!/usr/bin/env python3
"""为结构化视觉模型生成严格 authoritative-only 的序列窗口清单。

该脚本只读取已经生成的 canonical-sync JSONL，不重新解码视频或运行任何视觉模型。
窗口通过 ``feature_file + record_start_index + record_count`` 引用源记录，避免复制
大体积骨架/球路特征；标签仍由人工复核后的 rally 边界生成。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, deque
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .build_match_state_rgb_clip_manifest import _label_at
except ImportError:  # 允许远程 python scripts/... 直接运行
    from build_match_state_rgb_clip_manifest import _label_at


SCHEMA_VERSION = "match_state_structured_sequence_manifest.v1"
SEQUENCE_SCHEMA_VERSION = "match_state_structured_sequence.v1"
FEATURE_SCHEMA_VERSION = "match_state_canonical_sync_feature.v2"
STRICT_STATUS = "authoritative"
DEFAULT_CONTINUITY_TOLERANCE_MS = 2.0


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


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


def _portable_path(path: Path, dataset_root: Path | None) -> str:
    """返回不绑定本机绝对路径的 source provenance。"""

    if dataset_root is not None:
        try:
            return path.resolve().relative_to(dataset_root.resolve()).as_posix()
        except ValueError:
            pass
    return path.name


def _feature_file_path(feature_root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"canonical feature path 必须是安全相对路径: {relative_path}")
    return feature_root / path


def _iter_jsonl_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON 无法解析: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: 记录必须是对象")
            yield value


def _iter_indexed_records(path: Path) -> Iterable[dict[str, Any]]:
    """以记录序号、物理行号和字节偏移读取 JSONL，便于下游随机读取。"""

    with path.open("rb") as handle:
        record_index = 0
        line_number = 0
        while True:
            byte_offset = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break
            line_number += 1
            if not raw_line.strip():
                continue
            try:
                value = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path}:{line_number}: JSON 无法解析: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: 记录必须是对象")
            yield {
                "record_index": record_index,
                "line_number": line_number,
                "byte_offset": byte_offset,
                "record": value,
            }
            record_index += 1


def _strict_authoritative_record(record: dict[str, Any]) -> bool:
    if record.get("schema_version") != FEATURE_SCHEMA_VERSION:
        return False
    sync = record.get("sync") or {}
    quality = record.get("quality") or {}
    views = record.get("views") or {}
    if sync.get("status") != STRICT_STATUS or quality.get("authoritative_joint_eligible") is not True:
        return False
    if quality.get("dual_view_available") is not True:
        return False
    if set(views) != {"cam_1", "cam_2"}:
        return False
    for role in ("cam_1", "cam_2"):
        view = views.get(role) or {}
        source = view.get("source") or {}
        view_quality = view.get("quality") or {}
        if source.get("sync_status") != STRICT_STATUS:
            return False
        if view_quality.get("view_missing") is True or view_quality.get("structured_available") is not True:
            return False
    return True


def _quality_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    view_summary: dict[str, dict[str, Any]] = {}
    for role in ("cam_1", "cam_2"):
        pose_count = 0
        ball_count = 0
        court_count = 0
        source_errors: list[float] = []
        feature_errors: list[float] = []
        for record in records:
            view = (record.get("views") or {}).get(role) or {}
            quality = view.get("quality") or {}
            if quality.get("pose_usable") is True:
                pose_count += 1
            if quality.get("ball_observed") is True:
                ball_count += 1
            if quality.get("court_line_available") is True:
                court_count += 1
            source = view.get("source") or {}
            if source.get("alignment_error_ms") is not None:
                source_errors.append(abs(float(source["alignment_error_ms"])))
            if source.get("feature_alignment_error_ms") is not None:
                feature_errors.append(abs(float(source["feature_alignment_error_ms"])))
        view_summary[role] = {
            "pose_usable_count": pose_count,
            "ball_observed_count": ball_count,
            "court_line_available_count": court_count,
            "pose_coverage": round(pose_count / max(len(records), 1), 6),
            "ball_observed_coverage": round(ball_count / max(len(records), 1), 6),
            "court_line_coverage": round(court_count / max(len(records), 1), 6),
            "source_alignment_error_ms_max": round(max(source_errors), 3) if source_errors else None,
            "feature_alignment_error_ms_max": round(max(feature_errors), 3) if feature_errors else None,
        }
    return {"frame_count": len(records), "views": view_summary}


def _timeline_labels(
    records: list[dict[str, Any]], rallies: list[dict[str, Any]], uncertain_radius_ms: int
) -> tuple[list[dict[str, Any]], Counter[str]]:
    labels: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for record in records:
        timestamp_ms = float(record["canonical_timestamp_ms"])
        label, quality, rally_id = _label_at(int(round(timestamp_ms)), rallies, uncertain_radius_ms)
        labels.append(
            {
                "canonical_timestamp_ms": round(timestamp_ms, 3),
                "label": label,
                "quality": quality,
                "loss_mask": int(quality == "high_confidence"),
                "rally_segment_id": rally_id,
            }
        )
        counts[label] += 1
    return labels, counts


def _sequence_id(
    *,
    dataset_manifest_id: str,
    feature_manifest_id: str,
    capture_take_id: str,
    record_start_index: int,
    config: dict[str, Any],
) -> str:
    identity = {
        "dataset_manifest_id": dataset_manifest_id,
        "feature_manifest_id": feature_manifest_id,
        "capture_take_id": capture_take_id,
        "record_start_index": record_start_index,
        "config": config,
    }
    return f"mssq_{hashlib.sha256(canonical_bytes(identity)).hexdigest()[:20]}"


def _build_sequence(
    *,
    refs: list[dict[str, Any]],
    feature_entry: dict[str, Any],
    feature_root: Path,
    take: dict[str, Any],
    split: str,
    dataset_manifest_id: str,
    feature_manifest_id: str,
    uncertain_radius_ms: int,
    window_duration_ms: int,
    fps: float,
    frame_count: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    records = [item["record"] for item in refs]
    start_ms = float(records[0]["canonical_timestamp_ms"])
    last_ms = float(records[-1]["canonical_timestamp_ms"])
    center_ms = start_ms + window_duration_ms / 2.0
    rallies = sorted(take.get("labels") or [], key=lambda item: (int(item["start_ms"]), int(item["end_ms"])))
    center_label, center_quality, center_rally_id = _label_at(
        int(round(center_ms)), rallies, uncertain_radius_ms
    )
    timeline_labels, label_counts = _timeline_labels(records, rallies, uncertain_radius_ms)
    source_start = refs[0]
    source_end = refs[-1]
    record_start_index = int(source_start["record_index"])
    identity = {
        "source_session_id": take["source_session_id"],
        "capture_take_id": take["capture_take_id"],
        "feature_file": feature_entry["path"],
        "feature_sha256": feature_entry["sha256"],
        "record_start_index": record_start_index,
        "record_count": frame_count,
        "config": config,
    }
    return {
        "schema_version": SEQUENCE_SCHEMA_VERSION,
        "sequence_id": _sequence_id(
            dataset_manifest_id=dataset_manifest_id,
            feature_manifest_id=feature_manifest_id,
            capture_take_id=str(take["capture_take_id"]),
            record_start_index=record_start_index,
            config=config,
        ),
        "dataset_manifest_id": dataset_manifest_id,
        "canonical_feature_manifest_id": feature_manifest_id,
        "capture_take_id": take["capture_take_id"],
        "source_session_id": take["source_session_id"],
        "split": split,
        "timebase": "reference_camera_source_pts",
        "canonical_start_ms": round(start_ms, 3),
        "canonical_end_ms": round(start_ms + window_duration_ms, 3),
        "last_observed_timestamp_ms": round(last_ms, 3),
        "center_timestamp_ms": round(center_ms, 3),
        "window_duration_ms": window_duration_ms,
        "sampling_fps": fps,
        "record_count": frame_count,
        "source": {
            "feature_file": str(feature_entry["path"]),
            "feature_sha256": feature_entry["sha256"],
            "feature_size_bytes": int(feature_entry["size_bytes"]),
            "record_start_index": record_start_index,
            "record_end_index": int(source_end["record_index"]),
            "line_start": int(source_start["line_number"]),
            "line_end": int(source_end["line_number"]),
            "byte_offset_start": int(source_start["byte_offset"]),
            "byte_offset_end": int(source_end["byte_offset"]),
            "sync_revision": feature_entry["sync_revision"],
        },
        "strict_gate": {
            "authoritative_joint_eligible": True,
            "authoritative_record_count": frame_count,
            "sync_status_counts": {STRICT_STATUS: frame_count},
        },
        "label": {
            "center_label": center_label,
            "center_quality": center_quality,
            "center_loss_mask": int(center_quality == "high_confidence"),
            "center_rally_segment_id": center_rally_id,
            "timeline_labels": timeline_labels,
            "timeline_label_counts": dict(label_counts),
            "uncertain_radius_ms": uncertain_radius_ms,
        },
        "quality_summary": _quality_summary(records),
        "identity": identity,
    }


def _iter_windows(
    path: Path,
    *,
    frame_count: int,
    stride_frames: int,
    fps: float,
    continuity_tolerance_ms: float,
) -> Iterable[list[dict[str, Any]]]:
    expected_step_ms = 1000.0 / fps
    buffer: deque[dict[str, Any]] = deque()
    previous_timestamp_ms: float | None = None
    for ref in _iter_indexed_records(path):
        record = ref["record"]
        timestamp = record.get("canonical_timestamp_ms")
        if not isinstance(timestamp, (int, float)):
            raise ValueError(f"{path}:{ref['line_number']}: 缺少 canonical_timestamp_ms")
        timestamp_ms = float(timestamp)
        if (
            previous_timestamp_ms is not None
            and abs(timestamp_ms - previous_timestamp_ms - expected_step_ms) > continuity_tolerance_ms
        ):
            buffer.clear()
        previous_timestamp_ms = timestamp_ms
        buffer.append(ref)
        if len(buffer) < frame_count:
            continue
        yield list(buffer)
        for _ in range(min(stride_frames, len(buffer))):
            buffer.popleft()


def _source_feature_file_sha256(feature_path: Path, feature_entry: dict[str, Any]) -> None:
    expected = str(feature_entry.get("sha256", ""))
    if not feature_path.is_file():
        raise ValueError(f"canonical feature 文件不存在: {feature_path}")
    actual = sha256_file(feature_path)
    if expected and actual != expected:
        raise ValueError(f"canonical feature SHA-256 不匹配: {feature_path}")
    expected_size = int(feature_entry.get("size_bytes", -1))
    if expected_size >= 0 and feature_path.stat().st_size != expected_size:
        raise ValueError(f"canonical feature 文件大小不匹配: {feature_path}")


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_json(args.dataset_manifest)
    label_profile = load_json(args.label_profile)
    split_manifest = load_json(args.group_split)
    feature_manifest = load_json(args.canonical_manifest)
    if dataset.get("schema_version") != "match_state_dataset_manifest.v1":
        raise ValueError("dataset manifest schema 不匹配")
    if split_manifest.get("schema_version") != "match_state_group_split.v1":
        raise ValueError("group split schema 不匹配")
    if feature_manifest.get("schema_version") != "match_state_canonical_sync_manifest.v2":
        raise ValueError("canonical feature manifest schema 不匹配")
    if args.frame_count <= 0 or args.stride_frames <= 0 or args.fps <= 0:
        raise ValueError("frame_count、stride_frames、fps 必须为正数")
    if args.window_duration_ms <= 0:
        raise ValueError("window_duration_ms 必须为正数")
    expected_duration = args.frame_count * 1000.0 / args.fps
    if abs(expected_duration - args.window_duration_ms) > 0.01:
        raise ValueError(
            "window_duration_ms 必须等于 frame_count/fps；当前配置会导致序列时长契约不一致"
        )

    uncertain_radius_ms = int(label_profile["reviewed_boundary_policy"]["uncertain_radius_ms"])
    assignment = split_manifest.get("assignment") or {}
    takes_by_id = {str(item["capture_take_id"]): item for item in dataset.get("takes", [])}
    feature_entries = {str(item["capture_take_id"]): item for item in feature_manifest.get("entries", [])}
    if set(takes_by_id) != set(feature_entries):
        raise ValueError(
            f"dataset 与 canonical feature 覆盖不一致: missing={sorted(set(takes_by_id)-set(feature_entries))}, "
            f"extra={sorted(set(feature_entries)-set(takes_by_id))}"
        )
    if set(assignment) != set(takes_by_id):
        raise ValueError("group split 没有覆盖每个 CaptureTake 恰好一次")

    config = {
        "window_duration_ms": args.window_duration_ms,
        "sampling_fps": args.fps,
        "frame_count": args.frame_count,
        "stride_frames": args.stride_frames,
        "stride_ms": round(args.stride_frames * 1000.0 / args.fps, 6),
        "continuity_tolerance_ms": args.continuity_tolerance_ms,
        "strict_authoritative_only": True,
        "include_uncertain_windows": True,
        "padding_policy": "exclude_from_strict_sequence_manifest",
        "label_step_ms": round(1000.0 / args.fps, 6),
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    sequences_path = args.output_root / "sequences.jsonl"
    sequence_count = 0
    center_label_counts: Counter[str] = Counter()
    center_quality_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    timeline_label_counts: Counter[str] = Counter()
    take_counts: Counter[str] = Counter()
    source_authoritative_records = 0
    temp_path = args.output_root / ".sequences.jsonl.partial"
    try:
        with temp_path.open("w", encoding="utf-8") as output:
            for take_id in sorted(takes_by_id):
                feature_entry = feature_entries[take_id]
                feature_path = _feature_file_path(args.canonical_feature_root, str(feature_entry["path"]))
                if feature_entry.get("status") != "complete":
                    raise ValueError(f"canonical feature entry 未 complete: {take_id}")
                if args.verify_source_hashes:
                    _source_feature_file_sha256(feature_path, feature_entry)
                source_authoritative_records += int(feature_entry.get("authoritative_joint_record_count", 0))
                take = takes_by_id[take_id]
                split = str(assignment[take_id])
                for refs in _iter_windows(
                    feature_path,
                    frame_count=args.frame_count,
                    stride_frames=args.stride_frames,
                    fps=args.fps,
                    continuity_tolerance_ms=args.continuity_tolerance_ms,
                ):
                    if not all(_strict_authoritative_record(item["record"]) for item in refs):
                        continue
                    sequence = _build_sequence(
                        refs=refs,
                        feature_entry=feature_entry,
                        feature_root=args.canonical_feature_root,
                        take=take,
                        split=split,
                        dataset_manifest_id=str(dataset["manifest_id"]),
                        feature_manifest_id=str(feature_manifest["manifest_id"]),
                        uncertain_radius_ms=uncertain_radius_ms,
                        window_duration_ms=args.window_duration_ms,
                        fps=args.fps,
                        frame_count=args.frame_count,
                        config=config,
                    )
                    output.write(json.dumps(sequence, ensure_ascii=False, separators=(",", ":")) + "\n")
                    sequence_count += 1
                    center_label_counts[sequence["label"]["center_label"]] += 1
                    center_quality_counts[sequence["label"]["center_quality"]] += 1
                    split_counts[split] += 1
                    timeline_label_counts.update(sequence["label"]["timeline_label_counts"])
                    take_counts[take_id] += 1
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, sequences_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    identity = {
        "dataset_manifest_id": dataset["manifest_id"],
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "label_profile_sha256": sha256_file(args.label_profile),
        "group_split_id": split_manifest["split_id"],
        "group_split_sha256": sha256_file(args.group_split),
        "canonical_feature_manifest_id": feature_manifest["manifest_id"],
        "canonical_feature_manifest_sha256": sha256_file(args.canonical_manifest),
        "builder_sha256": sha256_file(Path(__file__).resolve()),
        "config": config,
        "strict_authoritative_only": True,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": f"mssm_{hashlib.sha256(canonical_bytes(identity)).hexdigest()[:20]}",
        "generated_at": datetime.now(UTC).isoformat(),
        "sequence_file": sequences_path.name,
        "sequence_count": sequence_count,
        "center_label_counts": dict(center_label_counts),
        "center_quality_counts": dict(center_quality_counts),
        "split_counts": dict(split_counts),
        "timeline_label_counts": dict(timeline_label_counts),
        "take_counts": dict(take_counts),
        "source_authoritative_record_count": source_authoritative_records,
        "config": config,
        "input_contract": {
            "modalities": ["pose", "ball", "court_line", "quality"],
            "views": ["cam_1", "cam_2"],
            "source_record_schema": FEATURE_SCHEMA_VERSION,
            "reference": "sequence rows point to canonical feature JSONL by record index; no feature duplication",
            "pose": {"player_slots": 4, "keypoints": 26, "coordinates": "normalized_image"},
            "ball": {"candidate_tracking": True, "missing_semantics": "unknown_not_no_ball"},
            "court_line": {"projection_available": False, "use_as_quality_and_geometry": True},
            "quality": {"retain_confidence_visibility_missing_mask": True},
        },
        "source": {
            "dataset_manifest": _portable_path(args.dataset_manifest, args.dataset_root),
            "label_profile": _portable_path(args.label_profile, args.dataset_root),
            "group_split": _portable_path(args.group_split, args.dataset_root),
            "canonical_feature_manifest": _portable_path(args.canonical_manifest, args.dataset_root),
            "canonical_feature_root": _portable_path(args.canonical_feature_root, args.dataset_root),
        },
        "identity": identity,
        "sequence_file_sha256": sha256_file(sequences_path),
        "integrity": {
            "status": "passed",
            "source_hashes_verified": bool(args.verify_source_hashes),
            "strict_gate": "all 48 records and both views authoritative",
        },
    }
    manifest_path = args.output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="生成严格 authoritative-only 结构化序列窗口 manifest")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--label-profile", type=Path, required=True)
    parser.add_argument("--group-split", type=Path, required=True)
    parser.add_argument("--canonical-manifest", type=Path, required=True)
    parser.add_argument("--canonical-feature-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--window-duration-ms", type=int, default=4000)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--frame-count", type=int, default=48)
    parser.add_argument("--stride-frames", type=int, default=6)
    parser.add_argument("--continuity-tolerance-ms", type=float, default=DEFAULT_CONTINUITY_TOLERANCE_MS)
    parser.add_argument(
        "--no-verify-source-hashes",
        dest="verify_source_hashes",
        action="store_false",
        help="仅在已完成独立完整性校验时跳过源 JSONL hash 重读",
    )
    parser.set_defaults(verify_source_hashes=True)
    args = parser.parse_args()
    manifest = build_manifest(args)
    print(
        json.dumps(
            {
                "schema_version": manifest["schema_version"],
                "manifest_id": manifest["manifest_id"],
                "sequence_count": manifest["sequence_count"],
                "center_label_counts": manifest["center_label_counts"],
                "center_quality_counts": manifest["center_quality_counts"],
                "split_counts": manifest["split_counts"],
                "sequence_file": str(args.output_root / manifest["sequence_file"]),
                "source_hashes_verified": manifest["integrity"]["source_hashes_verified"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
