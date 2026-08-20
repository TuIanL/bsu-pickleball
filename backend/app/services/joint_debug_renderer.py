"""Render persisted joint debug evidence without running analysis again."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np

from app.vision.multiview.debug_trace import load_joint_debug_trace
from app.vision.multiview.joint_artifact import load_fused_trajectory


class JointDebugRenderError(ValueError):
    """Input or output contract error raised by the diagnostic-only renderer."""


@dataclass(frozen=True)
class JointDebugRenderInputs:
    video_paths: Mapping[str, str | os.PathLike[str]]
    trace_path: str | os.PathLike[str]
    trajectory_path: str | os.PathLike[str]
    diagnostics_path: str | os.PathLike[str]
    canonical_frame_path: str | os.PathLike[str]
    timing_mapping_path: str | os.PathLike[str]
    output_video_path: str | os.PathLike[str]
    summary_path: str | os.PathLike[str]
    fps: float = 30.0


_FUNNEL_KEYS = (
    "recovery_opportunity_count",
    "guidance_generated_count",
    "guided_roi_invocation_count",
    "guided_recovery_success_count",
    "base_recovered_count",
)


def render_joint_debug_artifacts(inputs: JointDebugRenderInputs) -> dict[str, object]:
    """Render a four-panel MP4 and its summary from persisted run evidence.

    This function intentionally has no detector, tracker, frame selector, or
    association dependency.  The trace is the source of truth for frame
    decisions; a missing source frame is shown as unavailable rather than
    replaced with a nearest or same-numbered frame.
    """
    trace = _load_object("trace_path", inputs.trace_path, load_joint_debug_trace)
    trajectory_payload = _load_json_object("trajectory_path", inputs.trajectory_path)
    diagnostics = _load_json_object("diagnostics_path", inputs.diagnostics_path)
    canonical_frame = _load_json_object("canonical_frame_path", inputs.canonical_frame_path)
    timing_mapping = _load_json_object("timing_mapping_path", inputs.timing_mapping_path)
    _validate_business_inputs(trace, trajectory_payload, canonical_frame, timing_mapping)
    trajectory = load_fused_trajectory(trajectory_payload)

    view_ids = _trace_view_ids(trace)
    captures = _open_captures(inputs.video_paths, view_ids)
    output_path = Path(inputs.output_video_path)
    summary_path = Path(inputs.summary_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_video = _temporary_path(output_path)
    writer = None
    rendered_ticks = 0
    decode_errors: list[str] = []
    frame_cursors: dict[str, dict[str, object]] = {
        view_id: {"last_index": None, "frame": None} for view_id in view_ids
    }
    try:
        for tick in trace["ticks"]:
            panels: dict[str, np.ndarray] = {}
            for view_id in view_ids:
                view = tick["views"][view_id]
                panels[view_id] = _read_trace_frame(
                    captures[view_id], view, view_id, tick, frame_cursors[view_id]
                )
            canvas = _compose_canvas(
                tick=tick,
                trace=trace,
                panels=panels,
                trajectory=trajectory,
                diagnostics=diagnostics,
            )
            if writer is None:
                height, width = canvas.shape[:2]
                writer = cv2.VideoWriter(
                    str(temporary_video),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    max(float(inputs.fps), 1.0),
                    (width, height),
                )
                if not writer.isOpened():
                    raise JointDebugRenderError(f"unable to open debug MP4 writer: {output_path}")
            writer.write(canvas)
            rendered_ticks += 1
    except JointDebugRenderError:
        raise
    except Exception as exc:  # noqa: BLE001
        decode_errors.append(str(exc))
        raise JointDebugRenderError(f"debug renderer failed at tick {rendered_ticks}: {exc}") from exc
    finally:
        if writer is not None:
            writer.release()
        for capture in captures.values():
            capture.release()

    if rendered_ticks == 0:
        temporary_video.unlink(missing_ok=True)
        raise JointDebugRenderError("joint debug trace contains no ticks")
    _transcode_for_browser(temporary_video, output_path)
    summary = _build_summary(
        trace=trace,
        diagnostics=diagnostics,
        trajectory=trajectory_payload,
        output_video_path=output_path,
        summary_path=summary_path,
        rendered_ticks=rendered_ticks,
        decode_errors=decode_errors,
    )
    _write_json_atomic(summary_path, summary)
    return summary


def _trace_view_ids(trace: dict[str, object]) -> list[str]:
    ticks = trace.get("ticks")
    if not isinstance(ticks, list) or not ticks or not isinstance(ticks[0], dict):
        raise JointDebugRenderError("trace schema/input error: ticks are empty")
    views = ticks[0].get("views")
    if not isinstance(views, dict) or len(views) < 2:
        raise JointDebugRenderError("trace schema/input error: at least two views are required")
    ids = [str(view_id) for view_id in views]
    for index, tick in enumerate(ticks):
        if not isinstance(tick, dict) or not isinstance(tick.get("views"), dict):
            raise JointDebugRenderError(f"trace schema/input error: tick {index} has no views")
        if set(tick["views"]) != set(ids):
            raise JointDebugRenderError(f"trace schema/input error: tick {index} view set differs")
    return ids


def _open_captures(
    video_paths: Mapping[str, str | os.PathLike[str]],
    view_ids: list[str],
) -> dict[str, cv2.VideoCapture]:
    missing = [view_id for view_id in view_ids if view_id not in video_paths]
    if missing:
        raise JointDebugRenderError(f"missing input video_paths for view(s): {', '.join(missing)}")
    captures: dict[str, cv2.VideoCapture] = {}
    try:
        for view_id in view_ids:
            path = Path(video_paths[view_id])
            if not path.is_file():
                raise JointDebugRenderError(f"missing input video for {view_id}: {path}")
            capture = cv2.VideoCapture(str(path))
            if not capture.isOpened():
                capture.release()
                raise JointDebugRenderError(f"unreadable input video for {view_id}: {path}")
            captures[view_id] = capture
    except Exception:
        for capture in captures.values():
            capture.release()
        raise
    return captures


def _read_trace_frame(
    capture: cv2.VideoCapture,
    view: dict[str, object],
    view_id: str,
    tick: dict[str, object],
    cursor: dict[str, object],
) -> np.ndarray:
    status = str(view.get("status", "unavailable"))
    source_index = view.get("source_frame_index")
    # available / fallback_valid_start（历史窗口开头回退帧）/ available_extrapolated（锚点区间外
    # 对称外推显示帧）都可直接渲染：trace 已记录真实源帧索引，渲染器只负责解码呈现，
    # 不替换/伪造帧。历史 fallback_valid_start 仍保留兼容（2026-08-13 窗口开头黑屏修复）。
    renderable = status in ("available", "fallback_valid_start", "available_extrapolated")
    if not renderable or source_index is None:
        return _unavailable_panel(view_id, status, str(view.get("selection_error_ms")))
    try:
        source_index = int(source_index)
    except (TypeError, ValueError) as exc:
        raise JointDebugRenderError(
            f"trace schema/input error: {view_id} source_frame_index is not an integer at tick {tick.get('canonical_tick')}"
        ) from exc
    last_index = cursor.get("last_index")
    cached_frame = cursor.get("frame")
    if source_index == last_index and isinstance(cached_frame, np.ndarray):
        frame = cached_frame.copy()
        ok = True
    elif last_index is not None and source_index == int(last_index) + 1:
        # The trace normally advances monotonically. Keep the persisted source
        # frame decision, but avoid an expensive decoder seek for this common case.
        ok, frame = capture.read()
        if ok and frame is not None:
            cursor["last_index"] = source_index
            cursor["frame"] = frame.copy()
    else:
        capture.set(cv2.CAP_PROP_POS_FRAMES, source_index)
        ok, frame = capture.read()
        if ok and frame is not None:
            cursor["last_index"] = source_index
            cursor["frame"] = frame.copy()
    if not ok or frame is None:
        raise JointDebugRenderError(
            f"source frame decode failed: view={view_id}, frame={source_index}, tick={tick.get('canonical_tick')}"
        )
    _draw_view_overlays(frame, view)
    return _fit_panel(frame, 640, 360)


# display-only 帧状态：该 tick 未执行 perception（tracker 未 step），只供回放显示
_DISPLAY_ONLY_STATUSES = ("available_extrapolated", "fallback_valid_start")
_DISPLAY_ONLY_BANNER_COLOR = (80, 130, 255)  # BGR 醒目橙红
# tracker 候选框（live 但未满足 lock_only formal eligibility）：细线弱色
_CANDIDATE_COLOR = (0, 170, 190)  # BGR 柔和琥珀
_FORMAL_DETECTED_COLOR = (0, 190, 255)  # BGR 高亮橙（既有正式框样式）


def _draw_view_overlays(frame: np.ndarray, view: dict[str, object]) -> None:
    status = str(view.get("status", "unavailable"))
    if status in _DISPLAY_ONLY_STATUSES:
        # display-only 帧：主动禁止一切检测框/footpoint/guidance overlay（design D3），
        # 不依赖生产端恰好为空——即使异常 trace 带有 detections 也不画，杜绝伪造框。
        _draw_status_line(frame, view)
        cv2.putText(
            frame,
            "DISPLAY ONLY | TRACKING NOT STEPPED",
            (12, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            _DISPLAY_ONLY_BANNER_COLOR,
            2,
            cv2.LINE_AA,
        )
        return
    for detection in view.get("detections", []):
        if not isinstance(detection, dict):
            continue
        bbox = detection.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            x1, y1, x2, y2 = (int(float(value)) for value in bbox)
            color = _FORMAL_DETECTED_COLOR if detection.get("tracking_status") == "detected" else (150, 150, 150)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = str(detection.get("player_id") or detection.get("track_id") or "person")
            cv2.putText(frame, label, (x1, max(16, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        footpoint = detection.get("image_footpoint")
        if isinstance(footpoint, list) and len(footpoint) == 2:
            cv2.circle(frame, (int(float(footpoint[0])), int(float(footpoint[1]))), 4, (0, 255, 0), -1)
    # debug-only 候选层：细线弱色，统一 tracker candidate 标签（无 Player_N 正式身份）
    for detection in view.get("candidate_detections", []):
        if not isinstance(detection, dict):
            continue
        bbox = detection.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            x1, y1, x2, y2 = (int(float(value)) for value in bbox)
            cv2.rectangle(frame, (x1, y1), (x2, y2), _CANDIDATE_COLOR, 1)
            label = f"track_{detection.get('track_id')} | tracker candidate"
            cv2.putText(frame, label, (x1, max(16, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _CANDIDATE_COLOR, 1, cv2.LINE_AA)
    for guidance in view.get("guidance", []):
        if not isinstance(guidance, dict):
            continue
        roi = guidance.get("roi")
        if isinstance(roi, list) and len(roi) == 4:
            x1, y1, x2, y2 = (int(float(value)) for value in roi)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 80, 210), 2)
    _draw_status_line(frame, view)


def _draw_status_line(frame: np.ndarray, view: dict[str, object]) -> None:
    mapping_mode = view.get("mapping_mode")
    mode_label = f" mode={mapping_mode}" if mapping_mode else ""
    cv2.putText(
        frame,
        f"status={view.get('status')} obs={view.get('observation_status')}{mode_label}",
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def _compose_canvas(
    *,
    tick: dict[str, object],
    trace: dict[str, object],
    panels: dict[str, np.ndarray],
    trajectory,
    diagnostics: dict[str, object],
) -> np.ndarray:
    view_ids = list(panels)
    first = _fit_panel(panels[view_ids[0]], 640, 360)
    second = _fit_panel(panels[view_ids[1]], 640, 360)
    court = _court_panel(tick, trajectory)
    status = _status_panel(tick, trace, diagnostics)
    return np.vstack((np.hstack((first, second)), np.hstack((court, status))))


@dataclass(frozen=True)
class _CourtLayout:
    """横置 canonical court 的等比布局（44 ft 横轴 × 20 ft 纵轴，单一 px/ft）。"""

    origin_x: int
    origin_y: int
    scale: float  # px/ft，横向纵向共用同一比例（不得分别拉伸）
    court_width_px: int
    court_height_px: int


def _court_layout(panel_width: int = 640, panel_height: int = 260) -> _CourtLayout:
    """在面板内以单一 px/ft 比例排布 44×20 ft 球场（约 484×220，真实 2.2:1）。"""
    horizontal_margin = 20.0
    top_margin = 20.0
    bottom_margin = 20.0
    available_width = panel_width - 2.0 * horizontal_margin
    available_height = panel_height - top_margin - bottom_margin
    scale = min(available_width / 44.0, available_height / 20.0)
    court_width_px = int(44.0 * scale)
    court_height_px = int(20.0 * scale)
    return _CourtLayout(
        origin_x=(panel_width - court_width_px) // 2,
        origin_y=int(top_margin + (available_height - court_height_px) / 2.0),
        scale=scale,
        court_width_px=court_width_px,
        court_height_px=court_height_px,
    )


def _court_to_panel(x_ft: float, y_ft: float, layout: _CourtLayout) -> tuple[int, int]:
    """canonical 球场坐标 → 面板像素（显示层轴交换：screen_x ← y_ft、screen_y ← x_ft）。

    保留既有 [0,20]×[0,44] clamp；canonical (x_ft, y_ft) 数据本身不修改。
    """
    clamped_x = max(0.0, min(20.0, float(x_ft)))
    clamped_y = max(0.0, min(44.0, float(y_ft)))
    return (
        int(layout.origin_x + clamped_y * layout.scale),
        int(layout.origin_y + clamped_x * layout.scale),
    )


def _court_panel(tick: dict[str, object], trajectory) -> np.ndarray:
    panel = np.full((260, 640, 3), 245, dtype=np.uint8)
    layout = _court_layout()
    left, top = layout.origin_x, layout.origin_y
    right = layout.origin_x + layout.court_width_px
    bottom = layout.origin_y + layout.court_height_px
    line_color = (35, 80, 35)
    # 外边界（44×20 ft，等比）
    cv2.rectangle(panel, (left, top), (right, bottom), line_color, 2)
    # 网：y_ft = 22（横向中点）
    net_x, _ = _court_to_panel(0.0, 22.0, layout)
    cv2.line(panel, (net_x, top), (net_x, bottom), line_color, 2)
    # 两侧 NVZ line（距网 7 ft：y_ft = 15 / 29）
    for nvz_y_ft in (15.0, 29.0):
        nvz_x, _ = _court_to_panel(0.0, nvz_y_ft, layout)
        cv2.line(panel, (nvz_x, top), (nvz_x, bottom), line_color, 1)
    # 两段 service centerline（x_ft = 10，NVZ → 底线）
    for y_from, y_to in ((0.0, 15.0), (29.0, 44.0)):
        start = _court_to_panel(10.0, y_from, layout)
        end = _court_to_panel(10.0, y_to, layout)
        cv2.line(panel, start, end, line_color, 1)
    cv2.putText(panel, "canonical court 44x20 ft (to scale)", (14, 248), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 30), 1, cv2.LINE_AA)
    for sample in trajectory.samples:
        if sample.reference_frame_index != int(tick.get("reference_frame_index", -1)):
            continue
        x, y = _court_to_panel(sample.x_ft, sample.y_ft, layout)
        cv2.circle(panel, (x, y), 6, (30, 70, 220), -1)
        cv2.putText(panel, sample.global_player_id, (x + 8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)
    return panel


def _status_panel(
    tick: dict[str, object],
    trace: dict[str, object],
    diagnostics: dict[str, object],
) -> np.ndarray:
    panel = np.full((260, 640, 3), 25, dtype=np.uint8)
    lines = [
        f"run {trace.get('run_id')}  tick {tick.get('canonical_tick')}/{trace.get('tick_count')}",
        f"t={float(tick.get('canonical_timestamp_ms', 0.0)) / 1000.0:.3f}s  authoritative={tick.get('authoritative_tick')}",
        f"mode={trace.get('execution_mode')} quality={trace.get('sync_quality')}",
    ]
    for view_id, status in (tick.get("frame_status") or {}).items():
        lines.append(f"{view_id}: {status}")
    recovery = tick.get("recovery") or {}
    lines.append("recovery: " + ", ".join(f"{key}={value}" for key, value in recovery.items()) if recovery else "recovery: none")
    funnel = diagnostics.get("recovery_funnel") if isinstance(diagnostics.get("recovery_funnel"), dict) else {}
    lines.append(f"opportunities total={int(funnel.get('recovery_opportunity_count', 0))}")
    for index, line in enumerate(lines[:10]):
        cv2.putText(panel, str(line), (16, 28 + index * 23), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (235, 235, 235), 1, cv2.LINE_AA)
    return panel


def _unavailable_panel(view_id: str, status: str, selection_error: str) -> np.ndarray:
    panel = np.full((360, 640, 3), 45, dtype=np.uint8)
    cv2.putText(panel, view_id, (24, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (245, 245, 245), 2, cv2.LINE_AA)
    cv2.putText(panel, f"UNAVAILABLE: {status}", (24, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (80, 190, 255), 2, cv2.LINE_AA)
    cv2.putText(panel, f"selection_error_ms={selection_error}", (24, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)
    return panel


def _fit_panel(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    if frame is None or frame.size == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)
    source_height, source_width = frame.shape[:2]
    scale = min(width / max(source_width, 1), height / max(source_height, 1))
    resized = cv2.resize(frame, (max(1, int(source_width * scale)), max(1, int(source_height * scale))))
    panel = np.zeros((height, width, 3), dtype=np.uint8)
    y = (height - resized.shape[0]) // 2
    x = (width - resized.shape[1]) // 2
    panel[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return panel


def _validate_business_inputs(
    trace: dict[str, object],
    trajectory: dict[str, object],
    canonical_frame: dict[str, object],
    timing_mapping: dict[str, object],
) -> None:
    if trajectory.get("schema_version") != "fused_player_trajectory.v2":
        raise JointDebugRenderError("trajectory schema/input error: fused_player_trajectory.v2 is required")
    if canonical_frame.get("schema_version") != "canonical_court_frame.v1":
        raise JointDebugRenderError("canonical frame schema/input error: canonical_court_frame.v1 is required")
    if not timing_mapping:
        raise JointDebugRenderError("timing mapping schema/input error: mapping is empty")
    if trace.get("run_id") != trajectory.get("run_id"):
        raise JointDebugRenderError("trace/trajectory run_id mismatch")


def _load_json_object(label: str, path: str | os.PathLike[str]) -> dict[str, object]:
    target = Path(path)
    if not target.is_file():
        raise JointDebugRenderError(f"missing input {label}: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JointDebugRenderError(f"unreadable input {label}: {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise JointDebugRenderError(f"schema/input error {label}: expected JSON object")
    return payload


def _load_object(label: str, path: str | os.PathLike[str], loader) -> dict[str, object]:
    target = Path(path)
    if not target.is_file():
        raise JointDebugRenderError(f"missing input {label}: {target}")
    try:
        return loader(path)
    except ValueError as exc:
        raise JointDebugRenderError(f"schema/input error {label}: {exc}") from exc


def _build_summary(
    *,
    trace: dict[str, object],
    diagnostics: dict[str, object],
    trajectory: dict[str, object],
    output_video_path: Path,
    summary_path: Path,
    rendered_ticks: int,
    decode_errors: list[str],
) -> dict[str, object]:
    raw_funnel = diagnostics.get("recovery_funnel")
    funnel = raw_funnel if isinstance(raw_funnel, dict) else {}
    counts = {key: int(funnel.get(key, 0) or 0) for key in _FUNNEL_KEYS}
    evidence = {
        "recovery_opportunity": counts["recovery_opportunity_count"],
        "guidance_generated": counts["guidance_generated_count"],
        "guided_roi_invocation": counts["guided_roi_invocation_count"],
        "guided_recovery_success": counts["guided_recovery_success_count"],
        "base_recovered": counts["base_recovered_count"],
    }
    return {
        "schema_version": "joint_debug_summary.v1",
        "run_id": trace.get("run_id"),
        "capture_take_id": trace.get("capture_take_id"),
        "trace_schema": trace.get("schema_version"),
        "trajectory_schema": trajectory.get("schema_version"),
        "output_video_path": str(output_video_path),
        "summary_path": str(summary_path),
        "rendered_tick_count": rendered_ticks,
        "trace_tick_count": trace.get("tick_count"),
        "authority": {
            "execution_mode": trace.get("execution_mode"),
            "sync_quality": trace.get("sync_quality"),
            "authoritative_joint_eligible": trace.get("authoritative_joint_eligible"),
            "timing_authority_by_view": trace.get("timing_authority_by_view"),
        },
        "recovery_funnel": counts,
        "recovery_evidence": evidence,
        "natural_recovery_opportunity_zero": counts["recovery_opportunity_count"] == 0,
        "decode_errors": decode_errors,
    }


def _temporary_path(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=f".{target.stem}.", suffix=".mp4", dir=target.parent, delete=False)
    handle.close()
    return Path(handle.name)


def _transcode_for_browser(source_path: Path, output_path: Path) -> None:
    """Publish H.264 MP4 because browser playback does not reliably support mp4v."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        os.replace(source_path, output_path)
        return

    encoded_path = _temporary_path(output_path)
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source_path),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(encoded_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip() or f"ffmpeg exited with {completed.returncode}"
            raise JointDebugRenderError(f"browser-compatible MP4 transcode failed: {detail}")
        os.replace(encoded_path, output_path)
    finally:
        source_path.unlink(missing_ok=True)
        encoded_path.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
