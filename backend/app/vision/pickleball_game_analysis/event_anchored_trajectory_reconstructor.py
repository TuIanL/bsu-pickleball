"""事件锚定的 2.5D 视觉重建（event_anchored_trajectory_reconstructor）。

在图像空间完成观测拟合（测量模型），再以可信事件锚点重建球场展示轨迹
（展示模型）。核心算法（设计 S3，五步）：

  1. 图像空间鲁棒拟合 u(t)、v(t)；
  2. 拟合点经 homography 生成 pseudo-ground path（中间量）；
  3. 以锚点建立主轴，分解为纵向进度与横向残差；
  4. 纵向进度施加单调性约束（isotonic），消除段内折返；
  5. 横向残差鲁棒平滑、幅度限制、端点归零。

高度模型按段类型设置边界（D/S），不把段端统一置零：
  - bounce 边界 z 严格为 0；
  - hit / serve 边界 z = 接触高度先验（低可信）；
  - loss / unknown 边界不强制落到地面，末端置信度渐隐。

锚点数量降级：dual_anchor_warp / single_anchor_warp / image_only / local_visual_arc。
"""

from __future__ import annotations

from math import hypot, isfinite, pi, sin

import numpy as np

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.courtvision_calibration_engine.homography import HomographyError, image_to_court
from app.vision.pickleball_game_analysis.image_space_trajectory_fitter import (
    FitConfig,
    ImageSpaceTrajectoryFitter,
)
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    AnchorType,
    ReconstructedSample,
    ReconstructedSegment,
    ReconstructionConfig,
    ReconstructionMode,
    SampleSource,
    SpatialAnchor,
    TrajectoryEvent,
    TrajectoryEventType,
)
from app.vision.pickleball_game_analysis.schemas import Point2D, TrajectoryPoint


