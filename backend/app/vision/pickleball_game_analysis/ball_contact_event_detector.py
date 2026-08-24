"""启发式击球候选检测（ball_contact_event_detector）。

纯启发式：基于轨迹运动特征判断击球候选，不强接入姿态关键点。
关键约束（设计 D2）：
  - 突变前/后都有连续有效观测；
  - 速度方向突变或幅值突变达到阈值；
  - 突变前后局部拟合残差低（排除孤立误检）；
  - 不是长缺失后的首次重新锁定；
  - 满足最小事件间隔（refractory period）。

弹地抑制不在本模块执行：bounce suppression 是 `BallEventResolver.prefilter`
的唯一权威（不变量 I7），本模块不接收 `bounce_events`。

输出 `hit_candidate / rejected_hit` 及结构化拒绝原因。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import acos, degrees, hypot, isfinite

import numpy as np

from app.vision.pickleball_game_analysis.schemas import Point2D, TrajectoryPoint


@dataclass(frozen=True)
class ContactDetectorConfig:
    """击球候选检测超参数（透传 ReconstructionConfig 中 hit_* 项）。"""

    context_points: int = 4
    direction_change_deg: float = 35.0
    speed_change_ratio: float = 1.8
    fit_residual_px: float = 18.0
    # 时间是权威连续性语义；帧字段仅保留旧调用兼容与诊断。
    effective_fps: float = 30.0
    frame_stride: int = 1
    max_context_gap_sec: float = 0.12
    min_event_gap_sec: float = 10.0 / 30.0
    min_event_gap_frames: int = 10


@dataclass
class HitCandidate:
    """一个击球候选（检测器输出）。"""

    frame_index: int
    timestamp_sec: float
    image_xy: Point2D
    confidence: float
    status: str = "hit_candidate"  # hit_candidate / confirmed_hit / rejected_hit / ambiguous
    rejection_reason: str | None = None
    diagnostics: dict = field(default_factory=dict)


class BallContactEventDetector:
    """在清洗后轨迹上检测击球候选。"""

    def __init__(self, config: ContactDetectorConfig | None = None) -> None:
        self.config = config or ContactDetectorConfig()

    def detect(
        self,
        points: list[TrajectoryPoint],
        fps: float = 30.0,
        frame_stride: int | None = None,
    ) -> list[HitCandidate]:
        """对整条清洗轨迹扫描，返回击球候选列表（按帧序）。

        弹地抑制不在本模块执行（I7），候选状态只由运动突变与局部拟合判定。
        """
        valid = [i for i, p in enumerate(points) if self._valid_xy(p.image_xy)]
        if len(valid) < 2 * self.config.context_points + 2:
            return []

        ctx = self.config.context_points
        source_fps = fps if fps > 0 else self.config.effective_fps
        stride = max(1, int(frame_stride or self.config.frame_stride))
        expected_step_sec = stride / max(source_fps, 1e-6)
        max_context_gap_sec = max(self.config.max_context_gap_sec, expected_step_sec * 1.75)
        candidates: list[HitCandidate] = []
        for pos, index in enumerate(valid):
            # 前后各需足够连续有效观测
            if pos < ctx or pos + ctx >= len(valid):
                continue
            before_indices = valid[pos - ctx : pos]
            after_indices = valid[pos + 1 : pos + ctx + 1]

            before_pts = [points[i] for i in before_indices]
            after_pts = [points[i] for i in after_indices]
            point = points[index]

            # 前后上下文必须在真实时间上连续。合法抽帧（例如 60 FPS、stride=2）
            # 的 frame index 差为 2，但 timestamp 仍是正常的一个处理时间步。
            context = [*before_pts, point, *after_pts]
            gaps = [right.timestamp_sec - left.timestamp_sec for left, right in zip(context[:-1], context[1:], strict=False)]
            if any(gap <= 0 or gap > max_context_gap_sec for gap in gaps):
                continue

            v_in = self._mean_velocity(before_pts)
            v_out = self._mean_velocity(after_pts)
            if v_in is None or v_out is None:
                continue

            turn_deg = self._angle_between(v_in, v_out)
            speed_in = hypot(v_in[0], v_in[1])
            speed_out = hypot(v_out[0], v_out[1])
            speed_ratio = max(speed_in, speed_out) / max(min(speed_in, speed_out), 1e-6)

            motion_breach = (
                turn_deg >= self.config.direction_change_deg or speed_ratio >= self.config.speed_change_ratio
            )
            if not motion_breach:
                continue

            # 突变前后局部拟合残差低（排除孤立误检）
            residual_before = self._local_linear_residual(before_pts)
            residual_after = self._local_linear_residual(after_pts)
            if residual_before > self.config.fit_residual_px or residual_after > self.config.fit_residual_px:
                candidates.append(
                    HitCandidate(
                        frame_index=point.frame_index,
                        timestamp_sec=point.timestamp_sec,
                        image_xy=(float(point.image_xy[0]), float(point.image_xy[1])),
                        confidence=0.0,
                        status="rejected_hit",
                        rejection_reason="high_fit_residual",
                        diagnostics={
                            "turn_degrees": round(turn_deg, 2),
                            "speed_ratio": round(speed_ratio, 2),
                            "residual_before_px": round(residual_before, 2),
                            "residual_after_px": round(residual_after, 2),
                            "max_context_gap_sec": round(max(gaps, default=0.0), 6),
                            "effective_fps": round(source_fps / stride, 6),
                            "frame_stride": stride,
                        },
                    )
                )
                continue

            confidence = self._candidate_score(turn_deg, speed_ratio)
            candidates.append(
                HitCandidate(
                    frame_index=point.frame_index,
                    timestamp_sec=point.timestamp_sec,
                    image_xy=(float(point.image_xy[0]), float(point.image_xy[1])),
                    confidence=confidence,
                    status="hit_candidate",
                    rejection_reason=None,
                    diagnostics={
                        "turn_degrees": round(turn_deg, 2),
                        "speed_ratio": round(speed_ratio, 2),
                        "residual_before_px": round(residual_before, 2),
                        "residual_after_px": round(residual_after, 2),
                        "max_context_gap_sec": round(max(gaps, default=0.0), 6),
                        "effective_fps": round(source_fps / stride, 6),
                        "frame_stride": stride,
                    },
                )
            )

        # refractory period：保留置信度更高的候选
        confirmed = [c for c in candidates if c.status == "hit_candidate"]
        confirmed.sort(key=lambda c: c.confidence, reverse=True)
        selected: list[HitCandidate] = []
        min_event_gap_sec = (
            self.config.min_event_gap_sec
            if self.config.min_event_gap_sec > 0
            else self.config.min_event_gap_frames / max(source_fps, 1e-6)
        )
        for candidate in confirmed:
            if any(abs(candidate.timestamp_sec - kept.timestamp_sec) < min_event_gap_sec for kept in selected):
                continue
            selected.append(candidate)
        selected.sort(key=lambda c: c.frame_index)
        for candidate in selected:
            candidate.status = "confirmed_hit"

        # 组装结果：confirmed 在前，其余按帧序
        result = [c for c in candidates if c.status != "confirmed_hit"]
        result.sort(key=lambda c: c.frame_index)
        return selected + result

    # ---- 内部工具 ----

    @staticmethod
    def _valid_xy(xy: Point2D | None) -> bool:
        return xy is not None and isfinite(xy[0]) and isfinite(xy[1])

    @staticmethod
    def _mean_velocity(points: list[TrajectoryPoint]) -> tuple[float, float] | None:
        """窗口内平均速度向量（像素/秒），不依赖 source frame stride。"""
        if len(points) < 2:
            return None
        total = [0.0, 0.0]
        count = 0
        for left, right in zip(points[:-1], points[1:], strict=False):
            if left.image_xy is None or right.image_xy is None:
                continue
            gap = right.timestamp_sec - left.timestamp_sec
            if gap <= 0:
                continue
            total[0] += (right.image_xy[0] - left.image_xy[0]) / gap
            total[1] += (right.image_xy[1] - left.image_xy[1]) / gap
            count += 1
        if count == 0:
            return None
        return (total[0] / count, total[1] / count)

    @staticmethod
    def _angle_between(a: tuple[float, float], b: tuple[float, float]) -> float:
        denom = hypot(a[0], a[1]) * hypot(b[0], b[1])
        if denom <= 1e-6:
            return 0.0
        cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / denom))
        return float(degrees(acos(cosine)))

    @staticmethod
    def _local_linear_residual(points: list[TrajectoryPoint]) -> float:
        """窗口内点到最佳拟合直线的平均垂直距离（衡量局部平滑度）。"""
        xs = [p.image_xy[0] for p in points if p.image_xy is not None]
        ys = [p.image_xy[1] for p in points if p.image_xy is not None]
        if len(xs) < 3:
            return 0.0
        x = np.asarray(xs, dtype=np.float64)
        y = np.asarray(ys, dtype=np.float64)
        a, b = np.polyfit(x, y, 1)
        return float(np.mean(np.abs(y - (a * x + b))))

    @staticmethod
    def _candidate_score(turn_deg: float, speed_ratio: float) -> float:
        """候选置信度：方向突变与速度突变的综合分（0~1）。"""
        angle_score = min(1.0, turn_deg / 90.0)
        speed_score = min(1.0, max(0.0, speed_ratio - 1.0) / 1.5)
        return round(max(0.05, 0.6 * angle_score + 0.4 * speed_score), 3)
