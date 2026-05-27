"""动作分类预处理 —— 将比赛视频导出为目标球员连续帧训练样本。"""

from app.vision.action_classification_preprocessing.exporter import export_action_classification_dataset
from app.vision.action_classification_preprocessing.preprocessing import (
    apply_clahe_bgr,
    apply_light_denoise,
    build_clip_windows,
    crop_court_roi,
    crop_player,
    expand_box,
    sample_frame_indices,
)
from app.vision.action_classification_preprocessing.schemas import (
    ActionPreprocessingConfig,
    ActionPreprocessingError,
    CLAHEConfig,
    DenoiseConfig,
    ROIConfig,
)
from app.vision.action_classification_preprocessing.selection import select_target_detection

__all__ = [
    "ActionPreprocessingConfig",
    "ActionPreprocessingError",
    "CLAHEConfig",
    "DenoiseConfig",
    "ROIConfig",
    "apply_clahe_bgr",
    "apply_light_denoise",
    "build_clip_windows",
    "crop_court_roi",
    "crop_player",
    "expand_box",
    "export_action_classification_dataset",
    "sample_frame_indices",
    "select_target_detection",
]
