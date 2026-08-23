"""球员锁定管理器类型定义 —— PlayerSlot、PlayerLockUpdate、PlayerLockConfig。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.tracking import PlayerIdentityDiagnostic
from app.vision.player_tracking_engine.player_appearance import AppearanceTemplateGallery


@dataclass
class PlayerLockConfig:
    fps: float = 30.0
    target_player_count: int = 4
    near_side_quota: int = 2
    far_side_quota: int = 2
    allow_quota_fallback: bool = True
    fallback_promotion_frames: int = 90
    fallback_replacement_margin: float = 1.15
    bootstrap_min_frames: int = 60
    bootstrap_max_frames: int = 180
    min_observed_frames: int = 8
    lock_min_hits: int = 5
    plausible_min_hits: int = 3
    lost_grace_frames: int = 3
    # 【deprecated】硬锁到底后不再触发状态回退；保留字段仅为兼容旧配置/测试。
    lost_max_frames_locked: int = 300
    locked_conf: float = 0.06
    tentative_conf: float = 0.12
    searching_conf: float = 0.20
    reconnect_threshold: float = 0.45
    court_margin_ft: float = 12.0
    max_reconnect_distance_ft: float = 15.0
    # 重连空间门控：同侧但横向错配的候选侧分（与错侧同级惩罚），避免 position=0 的远距离候选靠运动/外观分数补足阈值
    reconnect_lateral_mismatch_score: float = 0.2
    # fix-multiview-player-identity D4：同侧横向错配候选的总分乘法惩罚系数
    # （side 相符但 left/right 不符时 score *= 该系数，防止跨身份互换）
    reconnect_lateral_mismatch_penalty: float = 0.5
    # 重连硬距离门开关：候选超过"允许距离"（max_reconnect_distance_ft + 速度×流逝时间）时拒绝重连、保持 LOST
    reconnect_gate_enabled: bool = True
    bootstrap_court_margin_ft: float = 12.0
    lost_reconnect_court_margin_ft: float = 20.0
    enable_appearance_score: bool = False
    reconnect_confirmation_frames: int = 1
    reconnect_ambiguity_margin: float = 0.08
    appearance_score_weight: float = 0.12
    # fix-multiview-player-identity D3：bootstrap 阶段"近端大尺寸高清晰"候选
    # 放宽判定阈值（bbox 面积 / 画面面积 比例）。
    near_large_bbox_ratio: float = 0.05


@dataclass
class PlayerSlot:
    identity_id: str  # "Player_1" / "Player_2" / "Player_3" / "Player_4"（与身份层命名一致）
    state: str = "searching"
    current_track_id: int | None = None
    track_id_history: list[int] = field(default_factory=list)

    last_seen_frame: int = -1
    last_confirmed_position_m: list[float] | None = None
    last_velocity_mps: list[float] | None = None
    last_bbox: list[float] | None = None
    last_image_footpoint: list[float] | None = None

    side_hint: str | None = None
    assignment_side: str | None = None
    home_quadrant: str | None = None
    confidence_ema: float = 0.0
    appearance_descriptor: list[float] | None = None
    appearance_template: AppearanceTemplateGallery = field(default_factory=AppearanceTemplateGallery)
    identity_epoch: int = 0

    lost_frames: int = 0
    locked_since_frame: int | None = None
    observed_frames: int = 0


@dataclass
class PlayerLockUpdate:
    eligible_track_ids: set[int] = field(default_factory=set)
    track_identity_hints: dict[int, str] = field(default_factory=dict)
    player_states: dict[str, str] = field(default_factory=dict)
    diagnostics: list[PlayerIdentityDiagnostic] = field(default_factory=list)
    newly_locked: list[str] = field(default_factory=list)
    newly_lost: list[str] = field(default_factory=list)
