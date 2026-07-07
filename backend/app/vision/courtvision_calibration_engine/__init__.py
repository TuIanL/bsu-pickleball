"""
CourtVision 标定引擎（courtvision_calibration_engine）。

这个子包负责"球场标定"的核心能力：
- 用标准匹克球场几何模型（court_geometry）描述真实球场；
- 计算"图像像素 ↔ 球场英尺坐标"之间的单应性矩阵（homography）；
- 把球场线投影回原始视频帧上做可视化叠加（court_overlay）；
- 支持自动标定：用 YOLO 分割球场线 → 掩码 → 提取四角 → 计算标定（coco_dataset / court_line_segmentation / mask_to_keypoints / reference_line_support）；
- 提供手工四角标定的引擎入口（manual_keypoint_calibrator）；
- 提供从真实视频抽帧、构建标定数据集的工具（real_video_frame_extraction）。

本文件（__init__.py）把最常用的球场几何类与单应性函数"再导出"一遍，
方便外部直接 `from app.vision.courtvision_calibration_engine import ...` 使用。
"""

# 标准球场几何：球场点/线/多边形/区域，以及标准 20×44 英尺球场对象
from app.vision.courtvision_calibration_engine.court_geometry import (
    PickleballCourtGeometry,
    StandardPickleballCourt,
    standard_court,
)
# 单应性计算与坐标变换：像素↔球场双向投影
from app.vision.courtvision_calibration_engine.homography import (
    compute_homography,
    court_to_image,
    image_to_court,
    project_point,
)

# __all__：声明本包对外公开的符号（别人 `from 包 import *` 时只导出这些）
__all__ = [
    "PickleballCourtGeometry",
    "StandardPickleballCourt",
    "compute_homography",
    "court_to_image",
    "image_to_court",
    "project_point",
    "standard_court",
]
