"""CrossViewGuidance + CrossViewGuidancePolicy。

强 guidance 仅对 `confirmed AND cross_view_anchored` 的 global player 生成(design D6/D7)。
guidance 只提供 ROI 搜索先验,不直接制造 observation(invariant 3)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.vision.multiview.court_frame import CourtOrientation, canonical_to_local
from app.vision.multiview.global_state import GlobalPlayerState


@dataclass
class CrossViewGuidancePolicy:
    """guidance 触发语义(参数值留实验调,语义冻结)。"""

    min_global_confidence: float = 0.6
    max_uncertainty_ft: float = 8.0
    missing_after_ms: float = 300.0      # binding 超过该 gap 视为 weak
    lost_after_ms: float = 1000.0        # binding 超过该 gap 视为 lost
    guidance_cooldown_ticks: int = 3
    max_regions_per_view_per_tick: int = 4
    base_roi_margin_px: float = 40.0
    uncertainty_to_px_scale: float = 12.0
    max_roi_margin_px: float = 160.0


@dataclass
class CrossViewGuidance:
    """一次跨视角搜索先验。"""

    global_player_id: str
    target_view: str
    predicted_canonical_position: tuple[float, float]
    uncertainty_ft: float
    predicted_local_position: tuple[float, float]
    expected_image_position: tuple[float, float]
    roi: tuple[float, float, float, float]  # (x1, y1, x2, y2) 目标视角图像空间
    confidence: float
    expires_at: float


class GuidanceGenerator:
    """按 policy 为 confirmed + anchored 的 global 生成 guidance。"""

    def __init__(self, policy: CrossViewGuidancePolicy | None = None) -> None:
        self.policy = policy or CrossViewGuidancePolicy()
        self._last_generated: dict[tuple[str, str], int] = {}  # (global, view) -> tick

    def generate(
        self,
        *,
        global_state: GlobalPlayerState,
        target_view: str,
        orientation: CourtOrientation,
        inverse_homography: Any,
        now_take_ms: float,
        tick: int,
        frame_width: int,
        frame_height: int,
        prediction: tuple[float, float, float] | None,
    ) -> CrossViewGuidance | None:
        """对单个 confirmed+anchored global 生成 guidance;不满足条件返回 None。"""
        p = self.policy
        if global_state.lifecycle != "confirmed" or not global_state.cross_view_anchored:
            return None
        if prediction is None:
            return None
        px, py, uncertainty = prediction
        if uncertainty > p.max_uncertainty_ft:
            return None

        binding = global_state.view_bindings.get(target_view)
        # 触发条件:目标视角 binding weak/missing/lost
        if binding is None or binding.visibility not in {"weak", "missing", "lost"}:
            return None
        # cooldown
        key = (global_state.global_player_id, target_view)
        last_tick = self._last_generated.get(key, -10**9)
        if tick - last_tick < p.guidance_cooldown_ticks:
            return None

        # canonical → local → image
        lx, ly = canonical_to_local(px, py, orientation)
        ix, iy = court_to_image_single((lx, ly), inverse_homography)
        # ROI:由 uncertainty 决定像素半径
        r_px = min(p.base_roi_margin_px + uncertainty * p.uncertainty_to_px_scale, p.max_roi_margin_px)
        x1 = max(0.0, ix - r_px)
        y1 = max(0.0, iy - r_px)
        x2 = min(float(frame_width), ix + r_px)
        y2 = min(float(frame_height), iy + r_px)

        self._last_generated[key] = tick
        return CrossViewGuidance(
            global_player_id=global_state.global_player_id,
            target_view=target_view,
            predicted_canonical_position=(px, py),
            uncertainty_ft=uncertainty,
            predicted_local_position=(lx, ly),
            expected_image_position=(ix, iy),
            roi=(x1, y1, x2, y2),
            confidence=max(0.0, 1.0 - uncertainty / p.max_uncertainty_ft),
            expires_at=now_take_ms + 50.0,
        )

    def generate_for_view(
        self,
        *,
        registry,
        target_view: str,
        orientation: CourtOrientation,
        inverse_homography: Any,
        now_take_ms: float,
        tick: int,
        frame_width: int,
        frame_height: int,
        predictions: dict[str, tuple[float, float, float]],
    ) -> list[CrossViewGuidance]:
        """为目标视角生成全部符合条件的 guidance(受 max_regions_per_view_per_tick 限制)。"""
        out: list[CrossViewGuidance] = []
        for gid, state in registry.players.items():
            pred = predictions.get(gid)
            if pred is None:
                continue
            g = self.generate(
                global_state=state,
                target_view=target_view,
                orientation=orientation,
                inverse_homography=inverse_homography,
                now_take_ms=now_take_ms,
                tick=tick,
                frame_width=frame_width,
                frame_height=frame_height,
                prediction=pred,
            )
            if g is not None:
                out.append(g)
            if len(out) >= self.policy.max_regions_per_view_per_tick:
                break
        return out


def court_to_image_single(point: tuple[float, float], inverse_homography: Any) -> tuple[float, float]:
    """把球场坐标投影到图像空间(复用 court_to_image,需传 H^-1)。"""
    from app.vision.courtvision_calibration_engine.homography import court_to_image

    result = court_to_image(point, inverse_homography)
    if isinstance(result, tuple):
        return float(result[0]), float(result[1])
    row = result[0]
    return float(row[0]), float(row[1])


def invert_homography(homography: list[list[float]]) -> np.ndarray:
    """H^-1(球场→图像方向)。"""
    return np.linalg.inv(np.asarray(homography, dtype=float))
