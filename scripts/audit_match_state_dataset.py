#!/usr/bin/env python3
"""盘点比赛状态识别数据资产并检查人工时间标注。

该脚本只读访问 CaptureTake/同步录制 manifest、Vidat 标注包和媒体文件，
输出一个可复现的 match_state_dataset_audit.v1 JSON 报告。它不把现有
``rally``/``non_play`` 语义结果变成模型输入，只把人工时间范围登记为粗标签来源。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "match_state_dataset_audit.v1"
VIDEO_SUFFIXES = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".ts"}
EVENT_TYPES = {"rally_start", "rally_end", "non_play_start", "non_play_end"}


def _json_load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _candidate_paths(raw_path: str, media_roots: list[Path]) -> Iterable[Path]:
    source = Path(raw_path).expanduser()
    yield source
    normalized = raw_path.replace("\\", "/")
    marker = "/captures/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        for root in media_roots:
            yield root / "captures" / suffix
    for root in media_roots:
        yield root / source.name


def _resolve_media(raw_path: str | None, media_roots: list[Path]) -> Path | None:
    if not raw_path:
        return None
    seen: set[str] = set()
    for candidate in _candidate_paths(raw_path, media_roots):
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.is_file() and not candidate.name.startswith("._"):
                return candidate.resolve()
        except OSError:
            continue
    return None


def _ffprobe(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate,r_frame_rate,nb_frames:format=duration,size,format_name",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "probe_unavailable", "detail": str(exc)}
    if completed.returncode != 0:
        return {"status": "probe_error", "detail": completed.stderr.strip()[-1000:]}
    payload = _json_load_text(completed.stdout)
    if not payload:
        return {"status": "probe_error", "detail": "ffprobe returned empty JSON"}
    streams = payload.get("streams") or []
    stream = streams[0] if streams and isinstance(streams[0], dict) else {}
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    return {
        "status": "passed",
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "r_frame_rate": stream.get("r_frame_rate"),
        "nb_frames": stream.get("nb_frames"),
        "duration_sec": _finite_number(fmt.get("duration")),
        "container_size": fmt.get("size"),
        "format_name": fmt.get("format_name"),
    }


def _full_decode(path: Path) -> dict[str, Any]:
    """把媒体完整解码到 null，验证容器可读性而不生成新媒体。"""
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "decode_unavailable", "detail": str(exc)}
    if completed.returncode != 0:
        return {"status": "decode_error", "detail": completed.stderr.strip()[-1000:]}
    return {"status": "passed"}


def _json_load_text(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _media_record(
    raw_path: str | None,
    *,
    media_roots: list[Path],
    expected_size: int | None = None,
    expected_duration_sec: float | None = None,
    expected_fps: float | None = None,
    role: str | None = None,
    camera_id: str | None = None,
    probe: bool = True,
    full_decode: bool = False,
    include_hash: bool = False,
) -> dict[str, Any]:
    resolved = _resolve_media(raw_path, media_roots)
    record: dict[str, Any] = {
        "declared_path": raw_path,
        "resolved_path": _relative_or_absolute(resolved) if resolved else None,
        "role": role,
        "camera_id": camera_id,
        "exists": resolved is not None,
        "actual_size": None,
        "expected_size": expected_size,
        "expected_duration_sec": expected_duration_sec,
        "expected_fps": expected_fps,
        "probe": None,
        "decode": None,
        "sha256": None,
    }
    if resolved is None:
        return record
    try:
        record["actual_size"] = resolved.stat().st_size
    except OSError:
        record["exists"] = False
        return record
    if include_hash:
        record["sha256"] = _sha256(resolved)
    if probe:
        record["probe"] = _ffprobe(resolved)
    if full_decode:
        record["decode"] = _full_decode(resolved)
    return record


def _annotation_video(annotation: dict[str, Any]) -> dict[str, Any]:
    outer = annotation.get("annotation")
    if isinstance(outer, dict) and isinstance(outer.get("video"), dict):
        return outer["video"]
    value = annotation.get("video")
    return value if isinstance(value, dict) else {}


def _annotation_actions(annotation: dict[str, Any]) -> list[dict[str, Any]]:
    outer = annotation.get("annotation")
    values = outer.get("actionAnnotationList") if isinstance(outer, dict) else None
    if not isinstance(values, list):
        values = annotation.get("actionAnnotationList")
    return [value for value in values or [] if isinstance(value, dict)]


def _action_event(action: dict[str, Any]) -> dict[str, Any] | None:
    description = action.get("description")
    if not isinstance(description, str) or not description.strip().startswith("{"):
        return None
    try:
        value = json.loads(description)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) and value.get("event_type") in EVENT_TYPES else None


def _infer_time_unit(actions: list[dict[str, Any]], video: dict[str, Any]) -> tuple[str, float | None, str]:
    values = []
    for action in actions:
        if _action_event(action) is None:
            continue
        start = _finite_number(action.get("start"))
        end = _finite_number(action.get("end"))
        if start is not None:
            values.append(start)
        if end is not None:
            values.append(end)
    duration = _finite_number(video.get("duration"))
    frames = _finite_number(video.get("frames"))
    fps = _finite_number(video.get("fps"))
    maximum = max(values) if values else None
    if maximum is None:
        return "unknown", None, "no_timed_boundary_actions"
    if duration is not None and maximum <= duration * 1.05:
        return "seconds", duration, "boundary_values_fit_video_duration"
    if frames is not None and maximum <= frames * 1.05:
        return "frames", duration if duration is not None else (frames / fps if fps else None), "boundary_values_fit_video_frame_count"
    return "ambiguous", duration, "boundary_values_fit_neither_duration_nor_frame_count"


def _annotation_record(path: Path) -> dict[str, Any]:
    annotation = _json_load(path) or {}
    manifest = annotation.get("pickleball_manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    video = _annotation_video(annotation)
    actions = _annotation_actions(annotation)
    unit, duration_sec, unit_reason = _infer_time_unit(actions, video)
    boundaries: list[dict[str, Any]] = []
    event_counts: Counter[str] = Counter()
    invalid_ranges: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        event = _action_event(action)
        if event is None:
            continue
        event_type = str(event["event_type"])
        event_counts[event_type] += 1
        start = _finite_number(action.get("start"))
        end = _finite_number(action.get("end"))
        if start is None or end is None or end <= start:
            invalid_ranges.append({"index": index, "event_type": event_type, "start": start, "end": end, "reason": "invalid_range"})
            continue
        factor = 1000.0 if unit == "seconds" else (1000.0 / _finite_number(video.get("fps")) if unit == "frames" and _finite_number(video.get("fps")) else None)
        if factor is None:
            invalid_ranges.append({"index": index, "event_type": event_type, "start": start, "end": end, "reason": "unknown_time_conversion"})
            continue
        start_ms = start * factor
        end_ms = end * factor
        if duration_sec is not None and end_ms > duration_sec * 1000.0 + 1000.0:
            invalid_ranges.append({"index": index, "event_type": event_type, "start_ms": start_ms, "end_ms": end_ms, "reason": "beyond_video_duration"})
        boundaries.append({"event_type": event_type, "start_ms": round(start_ms, 3), "end_ms": round(end_ms, 3), "source_action_index": index})
    rally_intervals = sorted(
        (item for item in boundaries if item["event_type"] == "rally_start"),
        key=lambda item: (item["start_ms"], item["end_ms"]),
    )
    overlap_count = sum(
        1
        for previous, current in zip(rally_intervals, rally_intervals[1:])
        if current["start_ms"] < previous["end_ms"]
    )
    return {
        "annotation_path": _relative_or_absolute(path),
        "package_id": manifest.get("package_id"),
        "capture_take_id": manifest.get("capture_take_id"),
        "video_fingerprint": manifest.get("video_fingerprint"),
        "video_source": (video.get("src") if isinstance(video, dict) else None),
        "video": {
            "fps": _finite_number(video.get("fps")),
            "frames": _finite_number(video.get("frames")),
            "duration_sec": duration_sec,
            "width": video.get("width"),
            "height": video.get("height"),
        },
        "action_count": len(actions),
        "event_counts": dict(sorted(event_counts.items())),
        "inferred_time_unit": unit,
        "time_unit_reason": unit_reason,
        "boundary_count": len(boundaries),
        "rally_interval_count": len(rally_intervals),
        "rally_overlap_count": overlap_count,
        "closed_boundary_count": len(boundaries),
        "open_boundary_count": len(invalid_ranges),
        "boundaries": boundaries,
        "invalid_ranges": invalid_ranges,
        "status": "usable" if unit in {"seconds", "frames"} and not invalid_ranges else "needs_review",
    }


def _annotation_paths(roots: list[Path]) -> list[Path]:
    paths: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else list(root.rglob("*.json"))
        for path in candidates:
            if path.name.startswith("._") or path.name == "example.json":
                continue
            if path.name == "annotation.json" or path.parent.name == "annotation":
                payload = _json_load(path)
                if payload and ("pickleball_manifest" in payload or "annotation" in payload):
                    paths[str(path.resolve())] = path
    return sorted(paths.values())


def _session_record(
    path: Path,
    media_roots: list[Path],
    *,
    probe: bool,
    full_decode: bool,
    include_hash: bool,
) -> dict[str, Any]:
    session = _json_load(path) or {}
    files: list[dict[str, Any]] = []
    for segment in session.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        for item in segment.get("files") or []:
            if not isinstance(item, dict) or not item.get("file_path"):
                continue
            files.append(
                _media_record(
                    item.get("file_path"),
                    media_roots=media_roots,
                    expected_size=item.get("file_size"),
                    expected_duration_sec=_finite_number(item.get("media_duration_sec")),
                    expected_fps=_finite_number(item.get("effective_fps")),
                    role=item.get("role"),
                    camera_id=item.get("camera_id"),
                    probe=probe,
                    full_decode=full_decode,
                    include_hash=include_hash,
                )
            )
    role_counts = Counter(item.get("role") for item in files if item.get("role"))
    usable_roles = {item.get("role") for item in files if item.get("exists") and (item.get("actual_size") or 0) > 0}
    return {
        "session_path": _relative_or_absolute(path),
        "session_id": session.get("session_id"),
        "capture_take_id": session.get("capture_take_id"),
        "field_session_id": session.get("field_session_id"),
        "status": session.get("status"),
        "capture_mode": "dual" if len(role_counts) >= 2 else "single_or_unknown",
        "camera_slots": session.get("camera_slots") or {},
        "registered_video_ids": session.get("registered_video_ids") or {},
        "duration_sec": _finite_number(session.get("duration_sec")),
        "fps": _finite_number(session.get("fps")),
        "resolution": session.get("resolution"),
        "media_files": files,
        "media_file_count": len(files),
        "usable_roles": sorted(usable_roles),
        "has_usable_dual_pair": {"cam_1", "cam_2"}.issubset(usable_roles),
        "video_availability": session.get("video_availability") or {},
        "storage_root": session.get("storage_root"),
        "output_dir": session.get("output_dir"),
    }


def _issue(code: str, severity: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "context": context}


def build_report(
    *,
    session_roots: list[Path],
    annotation_roots: list[Path],
    media_roots: list[Path],
    date_filter: str | None,
    excluded_session_ids: set[str],
    probe: bool,
    full_decode: bool,
    include_hash: bool,
) -> dict[str, Any]:
    session_paths: list[Path] = []
    for root in session_roots:
        if root.is_file():
            session_paths.append(root)
        elif root.exists():
            session_paths.extend(root.glob("sync_*.json"))
    session_paths = sorted({path.resolve() for path in session_paths if not path.name.startswith("._")})
    if date_filter:
        session_paths = [path for path in session_paths if date_filter.replace("-", "") in path.name]
    sessions = [
        _session_record(path, media_roots, probe=probe, full_decode=full_decode, include_hash=include_hash)
        for path in session_paths
    ]
    for session in sessions:
        session_id = str(session.get("session_id") or "")
        explicitly_excluded = session_id in excluded_session_ids
        session["dataset_included"] = bool(session.get("has_usable_dual_pair")) and not explicitly_excluded
        session["dataset_exclusion_reason"] = "short_test_clip" if explicitly_excluded else (None if session["dataset_included"] else "media_unavailable")

    annotations = [_annotation_record(path) for path in _annotation_paths(annotation_roots)]
    if date_filter:
        session_takes = {item.get("capture_take_id") for item in sessions}
        annotations = [item for item in annotations if item.get("capture_take_id") in session_takes]
    annotations_by_take: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in annotations:
        annotations_by_take[str(item.get("capture_take_id"))].append(item)
    for session in sessions:
        session["annotation_packages"] = annotations_by_take.get(str(session.get("capture_take_id")), [])

    issues: list[dict[str, Any]] = []
    for session in sessions:
        take = session.get("capture_take_id")
        if session.get("dataset_exclusion_reason") == "short_test_clip":
            continue
        if session.get("status") == "completed" and not session.get("has_usable_dual_pair"):
            issues.append(_issue("missing_usable_dual_media", "error", "完成状态的双摄录制没有可用的两个机位媒体", capture_take_id=take))
        if session.get("has_usable_dual_pair") and not session.get("annotation_packages"):
            issues.append(_issue("annotation_missing", "warning", "双摄媒体可用但未发现关联 Vidat 标注包", capture_take_id=take))
        for package in session.get("annotation_packages") or []:
            if package.get("inferred_time_unit") == "ambiguous":
                issues.append(_issue("annotation_time_unit_ambiguous", "error", "标注 start/end 无法可靠判断为秒或帧号", capture_take_id=take, package_id=package.get("package_id"), annotation_path=package.get("annotation_path")))
            if package.get("invalid_ranges"):
                issues.append(_issue("annotation_invalid_ranges", "error", "标注存在非法或超出视频范围的时间段", capture_take_id=take, package_id=package.get("package_id"), invalid_count=len(package["invalid_ranges"])))
            if package.get("rally_overlap_count", 0):
                issues.append(_issue("annotation_rally_overlap", "error", "同一标注包中的 rally 区间发生重叠", capture_take_id=take, package_id=package.get("package_id"), overlap_count=package["rally_overlap_count"]))
            if package.get("inferred_time_unit") == "frames":
                issues.append(_issue("annotation_frame_unit_detected", "warning", "发现旧版 Vidat 标注使用帧号，后续转换必须按 FPS 归一化", capture_take_id=take, package_id=package.get("package_id")))
    for package_id, group in _group_by(annotations, "package_id").items():
        fingerprints = {item.get("video_fingerprint") for item in group if item.get("video_fingerprint")}
        if len(group) > 1 and len(fingerprints) <= 1:
            issues.append(_issue("multiple_annotation_revisions", "info", "同一视频存在多个标注版本，应选择明确 revision 作为训练输入", package_id=package_id, count=len(group)))

    all_files = [file for session in sessions for file in session.get("media_files") or []]
    decode_statuses = Counter(
        str(item["decode"].get("status"))
        for item in all_files
        if isinstance(item.get("decode"), dict)
    )
    probe_statuses = Counter(
        str(item["probe"].get("status"))
        for item in all_files
        if isinstance(item.get("probe"), dict)
    )
    summary = {
        "session_count": len(sessions),
        "completed_session_count": sum(session.get("status") == "completed" for session in sessions),
        "usable_dual_pair_count": sum(bool(session.get("has_usable_dual_pair")) for session in sessions),
        "dataset_included_session_count": sum(bool(session.get("dataset_included")) for session in sessions),
        "dataset_excluded_session_count": sum(not bool(session.get("dataset_included")) for session in sessions),
        "media_file_count": len(all_files),
        "usable_media_file_count": sum(bool(item.get("exists")) and (item.get("actual_size") or 0) > 0 for item in all_files),
        "probe_status_counts": dict(sorted(probe_statuses.items())),
        "decode_status_counts": dict(sorted(decode_statuses.items())),
        "annotation_package_count": len(annotations),
        "annotation_usable_count": sum(item.get("status") == "usable" for item in annotations),
        "annotation_needs_review_count": sum(item.get("status") == "needs_review" for item in annotations),
        "rally_boundary_count": sum(item.get("event_counts", {}).get("rally_start", 0) for item in annotations),
        "issue_count": len(issues),
        "issue_counts_by_severity": dict(Counter(issue["severity"] for issue in issues)),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "date_filter": date_filter,
            "excluded_session_ids": sorted(excluded_session_ids),
            "session_roots": [_relative_or_absolute(path) for path in session_roots],
            "annotation_roots": [_relative_or_absolute(path) for path in annotation_roots],
            "media_roots": [_relative_or_absolute(path) for path in media_roots],
            "ffprobe_enabled": probe,
            "full_decode_enabled": full_decode,
            "sha256_enabled": include_hash,
        },
        "summary": summary,
        "sessions": sessions,
        "annotations": annotations,
        "issues": issues,
    }


def _group_by(values: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for value in values:
        grouped[str(value.get(key))].append(value)
    return grouped


def _default_path(value: str) -> Path:
    return Path(value).expanduser()


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="审计比赛状态识别的视频、双摄关系和人工时间标注")
    parser.add_argument("--session-root", action="append", type=_default_path, default=[project_root / "backend/data/sync-recordings/sessions"], help="同步录制 session JSON 目录，可重复")
    parser.add_argument("--annotation-root", action="append", type=_default_path, default=[project_root / "backend/data/vidat-annotations"], help="Vidat annotation.json/标注包目录，可重复")
    parser.add_argument("--media-root", action="append", type=_default_path, default=[project_root / "backend/data/recordings", Path("/Volumes/Elements/项目/匹克球/视频录制")], help="媒体搜索根目录，可重复")
    parser.add_argument("--date", default=None, help="只审计指定日期，例如 2026-07-20")
    parser.add_argument("--exclude-session-id", action="append", default=[], help="从训练数据范围排除的同步录制 session_id，可重复")
    parser.add_argument("--output", type=_default_path, required=True, help="输出 JSON 报告路径")
    parser.add_argument("--no-probe", action="store_true", help="不调用 ffprobe，适合先做路径/标注盘点")
    parser.add_argument("--full-decode", action="store_true", help="使用 ffmpeg 完整解码媒体到 null，读取大文件会较慢")
    parser.add_argument("--sha256", action="store_true", help="为已找到的媒体计算 SHA-256，读取大文件会较慢")
    args = parser.parse_args(argv)

    report = build_report(
        session_roots=args.session_root,
        annotation_roots=args.annotation_root,
        media_roots=args.media_root,
        date_filter=args.date,
        excluded_session_ids=set(args.exclude_session_id),
        probe=not args.no_probe,
        full_decode=args.full_decode,
        include_hash=args.sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if report["summary"]["issue_counts_by_severity"].get("error", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
