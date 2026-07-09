"""Ball candidate filtering and trajectory continuity tracking."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot

import numpy as np

from app.vision.pickleball_game_analysis.ball_detector_protocol import BallDetectorProtocol
from app.vision.pickleball_game_analysis.court_adapter import BallCourtAdapter
from app.vision.pickleball_game_analysis.schemas import BallCandidate, BallFrameSample, Point2D


@dataclass(frozen=True)
class BallTrackerConfig:
    """
    球跟踪器超参数（全部带默认值，可调）。

    思路：先用"框尺寸/长宽比/ROI"过滤掉明显不是球的候选，
    再用"轨迹连续性"（距离门限、预测门限、最大缺失帧）从剩余候选里挑最可信的一个。
    """

    confidence: float = 0.18                  # 调用检测器时的置信度阈值
    trajectory_length: int = 30              # 保留的最近有效点数量（滑动窗口）
    max_jump_pixels: float = 220.0           # 与上一个有效点的最大跳变（像素），超出视为不连续
    prediction_gate_pixels: float = 260.0    # 与预测位置的偏差门限（像素），超出视为不连续
    max_missing_frames: int = 5              # 允许连续缺失多少帧（超过则清空最后有效位置）
    roi_padding_ratio: float = 0.08          # ROI 边距的放宽比例（在给定 ROI 外再扩一点）
    max_box_area_ratio: float = 0.004        # 框面积占整帧比例上限（过大不像球）
    max_aspect_ratio: float = 4.0            # 框宽高比上限（过长不像球）
    court_bounds_margin_ft: float = 2.0      # 投影到球场后允许越界的容差（英尺）
    stationary_window_frames: int = 30        # 静态误报检测窗口
    stationary_radius_pixels: float = 5.0     # 窗口内都落在该半径内则视为固定物
    stationary_blacklist_frames: int = 60     # 静止候选跨帧累计帧数，达到后加入永久黑名单
    stationary_blacklist_grid_px: int = 5     # 静止黑名单坐标离散化精度（像素）


class BallTracker:
    """逐帧处理：过滤候选、挑选最可信的球位置、维护轨迹连续性，并投影到球场坐标。"""

    def __init__(
        self,
        detector: BallDetectorProtocol,
        config: BallTrackerConfig | None = None,
        court_adapter: BallCourtAdapter | None = None,
    ) -> None:
        self.detector = detector                      # 底层球检测器（满足 BallDetectorProtocol）
        self.config = config or BallTrackerConfig()   # 超参数
        self.court_adapter = court_adapter or BallCourtAdapter()  # 图像→球场投影器
        self.trajectory: deque[Point2D] = deque(maxlen=self.config.trajectory_length)  # 最近有效点队列
        self.selected_history: deque[Point2D] = deque(maxlen=max(1, self.config.stationary_window_frames))
        self.last_valid_position: Point2D | None = None  # 最近一个被接受的位置
        self.missing_frames = 0                       # 连续未检测到球的帧数
        # 静止黑名单：离散化坐标 → 累计被检测到的帧计数
        self._stationary_blacklist: dict[tuple[int, int], int] = {}
        # 永久黑名单：已达到阈值的静止位置
        self._stationary_blacklist_positions: set[tuple[int, int]] = set()

    def update(
        self,
        frame: np.ndarray,
        frame_index: int,
        timestamp_sec: float,
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None = None,
        homography: Sequence[Sequence[float]] | None = None,
    ) -> BallFrameSample:
        """
        处理一帧，返回该帧的球采样结果 BallFrameSample。

        流程：
          1. 调用检测器得到原始候选；
          2. 过滤（框尺寸/长宽比/ROI）得到候选列表；
          3. 从候选里挑一个最可信的；
          4. 若没候选或挑出的点"不连续"，记为未接受；
          5. 通过连续性检查后，投影到球场坐标并记为有效点。
        """
        raw_candidates = self.detector.detect(frame, conf=self.config.confidence)
        candidates, reject_reasons = self._extract_candidates(raw_candidates, frame.shape, roi_corners)
        # 对所有过滤后候选做静止坐标投票，更新黑名单
        self._update_stationary_blacklist(candidates)
        selected = self._select_candidate(candidates)
        # 情况 A：过滤后没有候选
        if selected is None:
            self._record_missing_detection()
            reason = reject_reasons[0] if reject_reasons else "no_candidates"
            return self._sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=None,
                court_xy=None,
                confidence=None,
                visible=bool(raw_candidates),
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=reason,
                in_bounds=None,
            )

        point = selected.image_xy
        self._record_selected_candidate(point)
        # 静止黑名单检查：若该位置已被标记为静止物，优先拒绝
        # 但若候选与上一有效点连续（跳变/预测均在门限内），则覆盖黑名单允许接受
        blacklist_reason = self._stationary_blacklist_reject_reason(point)
        if blacklist_reason is not None:
            self._record_missing_detection()
            return self._sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=blacklist_reason,
                in_bounds=None,
            )
        stationary_reason = self._stationary_reject_reason()
        if stationary_reason is not None:
            self._record_missing_detection()
            return self._sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=stationary_reason,
                in_bounds=None,
            )

        # 情况 B：有候选，但与已有轨迹不连续（跳变过大 / 偏离预测）
        reject_reason = self._continuity_reject_reason(point)
        if reject_reason is not None:
            self._record_missing_detection()
            return self._sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=reject_reason,
                in_bounds=None,
            )

        # 情况 C：通过连续性检查 → 投影并记录为有效点
        projection = self.court_adapter.project(point, homography)
        bounds_reject_reason = self._court_bounds_reject_reason(projection.court_xy)
        if bounds_reject_reason is not None:
            self._record_missing_detection()
            return self._sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=projection.court_xy,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=bounds_reject_reason,
                in_bounds=projection.in_bounds,
                diagnostics={"court_projection": projection.detail},
            )

        self._append_valid_point(point)
        return self._sample(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            image_xy=point,
            court_xy=projection.court_xy,
            confidence=selected.confidence,
            visible=True,
            accepted=True,
            candidate_count=len(candidates),
            reject_reason=None,
            in_bounds=projection.in_bounds,
            diagnostics={"court_projection": projection.detail},
        )

    def clear(self) -> None:
        """重置跟踪状态（换一段新视频/新作业时调用）。"""
        self.trajectory.clear()
        self.selected_history.clear()
        self.last_valid_position = None
        self.missing_frames = 0
        self._stationary_blacklist.clear()
        self._stationary_blacklist_positions.clear()

    def _extract_candidates(
        self,
        candidates: Sequence[BallCandidate],
        frame_shape: Sequence[int],
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None,
    ) -> tuple[list[BallCandidate], list[str]]:
        """
        候选过滤：按"框尺寸 / 长宽比 / 是否在 ROI 内"筛掉不像球的候选。

        返回：(过滤后的候选列表, 各被拒原因列表)。
        """
        filtered: list[BallCandidate] = []
        reject_reasons: list[str] = []
        frame_area = max(1.0, float(frame_shape[0] * frame_shape[1]))

        for candidate in candidates:
            width = candidate.width
            height = candidate.height
            area_ratio = candidate.area_ratio
            aspect_ratio = candidate.aspect_ratio
            # 若检测器给了宽高，先做有效性与比例计算
            if width is not None and height is not None:
                if width <= 0 or height <= 0:
                    reject_reasons.append("invalid_box")
                    continue
                # 缺失比例信息时，按宽高现算
                area_ratio = area_ratio if area_ratio is not None else (float(width) * float(height)) / frame_area
                aspect_ratio = aspect_ratio if aspect_ratio is not None else max(float(width) / float(height), float(height) / float(width))
            # 框占整帧面积过大 → 不像球
            if area_ratio is not None and area_ratio > self.config.max_box_area_ratio:
                reject_reasons.append("box_too_large")
                continue
            # 长宽比过大（过扁/过长）→ 不像球
            if aspect_ratio is not None and aspect_ratio > self.config.max_aspect_ratio:
                reject_reasons.append("aspect_ratio")
                continue
            # 不在给定 ROI 内 → 排除
            if not self._point_in_roi(candidate.image_xy, roi_corners):
                reject_reasons.append("outside_roi")
                continue
            filtered.append(
                BallCandidate(
                    image_x=float(candidate.image_x),
                    image_y=float(candidate.image_y),
                    confidence=float(candidate.confidence),
                    width=width,
                    height=height,
                    area_ratio=area_ratio,
                    aspect_ratio=aspect_ratio,
                    diagnostics=dict(candidate.diagnostics),
                )
            )
        return filtered, reject_reasons

    def _select_candidate(self, candidates: Sequence[BallCandidate]) -> BallCandidate | None:
        """
        从过滤后的候选里挑一个最可信的。

        规则：
          - 若还没有轨迹历史，直接选置信度最高的；
          - 否则基于"置信度 - 与预测位置的距离 - 框大小惩罚"综合打分，取最高分。
        """
        if not candidates:
            return None
        if not self.trajectory:
            return max(candidates, key=lambda item: item.confidence)
        predicted = self._predict_next_position()

        def score(candidate: BallCandidate) -> float:
            distance = self._distance(candidate.image_xy, predicted)
            size_penalty = float(candidate.area_ratio or 0.0) * 4000.0
            return candidate.confidence * 1000.0 - distance * 1.4 - size_penalty

        return max(candidates, key=score)

    def _point_in_roi(
        self,
        point: Point2D,
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None,
    ) -> bool:
        """
        判断点是否在 ROI（感兴趣区域）内。

        若未提供 ROI 则视为"全部允许"；否则在两个对角点构成的矩形基础上，
        按 roi_padding_ratio 向外放宽一点（避免边缘误杀）。
        """
        if roi_corners is None:
            return True
        x1, y1 = roi_corners[0]
        x2, y2 = roi_corners[1]
        padding = int(max(abs(x2 - x1), abs(y2 - y1)) * self.config.roi_padding_ratio)
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return (left - padding) <= point[0] <= (right + padding) and (top - padding) <= point[1] <= (bottom + padding)

    def _continuity_reject_reason(self, point: Point2D) -> str | None:
        """
        连续性检查：返回拒绝原因（若连续）或 None（若连续良好）。

        仅在"连续缺失帧数未超上限"时才检查；否则放宽（认为轨迹刚断了，先不拒）。
        判据：
          - 与上一个有效点跳变过大（>max_jump_pixels）→ "jump_distance"；
          - 与预测位置偏差过大（>prediction_gate_pixels）→ "prediction_gate"。
        """
        if not self.trajectory:
            return None
        strict_gate = self.missing_frames <= self.config.max_missing_frames
        if not strict_gate:
            return None
        jump_distance = self._distance(point, self.trajectory[-1])
        if jump_distance > self.config.max_jump_pixels:
            return "jump_distance"
        predicted_distance = self._distance(point, self._predict_next_position())
        if predicted_distance > self.config.prediction_gate_pixels:
            return "prediction_gate"
        return None

    def _court_bounds_reject_reason(self, court_xy: Point2D | None) -> str | None:
        if court_xy is None:
            return None
        margin = max(0.0, float(self.config.court_bounds_margin_ft))
        x, y = court_xy
        court = self.court_adapter.court
        if -margin <= x <= court.width_ft + margin and -margin <= y <= court.length_ft + margin:
            return None
        return "projected_outside_court"

    def _record_selected_candidate(self, point: Point2D) -> None:
        self.selected_history.append(point)

    def _stationary_reject_reason(self) -> str | None:
        if len(self.selected_history) < max(1, self.config.stationary_window_frames):
            return None
        points = list(self.selected_history)
        center_x = sum(point[0] for point in points) / len(points)
        center_y = sum(point[1] for point in points) / len(points)
        max_radius = max(self._distance(point, (center_x, center_y)) for point in points)
        if max_radius <= self.config.stationary_radius_pixels:
            return "stationary_candidate"
        return None

    def _update_stationary_blacklist(self, candidates: Sequence[BallCandidate]) -> None:
        """对所有过滤后候选做静止坐标投票，达到阈值的加入永久黑名单。

        算法：将每个候选的图像坐标按 stationary_blacklist_grid_px 精度离散化，
        累加每帧的检测计数。连续被检测帧数达到 stationary_blacklist_frames 时，
        该位置被加入永久黑名单。
        """
        grid = self.config.stationary_blacklist_grid_px
        threshold = self.config.stationary_blacklist_frames
        # 对本帧出现的坐标做离散化并递增计数
        for candidate in candidates:
            grid_x = int(candidate.image_x / grid) * grid
            grid_y = int(candidate.image_y / grid) * grid
            key = (grid_x, grid_y)
            self._stationary_blacklist[key] = self._stationary_blacklist.get(key, 0) + 1
            if self._stationary_blacklist[key] >= threshold:
                self._stationary_blacklist_positions.add(key)

    def _is_blacklisted(self, point: Point2D) -> bool:
        """检查某个坐标是否落入已知静止黑名单区域。"""
        grid = self.config.stationary_blacklist_grid_px
        grid_x = int(point[0] / grid) * grid
        grid_y = int(point[1] / grid) * grid
        return (grid_x, grid_y) in self._stationary_blacklist_positions

    def _stationary_blacklist_reject_reason(self, point: Point2D) -> str | None:
        """检查被黑名单标记的候选是否应被拒绝。

        若候选位置落入静止黑名单，默认应拒绝。
        但若该候选通过了连续性检查（与上一个有效点有明显位移且距离/预测偏差均在门限内），
        则覆盖黑名单——因为真球恰好经过先前被静止物占据的位置时不应被误杀。
        """
        if not self._is_blacklisted(point):
            return None
        # 若轨迹为空，直接拒绝（无历史参考，无法做连续性覆盖判断）
        if not self.trajectory:
            return "stationary_blacklisted"
        jump_distance = self._distance(point, self.trajectory[-1])
        # 若候选点距离上一个有效点很近（静止特征），不覆盖黑名单
        # 使用 2 倍静止半径作为判定，避免静止候选自我绕过黑名单
        if jump_distance < self.config.stationary_radius_pixels * 2:
            return "stationary_blacklisted"
        strict_gate = self.missing_frames <= self.config.max_missing_frames
        if not strict_gate:
            return "stationary_blacklisted"
        if jump_distance > self.config.max_jump_pixels:
            return "stationary_blacklisted"
        predicted_distance = self._distance(point, self._predict_next_position())
        if predicted_distance > self.config.prediction_gate_pixels:
            return "stationary_blacklisted"
        # 通过连续性检查 + 有显著位移 → 覆盖黑名单，允许接受该候选
        return None

    def _predict_next_position(self) -> Point2D:
        """
        用最近两个有效点做"匀速外推"，预测球的下一帧位置。

        若轨迹点不足 2 个，则退回到最近一个有效点本身。
        """
        if len(self.trajectory) < 2:
            return self.trajectory[-1]
        prev_x, prev_y = self.trajectory[-2]
        last_x, last_y = self.trajectory[-1]
        return (last_x + (last_x - prev_x), last_y + (last_y - prev_y))

    def _append_valid_point(self, point: Point2D) -> None:
        """记录一个被接受的有效点：加入轨迹队列、更新最后有效位置、清零缺失计数。"""
        self.trajectory.append(point)
        self.last_valid_position = point
        self.missing_frames = 0

    def _record_missing_detection(self) -> None:
        """记录一次"未检测到球"：缺失计数 +1；超过上限则清空最后有效位置（避免用陈旧点做预测）。"""
        self.missing_frames += 1
        if self.missing_frames > self.config.max_missing_frames:
            self.last_valid_position = None

    @staticmethod
    def _distance(point_a: Point2D, point_b: Point2D) -> float:
        """两点之间的欧氏距离（像素）。"""
        return float(hypot(point_a[0] - point_b[0], point_a[1] - point_b[1]))

    @staticmethod
    def _sample(**kwargs: object) -> BallFrameSample:
        """构造 BallFrameSample 的小工具：把可选的 diagnostics 单独取出组装。"""
        diagnostics = kwargs.pop("diagnostics", None) or {}
        return BallFrameSample(**kwargs, diagnostics=diagnostics)  # type: ignore[arg-type]
