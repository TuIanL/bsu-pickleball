"""球员锁定管理器类型定义 —— PlayerSlot、PlayerLockUpdate、PlayerLockConfig。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.tracking import PlayerIdentityDiagnostic


@dataclass
class PlayerLockConfig:
    target_player_count: int = 4
    bootstrap_min_frames: int = 60
    bootstrap_max_frames: int = 180
    min_observed_frames: int = 8
    lock_min_hits: int = 5
    plausible_min_hits: int = 3
    lost_grace_frames: int = 3
    lost_max_frames_locked: int = 300
    locked_conf: float = 0.06
    tentative_conf: float = 0.12
    searching_conf: float = 0.20
    reconnect_threshold: float = 0.45
    court_margin_ft: float = 12.0
    max_reconnect_distance_ft: float = 15.0
    bootstrap_court_margin_ft: float = 12.0
    lost_reconnect_court_margin_ft: float = 20.0
    enable_appearance_score: bool = False


@dataclass
class PlayerSlot:
    identity_id: str
    state: str = "searching"
    current_track_id: int | None = None
    track_id_history: list[int] = field(default_factory=list)

    last_seen_frame: int = -1
    last_confirmed_position_m: list[float] | None = None
    last_velocity_mps: list[float] | None = None
    last_bbox: list[float] | None = None
    last_image_footpoint: list[float] | None = None

    side_hint: str | None = None
    confidence_ema: float = 0.0
    appearance_descriptor: list[float] | None = None

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
