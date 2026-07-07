"""球轨迹与弹跳点核心引擎（pickleball_game_analysis 模块入口）。

本模块是"球分析"的算法实现集合，负责从视频帧里找出球、跟踪其轨迹、清洗轨迹、
并把弹跳点检测出来，最终产出可供前端叠加/展示的 JSON 产物。

主要组成：
  - schemas.py           ：球相关的数据模型（候选、采样、轨迹点、弹跳事件）与 JSON 辅助；
  - ball_detector_protocol.py：球检测器的接口约定（Protocol），便于替换底层模型；
  - ball_tracker.py      ：逐帧过滤候选 + 轨迹连续性跟踪 + 投影到球场坐标；
  - trajectory_cleaner.py：轨迹异常点去除 + 短缺口线性插值；
  - bounce_detector.py   ：基于清洗后轨迹的"弹跳点"规则检测；
  - court_adapter.py     ：把图像坐标投影到英尺制球场坐标；
  - detection_writer.py  ：把各类结果写成 JSON 文件（原始轨迹 / 清洗轨迹 / 弹跳 / overlay）。
"""

from app.vision.pickleball_game_analysis.ball_detector_protocol import BallDetectorProtocol
from app.vision.pickleball_game_analysis.ball_tracker import BallTracker, BallTrackerConfig
from app.vision.pickleball_game_analysis.bounce_detector import BounceDetector, BounceDetectorConfig
from app.vision.pickleball_game_analysis.court_adapter import BallCourtAdapter, CourtProjection
from app.vision.pickleball_game_analysis.minimap_visualizer import MinimapVisualizer
from app.vision.pickleball_game_analysis.overlay_video_writer import OverlayVideoWriter
from app.vision.pickleball_game_analysis.position_visualizer import PositionVisualizer
from app.vision.pickleball_game_analysis.schemas import (
    BallCandidate,
    BallFrameSample,
    BounceEvent,
    TrajectoryPoint,
)
from app.vision.pickleball_game_analysis.trajectory_cleaner import TrajectoryCleaner, TrajectoryCleanerConfig

# __all__：本模块对外公开的名字（from app.vision.pickleball_game_analysis import * 时只导出这些）
__all__ = [
    "BallCandidate",
    "BallCourtAdapter",
    "BallDetectorProtocol",
    "BallFrameSample",
    "BallTracker",
    "BallTrackerConfig",
    "BounceDetector",
    "BounceDetectorConfig",
    "BounceEvent",
    "CourtProjection",
    "MinimapVisualizer",
    "OverlayVideoWriter",
    "PositionVisualizer",
    "TrajectoryCleaner",
    "TrajectoryCleanerConfig",
    "TrajectoryPoint",
]
