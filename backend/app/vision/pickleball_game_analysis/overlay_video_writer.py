"""Write annotated analysis overlay videos."""

from __future__ import annotations

# defaultdict：按帧序号分组时默认空列表；Path：面向对象的文件路径；Any：宽松类型标注（叠加数据为 dict）。
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2  # type: ignore
import numpy as np

# 小地图渲染器，用于在视频角落叠加球场俯视小地图。
from app.vision.pickleball_game_analysis.minimap_visualizer import MinimapVisualizer
from app.services.analysis_window import AnalysisWindowError, resolve_analysis_window
from app.services.frame_timing_provider import FrameTimingProvider

# 可视化配置、坐标点、结果对象，以及按语言取标签的函数。
from app.vision.pickleball_game_analysis.visualization_schemas import (
    VisualizationConfig,
    VisualizationPoint,
    VisualizationResult,
    labels_for,
)


class OverlayVideoWriter:
    def __init__(self, config: VisualizationConfig | None = None) -> None:
        # 配置缺省时用默认值；labels 按配置语言取对应文案；minimap 复用同一份配置。
        self.config = config or VisualizationConfig()
        self.labels = labels_for(self.config.language)
        self.minimap = MinimapVisualizer(config=self.config)

    def write(
        self,
        *,
        source_video_path: Path,
        output_path: Path,
        tracking_overlay: dict[str, Any] | None = None,
        pose_overlay: dict[str, Any] | None = None,
        ball_overlay: dict[str, Any] | None = None,
        player_points: list[VisualizationPoint] | None = None,
        ball_points: list[VisualizationPoint] | None = None,
        bounce_points: list[VisualizationPoint] | None = None,
        fps_override: float | None = None,
        clip_start_ms: int | None = None,
        clip_end_ms: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> VisualizationResult:
        # 把人物检测/姿态/球检测等叠加层以及球场坐标点绘制到视频帧上，写出叠加视频。
        # 任一前置条件不满足时返回带状态说明的 VisualizationResult（不抛异常）。
        if not source_video_path.exists():
            return VisualizationResult("unavailable", f"源视频不存在：{source_video_path}")
        cap = cv2.VideoCapture(str(source_video_path))
        if not cap.isOpened():
            return VisualizationResult("unavailable", "源视频无法打开，跳过叠加视频生成")
        # 读取视频帧率与尺寸；读取失败时用默认值（帧率 25，尺寸为 0）。
        fps = float(fps_override or cap.get(cv2.CAP_PROP_FPS) or 25.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            cap.release()
            return VisualizationResult("failed", "源视频尺寸无效，无法写出叠加视频")
        timing_provider = FrameTimingProvider.from_media(
            source_video_path,
            frame_count=frame_count,
            fps=fps,
        )
        try:
            window = resolve_analysis_window(
                source_duration_ms=int(timing_provider.duration_seconds * 1000),
                source_frame_count=frame_count,
                fps=fps,
                clip_start_ms=clip_start_ms,
                clip_end_ms=clip_end_ms,
                timing_provider=timing_provider,
            )
        except AnalysisWindowError as exc:
            cap.release()
            return VisualizationResult("failed", f"叠加视频窗口无效：{exc}")
        start_frame = window.requested_start_frame if window.enabled else 0
        end_frame = window.requested_end_frame if window.enabled else frame_count
        assert start_frame is not None or not window.enabled
        if window.enabled:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame or 0)

        # 确保输出目录存在，并用 mp4v 编码创建 VideoWriter。
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            cap.release()
            return VisualizationResult("failed", "OpenCV 无法初始化 mp4 writer")

        # 把三种叠加层按 frame_index 建索引，便于逐帧 O(1) 查找。
        tracking_by_frame = _frames_by_index(tracking_overlay, "frames")
        pose_by_frame = _frames_by_index(pose_overlay, "frames")
        ball_by_frame = _frames_by_index(ball_overlay, "frames")
        # 坐标点缺省时置为空列表。
        player_points = player_points or []
        ball_points = ball_points or []
        bounce_points = bounce_points or []
        points_by_frame = _points_by_frame(ball_points)
        bounces_by_frame = _points_by_frame(bounce_points)
        # 预构建球员帧索引表（frame_index → {player_id → point}）
        player_frame_table: dict[int, dict[str, VisualizationPoint]] = defaultdict(dict)
        for pp in player_points:
            if pp.frame_index is not None:
                label = pp.label or ""
                player_frame_table[pp.frame_index][label] = pp
        trail_seconds = max(0.0, float(getattr(self.config, "minimap_player_trail_seconds", 0.0)))
        has_render_track = bool(player_frame_table)
        frame_index = start_frame or 0
        written = 0
        from collections import deque

        player_trails: dict[str, deque[VisualizationPoint]] = defaultdict(deque)
        try:
            # 逐帧读取、绘制、写回。
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_index >= end_frame:
                    break
                # 依次叠加四种信息：追踪框、姿态关键点、球检测、球场坐标点（实际在 minimap 画）。
                self._draw_tracking(frame, tracking_by_frame.get(frame_index))
                self._draw_pose(frame, pose_by_frame.get(frame_index))
                self._draw_ball_overlay(frame, ball_by_frame.get(frame_index))
                self._draw_court_points(
                    frame, points_by_frame.get(frame_index, []), bounces_by_frame.get(frame_index, [])
                )
                current_time = timing_provider.take_timestamp_for_frame(frame_index)
                if current_time is None:
                    current_time = frame_index / fps
                # 在角落叠加小地图面板。
                if has_render_track and trail_seconds > 0:
                    # 轨迹拖尾按 source PTS 时间裁剪，frame index 只负责查找当前帧。
                    current_players = player_frame_table.get(frame_index, {})
                    for pid, pt in current_players.items():
                        trail = player_trails[pid]
                        if trail:
                            prev_seg = trail[-1].segment_id
                            curr_seg = pt.segment_id
                            if prev_seg is not None and curr_seg is not None and prev_seg != curr_seg:
                                trail.clear()
                        trail.append(pt)
                    for pid in list(player_trails):
                        while player_trails[pid] and (
                            player_trails[pid][0].timestamp_seconds is not None
                            and player_trails[pid][0].timestamp_seconds < current_time - trail_seconds
                        ):
                            player_trails[pid].popleft()
                    minimap_player_points = [p for trail in player_trails.values() for p in trail]
                else:
                    minimap_player_points = _points_until_time(player_points, current_time)
                self._draw_minimap(
                    frame,
                    minimap_player_points,
                    _points_until_time(ball_points, current_time),
                    _points_near_time(bounce_points, current_time, window_seconds=0.5),
                )
                # 在画面底部写入“时间: X.XXs”文本。
                cv2.putText(
                    frame,
                    f"{self.labels['frame_time']}: {current_time:.2f}s",
                    (12, max(22, height - 14)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                writer.write(frame)
                written += 1
                if progress_callback is not None and (written == 1 or written % 120 == 0):
                    progress_callback(written, window.requested_frame_count if window.enabled else frame_count)
                frame_index += 1
        except Exception as exc:
            # 写出过程中任何异常都转为失败结果，保证资源被释放。
            return VisualizationResult("failed", f"叠加视频写出失败：{exc}")
        finally:
            # 无论成功失败都释放 writer 与 cap。
            writer.release()
            cap.release()

        # 一帧都没写出视为失败；否则返回成功结果与帧数。
        if written == 0:
            return VisualizationResult("failed", "未写出任何视频帧")
        return VisualizationResult(
            "available",
            f"已生成 {written} 帧分析叠加视频",
            str(output_path),
            item_count=written,
            metadata={
                **window.metadata(),
                "output_time_origin_ms": int(
                    (timing_provider.take_timestamp_for_frame(start_frame or 0) or 0.0) * 1000
                ),
                "timing_provenance": timing_provider.metadata(),
                "output_first_source_frame": start_frame if written else None,
                "output_last_source_frame": (frame_index - 1) if written else None,
                "written_frame_count": written,
            },
        )

    def _draw_tracking(self, frame: np.ndarray, overlay_frame: dict[str, Any] | None) -> None:
        # 绘制该帧的人物检测框与标签。
        if not overlay_frame:
            return
        for detection in overlay_frame.get("detections", []):
            bbox = detection.get("bbox")
            # bbox 必须是长度 >=4 的列表，否则跳过该检测。
            if not isinstance(bbox, list) or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = [int(round(float(v))) for v in bbox[:4]]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (35, 190, 90), 2)  # 绿色框
            # 标签优先级：label > player_id > 默认“球员”文案。
            # 不展示原始 track_id：身份契约要求用户可见标签只呈现 canonical 身份。
            label = str(detection.get("label") or detection.get("player_id") or self.labels["player"])
            cv2.putText(
                frame, label, (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (35, 190, 90), 2, cv2.LINE_AA
            )

    def _draw_pose(self, frame: np.ndarray, overlay_frame: dict[str, Any] | None) -> None:
        # 绘制该帧的姿态关键点（低置信度点被过滤）。
        if not overlay_frame:
            return
        for subject in overlay_frame.get("subjects", []):
            keypoints = subject.get("keypoints", [])
            pixels: list[tuple[int, int]] = []
            for point in keypoints:
                # 跳过置信度缺失或低于 0.2 的关键点。
                if (
                    not isinstance(point, dict)
                    or point.get("confidence", 0) is None
                    or float(point.get("confidence", 0)) < 0.2
                ):
                    continue
                try:
                    pixels.append((int(round(float(point["x"]))), int(round(float(point["y"])))))
                except (KeyError, TypeError, ValueError):
                    continue
            # 每个关键点画一个黄色实心圆。
            for pixel in pixels:
                cv2.circle(frame, pixel, 3, (255, 210, 70), -1, lineType=cv2.LINE_AA)
            # 关键点之间按顺序连成折线（这里只是相邻连接，非骨架拓扑）。
            for start, end in zip(pixels, pixels[1:], strict=False):
                cv2.line(frame, start, end, (255, 210, 70), 1, lineType=cv2.LINE_AA)

    def _draw_ball_overlay(self, frame: np.ndarray, overlay_frame: dict[str, Any] | None) -> None:
        # 绘制该帧的球检测中心点与标签。
        if not overlay_frame:
            return
        ball = overlay_frame.get("ball")
        if not isinstance(ball, dict):
            return
        center = ball.get("center")
        if isinstance(center, dict) and center.get("x") is not None and center.get("y") is not None:
            pixel = (int(round(float(center["x"]))), int(round(float(center["y"]))))
            cv2.circle(frame, pixel, 6, (50, 130, 255), -1, lineType=cv2.LINE_AA)  # 蓝色实心圆
            cv2.putText(
                frame,
                self.labels["ball"],
                (pixel[0] + 8, pixel[1]),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (50, 130, 255),
                2,
                cv2.LINE_AA,
            )

    def _draw_court_points(
        self, frame: np.ndarray, ball_points: list[VisualizationPoint], bounce_points: list[VisualizationPoint]
    ) -> None:
        # Court-coordinate points are drawn in the minimap. This hook keeps frame-level alignment explicit.
        # 球场坐标点实际画在小地图里，这里仅保留“逐帧对齐”的占位接口，不做主画面绘制。
        _ = (frame, ball_points, bounce_points)

    def _draw_minimap(
        self,
        frame: np.ndarray,
        player_points: list[VisualizationPoint],
        ball_points: list[VisualizationPoint],
        bounce_points: list[VisualizationPoint],
    ) -> None:
        # 生成小地图面板，并叠加到主画面右上角（半透明混合）。
        panel = self.minimap.render(player_points=player_points, ball_points=ball_points, bounce_points=bounce_points)
        panel_h, panel_w = panel.shape[:2]
        # 若主画面放不下整块面板，则等比缩小（最大缩放到 1.0 倍）。
        if frame.shape[0] < panel_h + 20 or frame.shape[1] < panel_w + 20:
            scale = min((frame.shape[0] - 20) / panel_h, (frame.shape[1] - 20) / panel_w, 1.0)
            if scale <= 0:
                return
            panel = cv2.resize(panel, (int(panel_w * scale), int(panel_h * scale)))
            panel_h, panel_w = panel.shape[:2]
        # 面板放在右上角（距右边 10px、距上边 10px）；取对应 ROI 区域做加权混合（底图 0.25 + 面板 0.75）。
        y1 = 10
        x1 = frame.shape[1] - panel_w - 10
        roi = frame[y1 : y1 + panel_h, x1 : x1 + panel_w]
        frame[y1 : y1 + panel_h, x1 : x1 + panel_w] = cv2.addWeighted(roi, 0.25, panel, 0.75, 0)


def _frames_by_index(payload: dict[str, Any] | None, field: str) -> dict[int, dict[str, Any]]:
    # 把叠加层 payload 按 frame_index 建索引，返回 {帧序号: 该帧叠加数据}。
    if not isinstance(payload, dict):
        return {}
    frames = payload.get(field)
    if not isinstance(frames, list):
        return {}
    indexed: dict[int, dict[str, Any]] = {}
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        try:
            indexed[int(frame.get("frame_index"))] = frame
        except (TypeError, ValueError):
            continue
    return indexed


def _points_by_frame(points: list[VisualizationPoint]) -> dict[int, list[VisualizationPoint]]:
    # 把坐标点按 frame_index 分组，返回 {帧序号: [该帧的点列表]}。
    grouped: dict[int, list[VisualizationPoint]] = defaultdict(list)
    for point in points:
        if point.frame_index is not None:
            grouped[point.frame_index].append(point)
    return grouped


def _points_until_time(points: list[VisualizationPoint], current_time: float) -> list[VisualizationPoint]:
    return [point for point in points if point.timestamp_seconds is None or point.timestamp_seconds <= current_time]


def _points_near_time(
    points: list[VisualizationPoint], current_time: float, *, window_seconds: float
) -> list[VisualizationPoint]:
    return [
        point
        for point in points
        if point.timestamp_seconds is not None and abs(point.timestamp_seconds - current_time) <= window_seconds
    ]
