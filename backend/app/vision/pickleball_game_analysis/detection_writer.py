"""JSON writers for ball trajectory and bounce artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.vision.pickleball_game_analysis.bounce_detector import BounceDetectorConfig
from app.vision.pickleball_game_analysis.schemas import (
    BallFrameSample,
    BounceEvent,
    TrajectoryPoint,
    coordinate_system_metadata,
    event_to_payload,
    sample_to_payload,
    to_jsonable,
)
from app.vision.pickleball_game_analysis.trajectory_cleaner import TrajectoryCleanerConfig


def build_raw_trajectory_payload(
    *,
    job_id: str,
    samples: list[BallFrameSample],
    status: str = "available",
    detail: str = "ball trajectory generated",
    court_width: float = 20.0,
    court_length: float = 44.0,
) -> dict[str, Any]:
    """
    构造"原始球轨迹"产物的 payload（字典）。

    原始轨迹 = BallTracker 逐帧输出、未经清洗。字段含 schema 版本、作业 ID、
    状态、坐标系统说明，以及每个采样点。
    """
    return {
        "schema_version": "ball_trajectory.v1",
        "job_id": job_id,
        "status": status,
        "detail": detail,
        "coordinate_system": coordinate_system_metadata(court_width, court_length),
        "samples": [sample_to_payload(sample) for sample in samples],
    }


def build_cleaned_trajectory_payload(
    *,
    job_id: str,
    samples: list[TrajectoryPoint],
    config: TrajectoryCleanerConfig | None = None,
    status: str = "available",
    detail: str = "cleaned ball trajectory generated",
    court_width: float = 20.0,
    court_length: float = 44.0,
) -> dict[str, Any]:
    """
    构造"清洗后球轨迹"产物的 payload。

    与原始轨迹相比，多了 filtering 字段，记录清洗参数（去异常、插值、缺口上限等）。
    """
    config = config or TrajectoryCleanerConfig()
    return {
        "schema_version": "cleaned_ball_trajectory.v1",
        "job_id": job_id,
        "status": status,
        "detail": detail,
        "coordinate_system": coordinate_system_metadata(court_width, court_length),
        "filtering": {
            "outlier_removal": True,
            "interpolation": True,
            "max_interpolation_gap": config.max_interpolation_gap,
            "outlier_step_floor_px": config.outlier_step_floor_px,
        },
        "samples": [sample_to_payload(sample) for sample in samples],
    }


def build_bounce_events_payload(
    *,
    job_id: str,
    events: list[BounceEvent],
    config: BounceDetectorConfig | None = None,
    status: str | None = None,
    detail: str | None = None,
    court_width: float = 20.0,
    court_length: float = 44.0,
) -> dict[str, Any]:
    """
    构造"弹跳事件"产物的 payload。

    status / detail 若未传则自动推断：有事件→available，无事件→no_candidates。
    config 段会记录弹跳检测的关键参数，便于复现/调试。
    """
    config = config or BounceDetectorConfig()
    resolved_status = status or ("available" if events else "no_candidates")
    resolved_detail = detail or (
        f"detected {len(events)} bounce event candidates" if events else "bounce detector ran with no candidates"
    )
    return {
        "schema_version": "bounce_events.v1",
        "job_id": job_id,
        "status": resolved_status,
        "detail": resolved_detail,
        "coordinate_system": coordinate_system_metadata(court_width, court_length),
        "detection_method": "trajectory_lag20",
        "config": {
            "fps": config.fps,
            "window_size": config.window_size,
            "center_offset": config.center_offset,
            "min_event_gap_sec": config.min_event_gap_sec,
            "min_score": config.min_score,
            "court_margin_ft": config.court_margin_ft,
        },
        "events": [event_to_payload(event) for event in events],
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    """
    把产物字典写成带缩进的 JSON 文件（中文不转义）。

    自动创建父目录；返回写入后的路径。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_raw_trajectory(path: Path, *, job_id: str, samples: list[BallFrameSample], **kwargs: Any) -> Path:
    """便捷方法：构造并写入"原始球轨迹"JSON。"""
    return write_json(path, build_raw_trajectory_payload(job_id=job_id, samples=samples, **kwargs))


