"""球员跟踪引擎 —— 人体检测、多目标跟踪、脚点估计、身份管理和投影。"""

# 对外导出本引擎的核心类与工具函数，供上游（分析流水线）直接 import。
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator, estimate_footpoint
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector, PersonDetector
from app.vision.player_tracking_engine.player_projector import PlayerProjector, project_track_points
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector, PrimaryPlayerSelection

# 显式声明公开符号，控制 `from ... import *` 的可见范围。
__all__ = [
    "EmptyPersonDetector",
    "FootpointEstimator",
    "MultiObjectTracker",
    "PersonDetector",
    "PlayerProjector",
    "PrimaryPlayerSelection",
    "PrimaryPlayerSelector",
    "estimate_footpoint",
    "project_track_points",
]
