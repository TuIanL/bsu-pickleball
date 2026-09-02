#!/usr/bin/env python3
"""构建 RGB/骨架/球候选/场地线的统一 take-time 特征缓存。

该脚本可在远程 CPU 节点运行，不解码视频。它读取已完成的 RGB frame index
和结构化 JSONL，按固定时间网格做最近邻对齐，再写出带质量 mask 的双摄
联合记录。RGB 路径只作为远程可解析的引用保留。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .match_state_temporal_features import (
        DEFAULT_MAX_ALIGNMENT_GAP_MS,
        FEATURE_SCHEMA_VERSION,
        BallFeatureState,
        PlayerFeatureState,
        TimestampIndex,
        build_aligned_view,
        canonical_grid,
    )
except ImportError:  # 允许 python scripts/build_match_state_aligned_features.py 直接运行
    from match_state_temporal_features import (
        DEFAULT_MAX_ALIGNMENT_GAP_MS,
        FEATURE_SCHEMA_VERSION,
        BallFeatureState,
        PlayerFeatureState,
        TimestampIndex,
        build_aligned_view,
        canonical_grid,
    )

MANIFEST_SCHEMA_VERSION = "match_state_aligned_feature_manifest.v1"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL 记录必须是对象")
            records.append(value)
    return records


def index_structured_cache(structured_root: Path) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for summary_path in sorted(structured_root.glob("*/summary.json")):
        summary = load_json(summary_path)
        if summary.get("status") != "complete":
            continue
        identity = summary.get("cache_identity", {})
        uri = str(identity.get("logical_media_uri", ""))
        if not uri:
            raise ValueError(f"结构化 summary 缺少 logical_media_uri: {summary_path}")
        frames_name = str(summary.get("artifacts", {}).get("frames", "frames.jsonl"))
        court_name = str(summary.get("artifacts", {}).get("court_line", "court-line.jsonl"))
        frames_path = summary_path.parent / frames_name
        court_path = summary_path.parent / court_name
        if not frames_path.is_file() or not court_path.is_file():
            raise ValueError(f"结构化缓存 artifact 缺失: {summary_path.parent}")
        indexed[uri] = {
            "summary": summary,
            "frames_path": frames_path,
            "court_path": court_path,
        }
    return indexed


def _missing_view() -> dict[str, Any]:
    return {
        "rgb": None,
        "structured": {"available": False, "timestamp_ms": None, "alignment_delta_ms": None, "schema_version": None},
        "court_line": {
            "available": False,
            "timestamp_ms": None,
            "alignment_delta_ms": None,
            "geometry": None,
            "projection_available": False,
        },
        "features": {
            "pose": {"players": [], "formation": {"player_count": 0}, "pose_usable": False},
            "ball": {"observed": False, "missing_semantics": "unknown_not_no_ball"},
        },
        "quality": {
            "rgb_available": False,
            "structured_available": False,
            "court_line_available": False,
            "pose_usable": False,
            "ball_observed": False,
            "ball_missing_semantics": "unknown_not_no_ball",
            "view_missing": True,
        },
    }


def iter_take_records(
    *,
    take_id: str,
    source_session_id: str,
    views: dict[str, dict[str, Any]],
    rgb_entries: dict[str, dict[str, Any]],
    fps: float,
    max_alignment_gap_ms: float,
) -> Iterator[dict[str, Any]]:
    max_timestamp = max(float(view["structured"]["summary"].get("last_timestamp_ms", 0.0)) for view in views.values())
    states = {camera: (PlayerFeatureState(), BallFeatureState()) for camera in views}
    indexes = {
        camera: (
            TimestampIndex(view["structured"]["frames"]),
            TimestampIndex(view["structured"]["court"], timestamp_key="timestamp_ms"),
        )
        for camera, view in views.items()
    }
    for timestamp_ms in canonical_grid(max_timestamp, fps):
        output_views: dict[str, Any] = {}
        for camera in ("cam_1", "cam_2"):
            view = views.get(camera)
            if view is None:
                output_views[camera] = _missing_view()
                continue
            player_state, ball_state = states[camera]
            structured_index, court_index = indexes[camera]
            rgb_entry = rgb_entries.get(view["uri"])
            output_views[camera] = build_aligned_view(
                timestamp_ms=float(timestamp_ms),
                rgb_entry=rgb_entry,
                structured_records=view["structured"]["frames"],
                court_records=view["structured"]["court"],
                player_state=player_state,
                ball_state=ball_state,
                rgb_fps=float((rgb_entry or {}).get("identity", {}).get("fps", fps)),
                max_alignment_gap_ms=max_alignment_gap_ms,
                structured_index=structured_index,
                court_index=court_index,
            )
        available_views = [item for item in output_views.values() if item["quality"]["structured_available"]]
        yield {
            "schema_version": FEATURE_SCHEMA_VERSION,
            "capture_take_id": take_id,
            "source_session_id": source_session_id,
            "timebase": "capture_take_relative_ms",
            "take_timestamp_ms": timestamp_ms,
            "views": output_views,
            "quality": {
                "view_count": len(available_views),
                "dual_view_available": len(available_views) == 2,
                "pose_view_count": sum(item["quality"]["pose_usable"] for item in output_views.values()),
                "ball_view_count": sum(item["quality"]["ball_observed"] for item in output_views.values()),
                "insufficient_evidence": not any(
                    item["quality"]["rgb_available"] and item["quality"]["structured_available"]
                    for item in output_views.values()
                ),
            },
        }


def build_take_records(
    *,
    take_id: str,
    source_session_id: str,
    views: dict[str, dict[str, Any]],
    rgb_entries: dict[str, dict[str, Any]],
    fps: float,
    max_alignment_gap_ms: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = list(
        iter_take_records(
            take_id=take_id,
            source_session_id=source_session_id,
            views=views,
            rgb_entries=rgb_entries,
            fps=fps,
            max_alignment_gap_ms=max_alignment_gap_ms,
        )
    )
    summary = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "complete",
        "capture_take_id": take_id,
        "source_session_id": source_session_id,
        "record_count": len(records),
        "timestamp_start_ms": records[0]["take_timestamp_ms"] if records else None,
        "timestamp_end_ms": records[-1]["take_timestamp_ms"] if records else None,
        "dual_view_record_count": sum(item["quality"]["dual_view_available"] for item in records),
        "alignment_gap_limit_ms": max_alignment_gap_ms,
    }
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="生成比赛状态统一时间基准结构化特征缓存")
    parser.add_argument("--rgb-cache-manifest", type=Path, required=True)
    parser.add_argument("--structured-cache-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--max-alignment-gap-ms", type=float, default=DEFAULT_MAX_ALIGNMENT_GAP_MS)
    parser.add_argument("--only-session")
    parser.add_argument("--max-takes", type=int)
    args = parser.parse_args()
    if args.fps <= 0 or args.max_alignment_gap_ms <= 0:
        raise SystemExit("fps 和 max-alignment-gap-ms 必须为正数")
    rgb_manifest = load_json(args.rgb_cache_manifest)
    rgb_entries = rgb_manifest.get("entries", {})
    if not isinstance(rgb_entries, dict):
        raise SystemExit("RGB cache manifest 的 entries 必须是对象")
    structured = index_structured_cache(args.structured_cache_root)
    by_take: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for uri, item in structured.items():
        summary = item["summary"]
        by_take[(str(summary["capture_take_id"]), str(summary["source_session_id"]))][str(summary["camera_role"])] = {
            "uri": uri,
            "structured": item,
        }
    selected = sorted(by_take.items())
    if args.only_session:
        selected = [item for item in selected if item[0][1] == args.only_session]
    if args.max_takes is not None:
        selected = selected[: args.max_takes]
    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest_identity = {
        "feature_schema": FEATURE_SCHEMA_VERSION,
        "rgb_cache_manifest_sha256": sha256_file(args.rgb_cache_manifest),
        "structured_cache_keys": sorted(item["summary"]["cache_key"] for item in structured.values()),
        "fps": args.fps,
        "max_alignment_gap_ms": args.max_alignment_gap_ms,
    }
    cache_id = hashlib.sha256(json.dumps(manifest_identity, sort_keys=True).encode()).hexdigest()[:24]
    output_entries: list[dict[str, Any]] = []
    for (take_id, session_id), views in selected:
        loaded_views: dict[str, dict[str, Any]] = {}
        for camera, view in views.items():
            cache = view["structured"]
            loaded_views[camera] = {
                **view,
                "structured": {
                    **cache,
                    "frames": load_jsonl(cache["frames_path"]),
                    "court": load_jsonl(cache["court_path"]),
                },
            }
        records_iter = iter_take_records(
            take_id=take_id,
            source_session_id=session_id,
            views=loaded_views,
            rgb_entries=rgb_entries,
            fps=args.fps,
            max_alignment_gap_ms=args.max_alignment_gap_ms,
        )
        output_path = args.output_root / f"{session_id}.aligned.jsonl"
        fd, temp_name = tempfile.mkstemp(prefix=f".{session_id}.", suffix=".partial", dir=args.output_root)
        try:
            record_count = 0
            dual_view_count = 0
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                for record in records_iter:
                    output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                    record_count += 1
                    dual_view_count += int(record["quality"]["dual_view_available"])
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_name, output_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        output_entries.append(
            {
                "capture_take_id": take_id,
                "source_session_id": session_id,
                "path": output_path.name,
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "status": "complete",
                "record_count": record_count,
                "timestamp_start_ms": 0 if record_count else None,
                "timestamp_end_ms": int(round((record_count - 1) * 1000.0 / args.fps)) if record_count else None,
                "dual_view_record_count": dual_view_count,
                "alignment_gap_limit_ms": args.max_alignment_gap_ms,
            }
        )
        print(
            json.dumps(
                {"capture_take_id": take_id, "record_count": record_count, "status": "complete"}, ensure_ascii=False
            )
        )
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_id": f"afm_{cache_id}",
        "generated_at": datetime.now(UTC).isoformat(),
        "identity": manifest_identity,
        "entries": output_entries,
    }
    (args.output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "status": "complete",
                "take_count": len(output_entries),
                "output_root": str(args.output_root),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
