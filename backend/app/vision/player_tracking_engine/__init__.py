"""球员跟踪引擎 —— 人体检测、多目标跟踪、脚点估计、身份管理和投影。"""

from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator, estimate_footpoint
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector, PersonDetector
from app.vision.player_tracking_engine.player_projector import PlayerProjector, project_track_points
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector, PrimaryPlayerSelection
from app.vision.player_tracking_engine.player_lock_manager import PlayerLockManager
from app.vision.player_tracking_engine.player_lock_types import PlayerLockConfig, PlayerLockUpdate, PlayerSlot

__all__ = [
    "EmptyPersonDetector",
    "FootpointEstimator",
    "MultiObjectTracker",
    "PersonDetector",
    "PlayerProjector",
    "PrimaryPlayerSelection",
    "PrimaryPlayerSelector",
    "PlayerLockManager",
    "PlayerLockConfig",
    "PlayerLockUpdate",
    "PlayerSlot",
    "estimate_footpoint",
    "project_track_points",
]