class EventAnchoredTrajectoryReconstructor:
    """把单个飞行段重建为带高度与球场坐标的采样序列。"""

    def __init__(
        self,
        config: ReconstructionConfig | None = None,
        court: PickleballCourtGeometry | None = None,
    ) -> None:
        self.config = config or ReconstructionConfig()
        self.court = court or standard_court()
        self.fitter = ImageSpaceTrajectoryFitter(FitConfig())

    def reconstruct(
        self,
        segment,
        points: list[TrajectoryPoint],
        events_by_id: dict[str, TrajectoryEvent],
        homography: list[list[float]] | None,
    ) -> ReconstructedSegment:
        """重建一个飞行段。"""
        seg_points = [points[i] for i in segment.point_indices]
        valid = [i for i, p in enumerate(seg_points) if self._valid_xy(p.image_xy)]
        if len(valid) < 3:
            return self._empty_segment(segment)

        # 1) 图像空间拟合（测量模型）
        fit = self.fitter.fit(seg_points)

        # 2) 锚点推导
        start_anchor = self._derive_anchor(
            segment, start=True, event=events_by_id.get(segment.start_event_id or ""), homography=homography
        )
        end_anchor = self._derive_anchor(
            segment, start=False, event=events_by_id.get(segment.end_event_id or ""), homography=homography
        )
        start_anchor, end_anchor = self._resolve_anchor_conflict(start_anchor, end_anchor, segment, events_by_id)

        # 3) 重建模式
        mode = self._reconstruction_mode(start_anchor, end_anchor)

        # 4) 生成球场路径（含锚点校正）
        court_path, status = self._build_court_path(mode, seg_points, fit, start_anchor, end_anchor, homography)

        # 5) 高度模型（image_only 不做空间重建，也不伪造高度）
        z0, z1, height_sources = self._height_boundaries(start_anchor, end_anchor)
        if mode == ReconstructionMode.IMAGE_ONLY:
            z0 = z1 = None
            height_sources = (None, None)

        # 6) 采样点
        samples = self._build_samples(
            seg_points,
            fit,
            court_path,
            z0,
            z1,
            height_sources,
            start_anchor,
            end_anchor,
            segment,
        )

        return ReconstructedSegment(
            segment_id=segment.segment_id,
            reconstruction_mode=mode.value,
            status=status,
            start_event_id=segment.start_event_id,
            end_event_id=segment.end_event_id,
            start_event_type=segment.start_event_type.value if segment.start_event_type else None,
            end_event_type=segment.end_event_type.value if segment.end_event_type else None,
            boundary_reason=segment.boundary_reason,
            fit_space="image_px",
            model="weighted_huber_anchor_constrained",
            anchors=self._anchor_payloads(start_anchor, end_anchor),
            samples=samples,
        )

    # ---- 锚点推导 ----

    def _derive_anchor(
        self,
        segment,
        *,
        start: bool,
        event: TrajectoryEvent | None,
        homography: list[list[float]] | None,
    ) -> SpatialAnchor | None:
        """从段起止事件推导空间锚点；不可作锚点的边界返回 None。"""
        if event is None:
            return None
        anchor_type: AnchorType | None = None
        height_ft: float | None = None
        uncertainty = 0.0

        if event.event_type == TrajectoryEventType.BOUNCE:
            anchor_type = AnchorType.BOUNCE
            height_ft = 0.0
            uncertainty = 0.3
        elif event.event_type in (
            TrajectoryEventType.HIT,
            TrajectoryEventType.SERVE_RESET,
        ):
            anchor_type = AnchorType.CONTACT
            height_ft = round(self.config.default_contact_height_ft, 3)
            uncertainty = self.config.contact_height_uncertainty_ft
        else:
            return None  # loss / end_of_stream 不是空间锚点

        # 球场坐标：优先用事件自带 court_xy（bounce 检测已投影），否则用 image_xy 经 homography 投影。
        # 弹地为硬锚点（z=0 单应精确），击球为软锚点（保留不确定度）。
        court_xy = event.court_xy if event.court_xy is not None else None
        if court_xy is None and event.image_xy is not None and homography is not None:
            court_xy = self._project(event.image_xy, homography)
        return SpatialAnchor(
            anchor_id=f"anchor-{event.event_id}",
            anchor_type=anchor_type,
            frame_index=event.frame_index,
            timestamp_sec=event.timestamp_sec,
            image_xy=event.image_xy,
            court_xy=court_xy,
            height_ft=height_ft,
            confidence=event.confidence if anchor_type == AnchorType.BOUNCE else min(0.5, event.confidence),
            uncertainty_ft=uncertainty,
            event_id=event.event_id,
        )

    def _resolve_anchor_conflict(self, start, end, segment, events_by_id):
        """同帧锚点冲突（如 hit 与 bounce 在同一帧）时，优先 bounce 硬锚点。"""
        if start is None or end is None:
            return start, end
        if start.frame_index == end.frame_index and start.anchor_type != end.anchor_type:
            if start.anchor_type == AnchorType.BOUNCE:
                return start, None
            if end.anchor_type == AnchorType.BOUNCE:
                return None, end
        return start, end

    # ---- 重建模式 ----

    def _reconstruction_mode(
        self,
        start: SpatialAnchor | None,
        end: SpatialAnchor | None,
    ) -> ReconstructionMode:
        usable = [a for a in (start, end) if a is not None and a.court_xy is not None]
        if len(usable) == 2:
            dist = hypot(
                usable[0].court_xy[0] - usable[1].court_xy[0],
                usable[0].court_xy[1] - usable[1].court_xy[1],
            )
            if dist < self.config.minimum_anchor_distance_ft:
                return ReconstructionMode.LOCAL_VISUAL_ARC
            return ReconstructionMode.DUAL_ANCHOR_WARP
        if len(usable) == 1:
            return ReconstructionMode.SINGLE_ANCHOR_WARP
        return ReconstructionMode.IMAGE_ONLY

    # ---- 球场路径构建 ----

    def _build_court_path(self, mode, points, fit, start, end, homography):
        """生成校正后的球场路径数组（与 points 等长），以及状态标签。"""
        n = len(points)
        if mode == ReconstructionMode.IMAGE_ONLY or not fit.converged:
            # 仅保留原始观测的伪球场点（raw evidence），状态标记不足锚点
            court = np.full((n, 2), np.nan)
            for i, point in enumerate(points):
                if self._valid_xy(point.image_xy) and homography is not None:
                    court[i] = self._project(point.image_xy, homography)
            return court, "insufficient_spatial_anchors"

        # 对每个点的时刻评估图像拟合曲线
        timestamps = [p.timestamp_sec for p in points]
        _, u_arr, v_arr = self.fitter.evaluate(fit, timestamps)
        pseudo = np.full((n, 2), np.nan)
        for i in range(n):
            if homography is not None:
                projected = self._project((float(u_arr[i]), float(v_arr[i])), homography)
                if projected is not None:
                    pseudo[i] = projected

        if mode == ReconstructionMode.SINGLE_ANCHOR_WARP:
            anchor = start if start is not None and start.court_xy is not None else end
            return self._single_anchor_warp(pseudo, anchor, points), "reconstructed"

        if mode == ReconstructionMode.LOCAL_VISUAL_ARC:
            return self._local_visual_arc(pseudo, start, end), "reconstructed"

        # dual
        return self._dual_anchor_warp(pseudo, start, end), "reconstructed"

    def _dual_anchor_warp(self, pseudo: np.ndarray, start, end) -> np.ndarray:
        """双锚点：单调纵向 + 有界横向 + 端点归零。"""
        a0 = np.asarray(start.court_xy, dtype=np.float64)
        a1 = np.asarray(end.court_xy, dtype=np.float64)
        axis = a1 - a0
        length = float(np.linalg.norm(axis))
        if length <= 1e-6:
            out = np.tile(a0, (len(pseudo), 1))
            return out
        unit = axis / length

        out = np.full((len(pseudo), 2), np.nan)
        s_raw: list[float] = []
        lat_raw: list[tuple[float, float]] = []
        for i in range(len(pseudo)):
            if not np.isfinite(pseudo[i]).all():
                s_raw.append(np.nan)
                lat_raw.append((np.nan, np.nan))
                continue
            d = pseudo[i] - a0
            s_raw.append(float(np.dot(d, unit) / length))
            lat_raw.append((d - s_raw[-1] * length * unit).tolist())

        # 单调性约束（isotonic 非降）→ 重归一化到 [0,1]
        s_mono = self._isotonic_increasing(np.asarray(s_raw, dtype=np.float64))
        finite_mask = np.isfinite(s_mono)
        s0 = s_mono[finite_mask][0] if finite_mask.any() else 0.0
        s1 = s_mono[finite_mask][-1] if finite_mask.any() else 1.0
        denom = (s1 - s0) or 1.0
        s_norm = (s_mono - s0) / denom

        # 横向残差：平滑 + 幅度限制 + 端点 taper
        lat = np.array(lat_raw, dtype=np.float64)
        lat_smooth = self._moving_average(lat, self.config.lateral_smooth_window)
        for i in range(len(pseudo)):
            if not np.isfinite(lat_smooth[i]).all():
                continue
            norm = float(np.linalg.norm(lat_smooth[i]))
            if norm > self.config.max_lateral_residual_ft:
                lat_smooth[i] = lat_smooth[i] * (self.config.max_lateral_residual_ft / norm)
        # 端点 taper：sin(pi*p) 两端为 0
        for i in range(len(pseudo)):
            if np.isnan(s_norm[i]):
                continue
            p = min(1.0, max(0.0, float(s_norm[i])))
            taper = sin(pi * max(1e-4, min(1 - 1e-4, p)))
            lat_smooth[i] = lat_smooth[i] * taper
            out[i] = a0 + s_norm[i] * axis + lat_smooth[i]
        return out

    def _single_anchor_warp(self, pseudo: np.ndarray, anchor, points) -> np.ndarray:
        """单锚点：锚点端严格对齐，另一端用 pseudo path 相对位移。"""
        a0 = np.asarray(anchor.court_xy, dtype=np.float64)
        out = np.full((len(pseudo), 2), np.nan)
        ref = None
        for i in range(len(pseudo)):
            if np.isfinite(pseudo[i]).all():
                ref = pseudo[i]
                break
        if ref is None:
            return out
        offset = a0 - ref
        lat = self._moving_average(pseudo + offset, self.config.lateral_smooth_window)
        for i in range(len(pseudo)):
            if np.isfinite(lat[i]).all():
                out[i] = lat[i]
        return out

    def _local_visual_arc(self, pseudo, start, end):
        """锚点距离过小：退化为以锚点为基准的局部视觉弧。"""
        anchor = start if start is not None and start.court_xy is not None else end
        n = len(pseudo)
        out = np.full((n, 2), np.nan)
        if anchor is None or anchor.court_xy is None:
            return out
        a = np.asarray(anchor.court_xy, dtype=np.float64)
        for i in range(n):
            if np.isfinite(pseudo[i]).all():
                out[i] = a
        return out

    # ---- 高度模型 ----

    def _height_boundaries(self, start, end):
        """返回 (z0, z1, height_sources)：段端高度（英尺）与来源标签。"""
        z0 = start.height_ft if start is not None else None
        z1 = end.height_ft if end is not None else None
        src0 = self._height_source(start)
        src1 = self._height_source(end)
        return z0, z1, (src0, src1)

    @staticmethod
    def _height_source(anchor: SpatialAnchor | None) -> str | None:
        if anchor is None:
            return None
        if anchor.anchor_type == AnchorType.BOUNCE:
            return "bounce"
        if anchor.anchor_type == AnchorType.CONTACT:
            return "global_contact_prior"
        return None

    def _height_at(self, p: float, z0: float | None, z1: float | None, peak: float) -> float | None:
        """在归一化进度 p 处计算高度；未知端不强制落地面。"""
        if z0 is None and z1 is None:
            return None
        if z0 is None:
            z0 = z1
        if z1 is None:
            # 只知起点：向峰值平滑上升并保持（末端渐隐由 height_confidence 表达）
            sp = p * p * (3.0 - 2.0 * p)  # smoothstep
            return z0 + (peak - z0) * sp
        a_coef = 4.0 * (peak - (z0 + z1) / 2.0)
        return z0 * (1.0 - p) + z1 * p + a_coef * p * (1.0 - p)

    # ---- 采样 ----

    def _build_samples(self, points, fit, court_path, z0, z1, height_sources, start, end, segment):
        samples: list[ReconstructedSample] = []
        n = len(points)
        # 段端是否有未知高度
        end_unknown = z1 is None

        # 弧线峰值：基于时长与平面距离的估算
        t0 = points[0].timestamp_sec
        t1 = points[-1].timestamp_sec
        duration = max(0.0, t1 - t0)
        dist = 0.0
        if len(court_path) >= 2:
            first_ok = next((court_path[i] for i in range(n) if np.isfinite(court_path[i]).all()), None)
            last_ok = next((court_path[i] for i in range(n - 1, -1, -1) if np.isfinite(court_path[i]).all()), None)
            if first_ok is not None and last_ok is not None:
                dist = float(np.linalg.norm(last_ok - first_ok))
        peak = max(2.4 + dist * 0.12 + duration * 0.65, 2.4, z0 or 0.0, z1 or 0.0)
        peak = min(peak, 8.5)

        consecutive_missing = 0
        for i, point in enumerate(points):
            p = (duration and (point.timestamp_sec - t0) / duration) or (i / max(1, n - 1))
            p = min(1.0, max(0.0, p))

            # 来源分类
            source = SampleSource.MODEL_PREDICTED.value
            confidence: float | None = None
            gap_length: int | None = None
            reproj: float | None = None

            if self._valid_xy(point.image_xy):
                consecutive_missing = 0
                if point.interpolated or point.source == "interpolated":
                    source = SampleSource.INTERPOLATED.value
                else:
                    source = SampleSource.DETECTED.value
                    confidence = point.confidence
                    if fit.converged:
                        _, u, v = self.fitter.evaluate(fit, [point.timestamp_sec])
                        reproj = round(float(hypot(point.image_xy[0] - u[0], point.image_xy[1] - v[0])), 2)
            else:
                consecutive_missing += 1
                gap_length = consecutive_missing
                source = SampleSource.MODEL_PREDICTED.value

            # 锚点帧标记
            if start is not None and point.frame_index == start.frame_index:
                source = SampleSource.ANCHOR.value
                confidence = start.confidence
            if end is not None and point.frame_index == end.frame_index:
                source = SampleSource.ANCHOR.value
                confidence = end.confidence

            # 球场坐标
            court_xy = None
            if np.isfinite(court_path[i]).all():
                court_xy = (round(float(court_path[i][0]), 4), round(float(court_path[i][1]), 4))

            # 高度
            height_ft = self._height_at(p, z0, z1, peak)
            height_conf: float | None = 1.0
            height_src: str | None = "estimated"
            if height_ft is None:
                height_conf = None
                height_src = None
            elif end_unknown and p > 0.6:
                # 未知端渐隐
                height_conf = max(0.0, 1.0 - (p - 0.6) / 0.4)
            if start is not None and point.frame_index == start.frame_index:
                height_src = height_sources[0]
            if end is not None and point.frame_index == end.frame_index:
                height_src = height_sources[1]

            samples.append(
                ReconstructedSample(
                    frame_index=point.frame_index,
                    timestamp_sec=round(point.timestamp_sec, 6),
                    court_xy=court_xy,
                    estimated_height_ft=round(height_ft, 3) if height_ft is not None else None,
                    source=source,
                    confidence=confidence,
                    height_source=height_src,
                    height_confidence=round(height_conf, 3) if height_conf is not None else None,
                    height_uncertainty_ft=(
                        round(self.config.contact_height_uncertainty_ft, 3) if height_ft is not None else None
                    ),
                    gap_length_frames=gap_length,
                    reprojection_error_px=reproj,
                )
            )
        return samples

    def _anchor_payloads(self, start, end) -> list[dict]:
        payloads = []
        for anchor in (start, end):
            if anchor is None:
                continue
            payloads.append(
                {
                    "anchor_id": anchor.anchor_id,
                    "anchor_type": anchor.anchor_type.value,
                    "frame_index": int(anchor.frame_index),
                    "court_xy": (
                        [round(anchor.court_xy[0], 4), round(anchor.court_xy[1], 4)]
                        if anchor.court_xy is not None
                        else None
                    ),
                    "height_ft": round(anchor.height_ft, 3) if anchor.height_ft is not None else None,
                    "confidence": round(anchor.confidence, 3),
                    "uncertainty_ft": round(anchor.uncertainty_ft, 3),
                }
            )
        return payloads

    # ---- 工具 ----

    @staticmethod
    def _valid_xy(xy: Point2D | None) -> bool:
        return xy is not None and isfinite(xy[0]) and isfinite(xy[1])

    @staticmethod
    def _project(image_xy, homography) -> tuple[float, float] | None:
        try:
            result = image_to_court(image_xy, homography)
            x, y = result[0] if isinstance(result, list) else result
            if isfinite(x) and isfinite(y):
                return (float(x), float(y))
        except (HomographyError, ValueError, TypeError, IndexError):
            pass
        return None

    @staticmethod
    def _moving_average(arr: np.ndarray, window: int) -> np.ndarray:
        """对 (n,2) 数组逐列做滑动平均；窗口为奇数时中心对齐。"""
        if arr.ndim != 2 or window < 1:
            return arr.copy()
        out = np.full(arr.shape, np.nan)
        half = window // 2
        for i in range(len(arr)):
            lo = max(0, i - half)
            hi = min(len(arr), i + half + 1)
            window_arr = arr[lo:hi]
            if not np.isfinite(window_arr).all():
                continue
            out[i] = np.nanmean(window_arr, axis=0)
        return out

    @staticmethod
    def _isotonic_increasing(y: np.ndarray) -> np.ndarray:
        """PAVA（合并相邻逆序块）非降 isotonic 拟合，确定性、无随机。"""
        n = y.size
        out = np.empty(n)
        if n == 0:
            return out
        if n == 1:
            out[0] = y[0]
            return out
        block_val: list[float] = []
        block_cnt: list[int] = []
        for i in range(n):
            if not np.isfinite(y[i]):
                continue
            block_val.append(float(y[i]))
            block_cnt.append(1)
            while len(block_val) >= 2 and block_val[-1] < block_val[-2]:
                total_cnt = block_cnt[-1] + block_cnt[-2]
                merged = (block_val[-1] * block_cnt[-1] + block_val[-2] * block_cnt[-2]) / total_cnt
                block_val.pop()
                block_cnt.pop()
                block_val.pop()
                block_cnt.pop()
                block_val.append(merged)
                block_cnt.append(total_cnt)
        idx = 0
        for val, cnt in zip(block_val, block_cnt, strict=False):
            for _ in range(cnt):
                if idx < n:
                    out[idx] = val
                idx += 1
        return out

    def _empty_segment(self, segment) -> ReconstructedSegment:
        return ReconstructedSegment(
            segment_id=segment.segment_id,
            reconstruction_mode=ReconstructionMode.IMAGE_ONLY.value,
            status="insufficient_spatial_anchors",
            start_event_id=segment.start_event_id,
            end_event_id=segment.end_event_id,
            start_event_type=segment.start_event_type.value if segment.start_event_type else None,
            end_event_type=segment.end_event_type.value if segment.end_event_type else None,
            boundary_reason=segment.boundary_reason,
            fit_space="image_px",
            model="weighted_huber_anchor_constrained",
            anchors=[],
            samples=[],
        )
