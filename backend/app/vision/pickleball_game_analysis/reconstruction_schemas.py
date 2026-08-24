"""事件切分球轨迹重建层的数据结构（reconstruction_schemas）。

本文件定义"重建层"在事件检测、段切分、锚点、重建采样之间传递的数据形状，
以及可配置的超参数。与 schemas.py 的跟踪/清洗层数据正交，不修改其逻辑。

坐标约定（与 schemas.py 一致）：
  - image（图像）：像素，原点左上；
  - court（球场）：英尺，原点球场一角（x 0→20，y 0→44，球网 y=22）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.vision.pickleball_game_analysis.schemas import Point2D

# 英尺 ↔ 米 换算常数（1 米 = 3.28084 英尺）
M_TO_FT = 3.28084


class TrajectoryEventType(StrEnum):
    """飞行段边界事件的类型。"""

    HIT = "hit"
    BOUNCE = "bounce"
    LOSS = "loss"
    SERVE_RESET = "serve_reset"
    END_OF_STREAM = "end_of_stream"


class EventSource(StrEnum):
    """事件来源（第一版只用 heuristic / bounce_detector / tracking / manual）。"""

    HEURISTIC = "heuristic"
    POSE_ASSISTED = "pose_assisted"  # 预留：后续接入手腕/球拍
    MANUAL_CORRECTED = "manual_corrected"  # 预留：人工修正
    BOUNCE_DETECTOR = "bounce_detector"
    TRACKING = "tracking"
    SERVE = "serve"


class AnchorType(StrEnum):
    """空间锚点类型（可信度分级）。"""

    BOUNCE = "bounce"  # 硬锚点：z=0，单应映射最可信
    CONTACT = "contact"  # 软锚点：击球点，保存不确定度
    RAW_ENDPOINT = "raw_endpoint"  # 弱约束：普通检测段端点
    LOSS = "loss"  # 非空间锚点：丢失边界


class ReconstructionMode(StrEnum):
    """球场空间重建模式（锚点数量降级）。"""

    DUAL_ANCHOR_WARP = "dual_anchor_warp"
    SINGLE_ANCHOR_WARP = "single_anchor_warp"
    IMAGE_ONLY = "image_only"
    LOCAL_VISUAL_ARC = "local_visual_arc"


class HybridReconstructionMode(StrEnum):
    """统一混合球路产物的段级重建模式。"""

    STEREO_ESTIMATED_3D = "stereo_estimated_3d"
    STEREO_ANCHORED_2_5D = "stereo_anchored_2_5d"
    SINGLE_VIEW_EVENT_ANCHORED_2_5D = "single_view_event_anchored_2_5d"
    SINGLE_VIEW_VISUAL_ARC = "single_view_visual_arc"
    UNAVAILABLE = "unavailable"


class SampleSource(StrEnum):
    """重建样本的来源分类。"""

    DETECTED = "detected"
    INTERPOLATED = "interpolated"
    MODEL_PREDICTED = "model_predicted"
    ANCHOR = "anchor"


class NetCrossingStatus(StrEnum):
    """过网状态软诊断取值。"""

    NOT_EXPECTED = "not_expected"
    EXPECTED = "expected"
    ESTIMATED = "estimated"
    IMPLAUSIBLE = "implausible"
    UNKNOWN = "unknown"


class OwnershipStatus(StrEnum):
    """击球归属状态（区分"是否为可信击球"与"能否确定击球者"）。"""

    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    UNASSIGNED = "unassigned"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class PlayerCandidateScore:
    """归属候选评分明细。"""

    player_id: str
    score: float


@dataclass(frozen=True)
class PlayerAttribution:
    """一次击球候选的球员归属结果。"""

    candidate_id: str
    status: str = OwnershipStatus.UNASSIGNED.value  # confirmed / ambiguous / unassigned
    player_id: str | None = None
    render_slot: str | None = None
    confidence: float = 0.0
    score_margin: float = 0.0
    attributed_frame_index: int | None = None
    method: str = "none"  # pose_bbox_fused / bbox_fused / serve_seeded / none
    candidate_scores: list[PlayerCandidateScore] = field(default_factory=list)


@dataclass(frozen=True)
class TrajectoryEvent:
    """一个飞行段边界事件（击球 / 弹地 / 丢失 / serve 重置 / 流结束）。

    `event_status` 与 `ownership_status` 严格分离：
      - event_status：这是不是一次可信击球；
      - ownership_status：即使是击球，能不能确定是哪名球员。
    """

    event_id: str
    event_type: TrajectoryEventType
    frame_index: int
    timestamp_sec: float
    image_xy: Point2D | None = None
    court_xy: Point2D | None = None
    confidence: float = 0.0
    source: str = EventSource.HEURISTIC.value
    diagnostics: dict = field(default_factory=dict)
    event_status: str = "confirmed"  # confirmed / ambiguous
    hitter_player_id: str | None = None
    hitter_render_slot: str | None = None
    ownership_status: str = OwnershipStatus.UNASSIGNED.value
    ownership_confidence: float | None = None
    ownership_source_event_id: str | None = None
    attribution: PlayerAttribution | None = None

    @property
    def is_anchor_capable(self) -> bool:
        """该事件是否可作为空间锚点（bounce 硬锚点、contact/serve 软锚点）。"""
        return self.event_type in (
            TrajectoryEventType.HIT,
            TrajectoryEventType.BOUNCE,
            TrajectoryEventType.SERVE_RESET,
        )


@dataclass(frozen=True)
class SpatialAnchor:
    """一个空间锚点：由段起止事件推导，带可信度与不确定度。"""

    anchor_id: str
    anchor_type: AnchorType
    frame_index: int
    timestamp_sec: float
    image_xy: Point2D | None = None
    court_xy: Point2D | None = None
    height_ft: float | None = None
    confidence: float = 0.0
    uncertainty_ft: float = 0.0
    event_id: str | None = None


@dataclass
class FlightSegment:
    """一个飞行段：两个事件边界之间的最小重建单位。

    语义上硬切段（击球/弹地/丢失等边界产生独立段），几何上相邻段可共享锚点。
    point_indices 指向 cleaned trajectory 中的下标（含 None 的缺失点）。
    归属字段由 BallShotAssembler 在重建后回填。
    """

    segment_id: str
    start_index: int
    end_index: int
    start_event_id: str | None = None
    end_event_id: str | None = None
    start_event_type: TrajectoryEventType | None = None
    end_event_type: TrajectoryEventType | None = None
    boundary_reason: str = ""
    start_anchor_id: str | None = None
    end_anchor_id: str | None = None
    point_indices: list[int] = field(default_factory=list)
    shot_id: str | None = None
    hitter_player_id: str | None = None
    hitter_render_slot: str | None = None
    ownership_status: str = OwnershipStatus.NOT_APPLICABLE.value
    ownership_confidence: float | None = None
    ownership_source_event_id: str | None = None


@dataclass(frozen=True)
class ReconstructedSample:
    """重建后的一个采样点（供 artifact 序列化）。"""

    frame_index: int
    timestamp_sec: float
    court_xy: Point2D | None
    estimated_height_ft: float | None
    source: str
    confidence: float | None
    height_source: str | None = None
    height_confidence: float | None = None
    height_uncertainty_ft: float | None = None
    gap_length_frames: int | None = None
    reprojection_error_px: float | None = None


@dataclass
class ReconstructedSegment:
    """一个飞行段的完整重建结果（含质量评分与采样点）。"""

    segment_id: str
    reconstruction_mode: str
    status: str = "reconstructed"  # reconstructed / insufficient_spatial_anchors
    start_event_id: str | None = None
    end_event_id: str | None = None
    start_event_type: str | None = None
    end_event_type: str | None = None
    boundary_reason: str = ""
    fit_space: str = "image_px"
    model: str = "weighted_huber_anchor_constrained"
    anchors: list[dict] = field(default_factory=list)
    quality: dict = field(default_factory=dict)
    samples: list[ReconstructedSample] = field(default_factory=list)
    shot_id: str | None = None
    hitter_player_id: str | None = None
    hitter_render_slot: str | None = None
    ownership_status: str = OwnershipStatus.NOT_APPLICABLE.value
    ownership_confidence: float | None = None
    ownership_source_event_id: str | None = None


@dataclass(frozen=True)
class ReconstructionConfig:
    """重建链的全部可配置超参数。

    与设计文档的 `ball_reconstruction` 配置块对应。
    """

    # 接触高度先验（S2）
    default_contact_height_m: float = 1.10
    contact_height_min_m: float = 0.45
    contact_height_max_m: float = 2.40
    contact_height_uncertainty_m: float = 0.60

    # 段切分
    long_loss_gap_frames: int = 12  # 帧间隔超过此值视为长时间丢失（与 cleaner 最大插值缺口一致）
    serve_confidence_threshold: float = 0.6  # 高可信 serve 事件阈值
    min_points_per_segment: int = 3

    # 击球候选检测（D2）
    hit_context_points: int = 4  # 突变前后各需的连续有效点数
    hit_direction_change_deg: float = 35.0  # 方向突变角度阈值
    hit_speed_change_ratio: float = 1.8  # 速度幅值突变比例阈值
    hit_fit_residual_px: float = 18.0  # 突变前后拟合残差上限（低于此才算可靠）
    hit_min_event_gap_sec: float = 0.35  # 击球候选 refractory period
    bounce_suppression_window_sec: float = 0.25  # 高可信弹地抑制击球的窗口

    # 事件仲裁
    ambiguous_margin_sec: float = 0.10  # 低可信弹地与击球候选同窗判定余量
    player_proximity_strong_ft: float = 12.0  # 击球点距球员区域近的证据（第一版用 weak evidence）

    # 重建
    minimum_anchor_distance_ft: float = 2.0
    max_lateral_residual_ft: float = 4.0
    lateral_smooth_window: int = 5
    flight_peak_height_ft: float = 5.5  # 无事件锚定时飞行弧线峰值上限（估算）

    # 展示阈值（D4 / 质量评估）
    high_confidence_threshold: float = 0.80
    medium_confidence_threshold: float = 0.60
    low_confidence_threshold: float = 0.40

    @property
    def default_contact_height_ft(self) -> float:
        return self.default_contact_height_m * M_TO_FT

    @property
    def contact_height_min_ft(self) -> float:
        return self.contact_height_min_m * M_TO_FT

    @property
    def contact_height_max_ft(self) -> float:
        return self.contact_height_max_m * M_TO_FT

    @property
    def contact_height_uncertainty_ft(self) -> float:
        return self.contact_height_uncertainty_m * M_TO_FT


def event_to_payload(event: TrajectoryEvent) -> dict:
    """TrajectoryEvent → JSON 安全的字典。"""
    attribution = None
    if event.attribution is not None:
        attribution = {
            "candidate_id": event.attribution.candidate_id,
            "status": event.attribution.status,
            "player_id": event.attribution.player_id,
            "render_slot": event.attribution.render_slot,
            "confidence": round(float(event.attribution.confidence), 3),
            "score_margin": round(float(event.attribution.score_margin), 3),
            "attributed_frame_index": event.attribution.attributed_frame_index,
            "method": event.attribution.method,
            "candidate_scores": [
                {"player_id": score.player_id, "score": round(float(score.score), 3)}
                for score in event.attribution.candidate_scores
            ],
        }
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "frame_index": int(event.frame_index),
        "timestamp_sec": round(float(event.timestamp_sec), 6),
        "image_xy": [float(x) for x in event.image_xy] if event.image_xy is not None else None,
        "court_xy": [float(x) for x in event.court_xy] if event.court_xy is not None else None,
        "confidence": round(float(event.confidence), 3),
        "source": event.source,
        "diagnostics": event.diagnostics,
        "event_status": event.event_status,
        "hitter_player_id": event.hitter_player_id,
        "hitter_render_slot": event.hitter_render_slot,
        "ownership_status": event.ownership_status,
        "ownership_confidence": round(float(event.ownership_confidence), 3)
        if event.ownership_confidence is not None
        else None,
        "ownership_source_event_id": event.ownership_source_event_id,
        "attribution": attribution,
    }
