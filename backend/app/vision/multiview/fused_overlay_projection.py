"""fused overlay 的 canonical→target-image 纯投影 helper（只读复用 guidance 链）。

把 Global Player 的 canonical 球场位置重新投影到某个 target view 的图像空间，
得到图像 footpoint。**不返回数值误差边界**（当前没有 calibration covariance
支撑该承诺）；只返回投影是否有效与失败原因。

复用 `guidance.py` 已有的 `canonical_to_local + court_to_image_single` 链，
**不修改 guidance 现有语义**，只做只读消费。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.vision.multiview.court_frame import canonical_to_local
from app.vision.multiview.guidance import court_to_image_single

# 图像空间安全边距（px）：投影点落在画面内且离边缘足够远才认为几何有效
_MIN_IMAGE_MARGIN_PX = 8.0


@dataclass(frozen=True)
class TargetImageProjection:
    """canonical → target image 的投影结果。"""

    image_footpoint: tuple[float, float]
    projection_valid: bool
    failure_reason: str | None = None


def canonical_to_target_image(
    *,
    canonical_position: tuple[float, float],
    orientation: Any,
    inverse_homography: Any,
    frame_width: int,
    frame_height: int,
) -> TargetImageProjection:
    """把 canonical 位置投影到 target view 图像空间。

    返回 `(image_footpoint, projection_valid, failure_reason)`：
    - 未声明 orientation / homography 缺失 → invalid；
    - 投影点超出图像边界（含安全边距）→ invalid；
    - 其余情况返回图像 footpoint。
    """
    if orientation is None:
        return TargetImageProjection((0.0, 0.0), False, "missing_orientation")
    if inverse_homography is None:
        return TargetImageProjection((0.0, 0.0), False, "missing_inverse_homography")
    try:
        local_x, local_y = canonical_to_local(
            float(canonical_position[0]),
            float(canonical_position[1]),
            orientation,
        )
        image_x, image_y = court_to_image_single((local_x, local_y), inverse_homography)
    except Exception as exc:  # noqa: BLE001 - 投影失败归类为 invalid，不中断 builder
        return TargetImageProjection((0.0, 0.0), False, f"projection_error:{type(exc).__name__}")
    if not frame_width or not frame_height:
        return TargetImageProjection((0.0, 0.0), False, "missing_frame_geometry")
    margin = _MIN_IMAGE_MARGIN_PX
    if (
        image_x < margin
        or image_y < margin
        or image_x > frame_width - margin
        or image_y > frame_height - margin
    ):
        return TargetImageProjection(
            (float(image_x), float(image_y)),
            False,
            "projection_outside_frame",
        )
    return TargetImageProjection((float(image_x), float(image_y)), True, None)