def write_cleaned_trajectory(path: Path, *, job_id: str, samples: list[TrajectoryPoint], **kwargs: Any) -> Path:
    """便捷方法：构造并写入"清洗后球轨迹"JSON。"""
    return write_json(path, build_cleaned_trajectory_payload(job_id=job_id, samples=samples, **kwargs))


def write_bounce_events(path: Path, *, job_id: str, events: list[BounceEvent], **kwargs: Any) -> Path:
    """便捷方法：构造并写入"弹跳事件"JSON。"""
    return write_json(path, build_bounce_events_payload(job_id=job_id, events=events, **kwargs))


def build_ball_overlay_payload(
    *,
    job_id: str,
    video_id: str | None = None,
    samples: list[BallFrameSample],
    source_width: int = 0,
    source_height: int = 0,
    fps: float = 0.0,
    frame_stride: int = 1,
    processed_frame_count: int = 0,
    status: str = "available",
    detail: str = "ball overlay generated",
) -> dict[str, Any]:
    """从 BallFrameSample 列表构造 ball_overlay.json 的 payload。

    只包含球分析实际运行过的抽样帧（方法 A），不强制补全每个 frame_index。
    顶层包含 source 和 coverage 元数据以弥补稀疏帧的可索引性问题。
    """
    overlay_frames: list[dict[str, Any]] = []
    detected_count = 0
    for sample in samples:
        bbox: list[float] | None = None
        if sample.image_xy is not None:
            bbox = [
                float(sample.image_xy[0]),
                float(sample.image_xy[1]),
                float(sample.image_xy[0]),
                float(sample.image_xy[1]),
            ]
            # 尝试从 diagnostics 中提取原始 bbox
            diag_bbox = sample.diagnostics.get("bbox")
            if isinstance(diag_bbox, list | tuple) and len(diag_bbox) == 4:
                try:
                    bbox = [float(v) for v in diag_bbox]
                except (TypeError, ValueError):
                    pass
        track_status: str
        if sample.accepted:
            track_status = "detected"
            detected_count += 1
        elif sample.reject_reason is not None:
            track_status = "rejected"
        else:
            track_status = "missing"

        court: dict[str, Any] | None = None
        if sample.court_xy is not None:
            court = {"x": round(float(sample.court_xy[0]), 4), "y": round(float(sample.court_xy[1]), 4), "unit": "ft"}

        overlay_frames.append(
            {
                "frame_index": int(sample.frame_index),
                "timestamp_seconds": round(float(sample.timestamp_sec), 6),
                "ball": {
                    "center": (
                        {"x": round(float(sample.image_xy[0]), 2), "y": round(float(sample.image_xy[1]), 2)}
                        if sample.image_xy is not None
                        else None
                    ),
                    "bbox": bbox,
                    "confidence": round(float(sample.confidence), 4) if sample.confidence is not None else None,
                    "track_status": track_status,
                    "court": court,
                },
            }
        )

    missing_count = max(0, processed_frame_count - detected_count)
    detection_rate = round(detected_count / max(1, processed_frame_count), 4) if processed_frame_count > 0 else 0.0

    return {
        "schema_version": "ball_overlay.v1",
        "job_id": job_id,
        "video_id": video_id,
        "status": status,
        "detail": detail,
        "source": {
            "width": int(source_width),
            "height": int(source_height),
            "fps": round(float(fps), 2),
            "frame_stride": int(frame_stride),
            "processed_frame_count": int(processed_frame_count),
        },
        "coverage": {
            "overlay_frame_count": detected_count,
            "missing_frame_count": missing_count,
            "detection_rate": detection_rate,
        },
        "frames": overlay_frames,
    }


def write_ball_overlay(
    path: Path, *, job_id: str, video_id: str | None = None, samples: list[BallFrameSample], **kwargs: Any
) -> Path:
    """便捷方法：构造并写入 ball_overlay.json（前端叠加/可视化用）。"""
    return write_json(path, build_ball_overlay_payload(job_id=job_id, video_id=video_id, samples=samples, **kwargs))
