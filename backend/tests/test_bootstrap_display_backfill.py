"""BootstrapDisplayBackfillBuilder 单元测试（fix-joint-bootstrap-visual-gap）。

不依赖完整 pipeline，仅验证：
- pre-lock 真实观测被回填、lock 帧与 post-lock 帧被排除；
- 坐标经 local_to_canonical 正确转换（identity 取向时 canonical==local）；
- provenance 字段（evidence_type / display_only / metric_eligible）正确；
- 无 initial_lock_assignments / 无 orientation → 安全返回空（不报错、不造假）；
- temporal/spatial continuity guard 在遇到异常跳变处截断历史（宁可少填）。
"""

from app.schemas.tracking import PlayerFramePosition
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.bootstrap_display_backfill import BootstrapDisplayBackfillBuilder
from app.vision.multiview.fused_overlay_bundle import JointOverlayEvidenceBundle
from app.vision.multiview.fused_overlay_builder import FusedPlayerOverlayBuilder
from app.vision.player_tracking_engine.player_lock_manager import InitialLockAssignment


def _pos(frame_index: int, track_id: int, cx: float, cy: float, conf: float = 0.9) -> PlayerFramePosition:
    return PlayerFramePosition(
        frame_index=frame_index,
        timestamp=float(frame_index) / 30.0,
        track_id=track_id,
        bbox=[cx - 10.0, cy - 20.0, cx + 10.0, cy],
        image_footpoint=[cx, cy],
        court_position=[cx, cy],
        confidence=conf,
    )


def test_fills_pre_lock_observations_only():
    assignments = {"Player_1": InitialLockAssignment(player_id="Player_1", track_id=5, locked_frame_index=30)}
    positions = [
        _pos(0, 5, 100, 100),
        _pos(10, 5, 105, 103),
        _pos(20, 5, 110, 106),
        _pos(30, 5, 115, 109),  # lock 帧：frame_index < locked 不成立，排除
        _pos(40, 5, 120, 112),  # post-lock：排除
    ]
    result = BootstrapDisplayBackfillBuilder().build(
        initial_lock_assignments=assignments,
        reference_positions=positions,
        reference_orientation=CourtOrientation.identity,
        reference_view_id="cam_1",
        frame_stride= 1,
        fps=30.0,
    )
    keyed = result.keyed()
    assert result.empty_reason is None
    assert len(result.observations) == 3
    assert ("Player_1", 0) in keyed
    assert ("Player_1", 30) not in keyed
    assert ("Player_1", 40) not in keyed
    obs = keyed[("Player_1", 0)]
    assert obs.canonical_court_position_ft == [100.0, 100.0]  # identity 取向：canonical==local
    assert obs.evidence_type == "bootstrap_backfill"
    assert obs.display_only is True
    assert obs.metric_eligible is False
    assert obs.bbox == [90.0, 80.0, 110.0, 100.0]


def test_no_assignments_returns_empty():
    result = BootstrapDisplayBackfillBuilder().build(
        initial_lock_assignments={},
        reference_positions=[_pos(0, 5, 100, 100)],
        reference_orientation=CourtOrientation.identity,
        reference_view_id="cam_1",
    )
    assert result.observations == []
    assert result.empty_reason == "no_initial_lock_assignments"


def test_missing_orientation_returns_empty():
    result = BootstrapDisplayBackfillBuilder().build(
        initial_lock_assignments={"Player_1": InitialLockAssignment("Player_1", 5, 30)},
        reference_positions=[_pos(0, 5, 100, 100)],
        reference_orientation=None,
        reference_view_id="cam_1",
    )
    assert result.observations == []
    assert result.empty_reason == "missing_reference_orientation"


def test_continuity_guard_rejects_abnormal_jump():
    assignments = {"Player_1": InitialLockAssignment("Player_1", 5, 30)}
    positions = [
        _pos(0, 5, 100, 100),       # anchor，接受
        _pos(10, 5, 1000, 1000),    # ≈1272 ft 跳变 / 0.33s >> 阈值 → 截断
    ]
    result = BootstrapDisplayBackfillBuilder(max_speed_ft_s=40.0).build(
        initial_lock_assignments=assignments,
        reference_positions=positions,
        reference_orientation=CourtOrientation.identity,
        reference_view_id="cam_1",
        fps=30.0,
    )
    keyed = result.keyed()
    assert ("Player_1", 0) in keyed
    assert ("Player_1", 10) not in keyed
    assert len(result.observations) == 1


def test_to_payload_serializes():
    assignments = {"Player_1": InitialLockAssignment("Player_1", 5, 30)}
    result = BootstrapDisplayBackfillBuilder().build(
        initial_lock_assignments=assignments,
        reference_positions=[_pos(0, 5, 100, 100)],
        reference_orientation=CourtOrientation.identity,
        reference_view_id="cam_1",
        fps=30.0,
    )
    payload = result.to_payload()
    assert payload["schema_version"] == "bootstrap_display_backfill.v1"
    assert payload["reference_view_id"] == "cam_1"
    assert payload["observation_count"] == 1
    obs = payload["observations"][0]
    assert obs["player_id"] == "Player_1"
    assert obs["evidence_type"] == "bootstrap_backfill"
    assert obs["display_only"] is True
    assert obs["metric_eligible"] is False


def test_decide_entity_bootstrap_fallback_branch():
    """验证 fused_overlay_builder._decide_entity 在五级证据全缺时启用 bootstrap 兜底。"""
    from app.vision.multiview.bootstrap_display_backfill import BootstrapBackfillObservation

    obs = BootstrapBackfillObservation(
        player_id="Player_1",
        track_id=5,
        frame_index=5,
        timestamp_seconds=0.166,
        bbox=[90.0, 80.0, 110.0, 100.0],
        court_position_local_ft=[100.0, 100.0],
        canonical_court_position_ft=[100.0, 100.0],
        source_confidence=0.9,
    )
    # 直接构造 bundle；bootstrap 分支不需要 f0_snapshot（经由 _decide_entity 直接分支）
    bundle = JointOverlayEvidenceBundle(bootstrap_backfill={("Player_1", 5): obs})
    entity = FusedPlayerOverlayBuilder()._decide_entity(
        bundle=bundle, tick=None, gid="Player_1", frame_index=5, now_ms=166.0
    )
    assert entity is not None
    assert entity.evidence_type == "bootstrap_backfill"
    assert entity.bbox == [90.0, 80.0, 110.0, 100.0]
    assert entity.canonical_court_position_ft == [100.0, 100.0]
    assert entity.player_id == "Player_1"

    # 不存在该帧的回填 → 仍返回 None（不渲染）
    none_entity = FusedPlayerOverlayBuilder()._decide_entity(
        bundle=bundle, tick=None, gid="Player_1", frame_index=99, now_ms=166.0
    )
    assert none_entity is None
