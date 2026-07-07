"""脚点估计器 —— 从检测框底部中点推算球员在图像中的脚部位置。"""

from __future__ import annotations

# BoundingBox：图像空间检测框；FootpointEstimate：脚点估计结果（含方法与像素坐标）；
# FootpointMethod：脚点估计方法枚举（字符串）；Track：带轨迹身份的检测框。
from app.schemas.tracking import BoundingBox, FootpointEstimate, FootpointMethod, Track


class FootpointEstimator:
    """Estimate image-space player footpoints from tracked person boxes."""

    def __init__(self, method: FootpointMethod = "bbox_bottom_center") -> None:
        # 记录使用的脚点估计方法，当前仅支持 bbox_bottom_center（检测框底边中点）。
        self.method = method

    def estimate(self, bbox_or_track: BoundingBox | Track | list[float] | tuple[float, float, float, float]) -> FootpointEstimate:
        # 目前只实现“检测框底边中点”一种方法，其他方法直接抛 NotImplementedError。
        if self.method != "bbox_bottom_center":
            raise NotImplementedError(f"Footpoint method is not implemented yet: {self.method}")

        # 取出 (x1, y1, x2, y2)，脚点即底边中点 (x1+x2)/2, y2。
        x1, _, x2, y2 = _bbox_values(bbox_or_track)
        return FootpointEstimate(
            image_footpoint=[float(x1 + x2) / 2.0, float(y2)],
            method=self.method,
        )


def estimate_footpoint(bbox: BoundingBox | list[float] | tuple[float, float, float, float]) -> tuple[float, float]:
    """Compatibility wrapper returning the bbox bottom-center tuple."""

    # 便捷函数：直接返回 (x, y) 元组，便于不需要 FootpointEstimate 包装的场景。
    estimate = FootpointEstimator().estimate(bbox)
    return (estimate.image_footpoint[0], estimate.image_footpoint[1])


def _bbox_values(bbox_or_track: BoundingBox | Track | list[float] | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    # 把多种输入形态（Track / BoundingBox / 四元组）统一拆成 (x1, y1, x2, y2) 浮点元组。
    if isinstance(bbox_or_track, Track):
        x1, y1, x2, y2 = bbox_or_track.bbox
    elif isinstance(bbox_or_track, BoundingBox):
        x1, y1, x2, y2 = bbox_or_track.x1, bbox_or_track.y1, bbox_or_track.x2, bbox_or_track.y2
    else:
        x1, y1, x2, y2 = bbox_or_track
    return (float(x1), float(y1), float(x2), float(y2))
