"""fused overlay（multiview-fused-player-overlay.v1）单元测试。

覆盖：contract schema 校验、投影 helper、evidence bundle、分支决策链、
bbox 记忆 / 纯平移 reanchor（tasks 1.3 / 2.3 / 3.7 / 4.3）。
"""

from __future__ import annotations

import pytest

from app.vision.multiview.fused_overlay_builder import (
    FusedPlayerOverlayBuilder,
    OverlayBuilderConfig,
    TargetViewBBoxMemory,
    classify_f0_origin,
)
from app.vision.multiview.fused_overlay_bundle import (
    JointOverlayEvidenceBundle,
    ViewGeometry,
    build_overlay_evidence_bundle,
)
from app.vision.multiview.overlay_display_state import (
    DisplayContext,
    OverlayDisplayStateMachine,
)
from app.vision.multiview.bootstrap_display_backfill import BootstrapBackfillObservation
from app.vision.multiview.fused_overlay_projection import canonical_to_target_image
from app.vision.multiview.fused_overlay_types import (
    build_fused_player_overlay_payload,
    validate_fused_player_overlay,
)
from app.vision.multiview.offline_refinement import (
    F0RefinementSnapshot,
    F0TickSnapshot,
    F0TickViewState,
    RecoveredViewObservation,
)
from app.vision.multiview.court_frame import CourtOrientation

# ---- 测试用几何：identity 朝向 + 10x 缩放 homography -------------------------

IDENTITY_ORIENTATION = CourtOrientation.identity

# 球场→图像方向：10x 缩放（球场英尺坐标 ×10 → 像素）
TEST_INVERSE_HOMOGRAPHY = [
    [10.0, 0.0, 0.0],
    [0.0, 10.0, 0.0],
    [0.0, 0.0, 1.0],
]


def _geometry(width: int = 640, height: int = 480) -> ViewGeometry:
    return ViewGeometry(
        view_id="cam_1",
        orientation=IDENTITY_ORIENTATION,
        inverse_homography=TEST_INVERSE_HOMOGRAPHY,
        frame_width=width,
        frame_height=height,
    )


def _make_state(
    *,
    observed: bool = True,
    quality: float = 0.8,
    origin: str = "base",
    bbox: tuple[float, ...] = (100.0, 200.0, 150.0, 300.0),
    canonical_position: tuple[float, float] = (10.0, 20.0),
    mapped_take_timestamp_ms: float | None = 1000.0,
) -> F0TickViewState:
    return F0TickViewState(
        observed=observed,
        quality=quality,
        canonical_position=canonical_position,
        origin=origin,
        source_frame_index=10,
        source_timestamp_ms=1000.0,
        mapped_take_timestamp_ms=mapped_take_timestamp_ms,
        timing_authority="reference",
        sync_quality="good",
        view_status="available",
        observation_status="observed" if observed else "missing",
        view_player_id="global_player_1",
        detector_confidence=quality,
        projection_confidence=0.9,
        tracking_status="detected",
        bbox=bbox,
    )


def _make_tick(
    canonical_tick: int = 1,
    reference_frame_index: int = 10,
    canonical_timestamp_ms: float = 1000.0,
    observations: tuple[tuple[str, str, F0TickViewState], ...] = (),
    global_positions: tuple[tuple[str, tuple[float, float]], ...] = (),
    predictions: tuple[tuple[str, tuple[float, float]], ...] = (),
) -> F0TickSnapshot:
    return F0TickSnapshot(
        canonical_tick=canonical_tick,
        canonical_timestamp_ms=canonical_timestamp_ms,
        reference_frame_index=reference_frame_index,
        observations=observations,
        global_positions=global_positions,
        predictions=predictions,
    )


def _make_bundle(
    *,
    f0_snapshot: F0RefinementSnapshot | None = None,
    fused_samples: dict | None = None,
    fused_positions: dict | None = None,
    recovered: list[RecoveredViewObservation] | None = None,
    final_source: str = "first_pass_f0",
    roster_map: dict | None = None,
    bootstrap_backfill: dict | None = None,
) -> JointOverlayEvidenceBundle:
    return JointOverlayEvidenceBundle(
        f0_snapshot=f0_snapshot,
        reference_view_id="cam_1",
        view_ids=("cam_1", "cam_2"),
        roster_map=dict(roster_map or {"global_player_1": "Player_1"}),
        view_geometry={"cam_1": _geometry(), "cam_2": _geometry()},
        fused_samples=dict(fused_samples or {}),
        fused_positions=dict(fused_positions or {}),
        recovered_observations={
            (obs.global_player_id, obs.canonical_tick): obs for obs in (recovered or [])
        },
        final_source=final_source,
        last_real_observed_ms={("global_player_1", "cam_1"): 1000.0},
        bootstrap_backfill=dict(bootstrap_backfill or {}),
    )


# ===========================================================================
# 1.3 contract schema 校验
# ===========================================================================


class TestContractSchema:
    def test_valid_payload(self) -> None:
        payload = build_fused_player_overlay_payload(
            job_id="job-1",
            video_id="video-1",
            reference_view_id="cam_1",
            frame_size={"width": 640, "height": 480},
            frames=[],
            status="available",
            detail="ok",
        )
        validate_fused_player_overlay(payload)
        assert payload["schema_version"] == "multiview-fused-player-overlay.v1"

    def test_cross_view_must_carry_donor(self) -> None:
        from app.vision.multiview.fused_overlay_types import FusedPlayerOverlayFrame

        frame = FusedPlayerOverlayFrame(
            frame_index=0,
            timestamp_seconds=0.0,
            players=[],
        )
        payload = build_fused_player_overlay_payload(
            job_id="job-1",
            video_id=None,
            reference_view_id="cam_1",
            frame_size=None,
            frames=[frame],
        )
        # 手动注入一个缺 donor_view 的 cross_view entity
        payload["frames"][0]["players"].append(
            {
                "player_id": "Player_3",
                "bbox": [1, 2, 3, 4],
                "evidence_type": "cross_view_projected",
                "donor_view": None,
            }
        )
        with pytest.raises(ValueError, match="donor_view"):
            validate_fused_player_overlay(payload)

    def test_duplicate_player_rejected(self) -> None:
        payload = build_fused_player_overlay_payload(
            job_id="job-1",
            video_id=None,
            reference_view_id="cam_1",
            frame_size=None,
            frames=[],
        )
        payload["frames"].append(
            {
                "frame_index": 0,
                "timestamp_seconds": 0.0,
                "players": [
                    {"player_id": "Player_1", "evidence_type": "base_observed"},
                    {"player_id": "Player_1", "evidence_type": "base_observed"},
                ],
            }
        )
        with pytest.raises(ValueError, match="duplicate player_id"):
            validate_fused_player_overlay(payload)


# ===========================================================================
# 1.3 投影 helper
# ===========================================================================


class TestProjectionHelper:
    def test_valid_projection(self) -> None:
        result = canonical_to_target_image(
            canonical_position=(10.0, 20.0),
            orientation=IDENTITY_ORIENTATION,
            inverse_homography=TEST_INVERSE_HOMOGRAPHY,
            frame_width=640,
            frame_height=480,
        )
        assert result.projection_valid is True
        assert result.image_footpoint == (100.0, 200.0)

    def test_missing_orientation_invalid(self) -> None:
        result = canonical_to_target_image(
            canonical_position=(10.0, 20.0),
            orientation=None,
            inverse_homography=TEST_INVERSE_HOMOGRAPHY,
            frame_width=640,
            frame_height=480,
        )
        assert result.projection_valid is False
        assert result.failure_reason == "missing_orientation"

    def test_outside_frame_invalid(self) -> None:
        result = canonical_to_target_image(
            canonical_position=(100.0, 100.0),
            orientation=IDENTITY_ORIENTATION,
            inverse_homography=TEST_INVERSE_HOMOGRAPHY,
            frame_width=640,
            frame_height=480,
        )
        assert result.projection_valid is False
        assert result.failure_reason == "projection_outside_frame"


# ===========================================================================
# 2.3 evidence bundle
# ===========================================================================


class TestEvidenceBundle:
    def test_bundle_from_snapshot(self) -> None:
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(("global_player_1", "cam_1", _make_state()),),
                ),
            ),
        )
        bundle = _make_bundle(f0_snapshot=snapshot)
        assert bundle.player_id_for("global_player_1") == "Player_1"
        assert bundle.recovered_for("global_player_1", 1) is None

    def test_recovered_mapping(self) -> None:
        recovered = RecoveredViewObservation(
            view_id="cam_1",
            take_timestamp_ms=1000.0,
            source_frame_index=10,
            canonical_x_ft=10.0,
            canonical_y_ft=20.0,
            bbox=(100.0, 200.0, 150.0, 300.0),
            confidence=0.9,
            global_player_id="global_player_1",
            canonical_tick=1,
        )
        bundle = _make_bundle(recovered=[recovered], final_source="refined_f1")
        assert bundle.has_recovered_evidence() is True
        assert bundle.recovered_for("global_player_1", 1) is recovered

    def test_no_recovered_when_first_pass(self) -> None:
        bundle = _make_bundle(final_source="first_pass_f0")
        assert bundle.has_recovered_evidence() is False


# ===========================================================================
# 3.7 分支决策链
# ===========================================================================


class TestBranchDecisionChain:
    def test_target_view_switch_reuses_canonical_identity_and_position(self) -> None:
        snapshot = F0RefinementSnapshot(
            run_id="run-view-switch",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(
                        ("global_player_1", "cam_1", _make_state(bbox=(100.0, 200.0, 150.0, 300.0))),
                        ("global_player_1", "cam_2", _make_state(bbox=(300.0, 120.0, 350.0, 220.0))),
                    ),
                ),
            ),
        )
        bundle = _make_bundle(
            f0_snapshot=snapshot,
            fused_positions={"global_player_1": {10: (10.0, 20.0)}},
        )

        cam_a = FusedPlayerOverlayBuilder().build(bundle=bundle, target_view_id="cam_1")
        cam_b = FusedPlayerOverlayBuilder().build(bundle=bundle, target_view_id="cam_2")

        assert cam_a[0].players[0].player_id == cam_b[0].players[0].player_id == "Player_1"
        assert cam_a[0].players[0].bbox != cam_b[0].players[0].bbox
        assert cam_a[0].players[0].canonical_court_position_ft == [10.0, 20.0]
        assert cam_b[0].players[0].canonical_court_position_ft == [10.0, 20.0]

    def test_strong_f0_base_observed(self) -> None:
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.8)),),
                    global_positions=(("global_player_1", (10.0, 20.0)),),
                ),
            ),
        )
        bundle = _make_bundle(f0_snapshot=snapshot)
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert len(frames) == 1
        players = frames[0].players
        assert len(players) == 1
        assert players[0].evidence_type == "base_observed"
        assert players[0].bbox == [100.0, 200.0, 150.0, 300.0]

    def test_guided_roi_maps_to_guided_observed(self) -> None:
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(("global_player_1", "cam_1", _make_state(origin="guided_roi", quality=0.8)),),
                ),
            ),
        )
        bundle = _make_bundle(f0_snapshot=snapshot)
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert frames[0].players[0].evidence_type == "guided_observed"

    def test_recovered_precedes_weak_f0(self) -> None:
        # F0 weak（quality 0.3）+ accepted recovered → refined_observed
        recovered = RecoveredViewObservation(
            view_id="cam_1",
            take_timestamp_ms=1000.0,
            source_frame_index=10,
            canonical_x_ft=10.0,
            canonical_y_ft=20.0,
            bbox=(110.0, 210.0, 160.0, 310.0),
            confidence=0.92,
            global_player_id="global_player_1",
            canonical_tick=1,
        )
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.3)),),
                ),
            ),
        )
        bundle = _make_bundle(f0_snapshot=snapshot, recovered=[recovered], final_source="refined_f1")
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        player = frames[0].players[0]
        assert player.evidence_type == "refined_observed"
        assert player.bbox == [110.0, 210.0, 160.0, 310.0]
        assert player.provenance == "offline_refinement"

    def test_strong_f0_not_overridden_by_recovered(self) -> None:
        recovered = RecoveredViewObservation(
            view_id="cam_1",
            take_timestamp_ms=1000.0,
            source_frame_index=10,
            canonical_x_ft=10.0,
            canonical_y_ft=20.0,
            bbox=(999.0, 999.0, 1050.0, 1100.0),
            confidence=0.99,
            global_player_id="global_player_1",
            canonical_tick=1,
        )
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.8)),),
                ),
            ),
        )
        bundle = _make_bundle(f0_snapshot=snapshot, recovered=[recovered], final_source="refined_f1")
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert frames[0].players[0].evidence_type == "base_observed"

    def test_cross_view_projected(self) -> None:
        # reference 无观测；donor cam_2 真实观测 + fused 位置 + geometry 有效
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(
                        ("global_player_1", "cam_1", _make_state(observed=False, bbox=None)),
                        ("global_player_1", "cam_2", _make_state(origin="base", quality=0.85, bbox=(300.0, 200.0, 350.0, 300.0))),
                    ),
                    global_positions=(("global_player_1", (10.0, 20.0)),),
                ),
            ),
        )
        bundle = _make_bundle(
            f0_snapshot=snapshot,
            fused_samples={
                "global_player_1": {10: {"global_player_id": "global_player_1", "fusion_status": "dual_observed"}}
            },
            fused_positions={"global_player_1": {10: (10.0, 20.0)}},
        )
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        player = frames[0].players[0]
        assert player.evidence_type == "cross_view_projected"
        assert player.donor_view == "cam_2"
        # projection 10,20 → (100, 200)；无历史 bbox → footpoint + halo
        assert player.footpoint == [100.0, 200.0]
        assert player.bbox is None
        assert player.bbox_source == "none"

    def test_projected_bbox_collision_keeps_stable_geometry_and_records_reason(self) -> None:
        """投影框若会覆盖另一名可信球员，不发布新 synthetic geometry。"""
        snapshot = F0RefinementSnapshot(
            run_id="run-collision",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1", "global_player_2"),
            ticks=(
                _make_tick(
                    canonical_tick=1,
                    reference_frame_index=10,
                    canonical_timestamp_ms=1000.0,
                    observations=(
                        ("global_player_1", "cam_1", _make_state(quality=0.9, bbox=(100.0, 200.0, 150.0, 300.0))),
                    ),
                ),
                _make_tick(
                    canonical_tick=2,
                    reference_frame_index=20,
                    canonical_timestamp_ms=1033.0,
                    observations=(
                        ("global_player_1", "cam_1", _make_state(observed=False, quality=0.0, origin="missing", bbox=None, canonical_position=None)),
                        ("global_player_1", "cam_2", _make_state(quality=0.9, bbox=(300.0, 200.0, 350.0, 300.0))),
                        ("global_player_2", "cam_1", _make_state(quality=0.9, bbox=(75.0, 150.0, 125.0, 250.0))),
                    ),
                ),
            ),
        )
        bundle = _make_bundle(
            f0_snapshot=snapshot,
            roster_map={"global_player_1": "Player_1", "global_player_2": "Player_2"},
            fused_samples={
                "global_player_1": {20: {"global_player_id": "global_player_1", "fusion_status": "dual_observed"}},
            },
            fused_positions={"global_player_1": {20: (10.0, 20.0)}},
        )
        builder = FusedPlayerOverlayBuilder()
        frames = builder.build(bundle=bundle)
        player = next(item for item in frames[1].players if item.player_id == "Player_1")
        assert player.evidence_type == "cross_view_projected"
        assert player.projection_rejection_reason == "projection_collision_with_global_player_2"
        assert player.display_reason == "projection_collision_fallback"
        assert builder.diagnostics["projection_gate_rejected"] == 1

    def test_predicted_only_when_within_ttl(self) -> None:
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    observations=(),
                    global_positions=(("global_player_1", (10.0, 20.0)),),
                ),
            ),
        )
        bundle = _make_bundle(
            f0_snapshot=snapshot,
            fused_samples={
                "global_player_1": {10: {"global_player_id": "global_player_1", "fusion_status": "predicted"}}
            },
            fused_positions={"global_player_1": {10: (10.0, 20.0)}},
            roster_map={"global_player_1": "Player_1"},
        )
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        player = frames[0].players[0]
        assert player.evidence_type == "predicted_only"
        assert player.bbox is None
        assert player.footpoint == [100.0, 200.0]

    def test_predicted_hidden_when_over_ttl(self) -> None:
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    canonical_timestamp_ms=5000.0,  # last_real 1000ms → age 4000ms > 500ms TTL
                    observations=(),
                ),
            ),
        )
        bundle = _make_bundle(
            f0_snapshot=snapshot,
            fused_samples={
                "global_player_1": {10: {"global_player_id": "global_player_1", "fusion_status": "predicted"}}
            },
            roster_map={"global_player_1": "Player_1"},
        )
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert frames[0].players == []

    def test_no_evidence_hidden(self) -> None:
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(_make_tick(observations=()),),
        )
        bundle = _make_bundle(f0_snapshot=snapshot)
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert frames[0].players == []


# ===========================================================================
# 4.3 bbox memory / reanchor
# ===========================================================================


class TestBBoxMemory:
    def test_qualifying_update_only(self) -> None:
        memory = TargetViewBBoxMemory(OverlayBuilderConfig())
        # 低质量不刷新
        memory.update(
            global_player_id="g1", view_id="cam_1",
            bbox=(100.0, 200.0, 150.0, 300.0), quality=0.2, observed_ms=1000.0,
        )
        assert memory.reanchor(
            global_player_id="g1", view_id="cam_1", new_footpoint=(120.0, 250.0), now_ms=1000.0
        ) is None
        # 合格刷新
        memory.update(
            global_player_id="g1", view_id="cam_1",
            bbox=(100.0, 200.0, 150.0, 300.0), quality=0.9, observed_ms=1000.0,
        )
        entry = memory.reanchor(
            global_player_id="g1", view_id="cam_1", new_footpoint=(120.0, 250.0), now_ms=1000.0
        )
        assert entry is not None
        # 纯平移：宽 50 高 100 不变；脚点 (120,250) → x1=95 x2=145 y1=150 y2=250
        assert entry.bbox == (95.0, 150.0, 145.0, 250.0)
        assert entry.width == 50.0
        assert entry.height == 100.0

    def test_expired_memory_degrades_to_none(self) -> None:
        memory = TargetViewBBoxMemory(OverlayBuilderConfig(bbox_memory_ttl_ms=2000.0))
        memory.update(
            global_player_id="g1", view_id="cam_1",
            bbox=(100.0, 200.0, 150.0, 300.0), quality=0.9, observed_ms=1000.0,
        )
        entry = memory.reanchor(
            global_player_id="g1", view_id="cam_1", new_footpoint=(120.0, 250.0), now_ms=4000.0
        )
        assert entry is None

    def test_invalid_bbox_not_qualifying(self) -> None:
        memory = TargetViewBBoxMemory(OverlayBuilderConfig())
        memory.update(
            global_player_id="g1", view_id="cam_1",
            bbox=(100.0, 200.0, 50.0, 300.0), quality=0.9, observed_ms=1000.0,  # 反向宽
        )
        assert memory.reanchor(
            global_player_id="g1", view_id="cam_1", new_footpoint=(120.0, 250.0), now_ms=1000.0
        ) is None


# ===========================================================================
# provenance mapper
# ===========================================================================


class TestOriginMapper:
    def test_guided_roi_maps_correctly(self) -> None:
        assert classify_f0_origin("guided_roi") == "guided_observed"

    def test_base_maps_correctly(self) -> None:
        assert classify_f0_origin("base") == "base_observed"

    def test_unknown_falls_back_to_base(self) -> None:
        assert classify_f0_origin("some_future_origin") == "base_observed"


# ===========================================================================
# 8.2 硬不变量统计
# ===========================================================================


class TestOverlayInvariants:
    def test_clean_payload_zero_invariants(self) -> None:
        from app.vision.multiview.fused_overlay_types import count_overlay_invariants

        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1", "global_player_2"),
            ticks=(
                _make_tick(
                    observations=(
                        ("global_player_1", "cam_1", _make_state(quality=0.9)),
                        ("global_player_2", "cam_1", _make_state(quality=0.8, bbox=(200.0, 200.0, 250.0, 300.0))),
                    ),
                ),
            ),
        )
        bundle = _make_bundle(
            f0_snapshot=snapshot,
            roster_map={"global_player_1": "Player_1", "global_player_2": "Player_2"},
        )
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        payload = build_fused_player_overlay_payload(
            job_id="job-1", video_id=None, reference_view_id="cam_1",
            frame_size={"width": 640, "height": 480}, frames=frames,
        )
        counts = count_overlay_invariants(payload, expected_player_count=4)
        assert counts == {
            "invalid_projection_count": 0,
            "unknown_public_player_id_count": 0,
            "overlay_player_count_per_tick_exceeded": 0,
            "cross_view_projected_without_donor": 0,
            "prediction_over_ttl_rendered": 0,
        }

    def test_invariant_detects_violations(self) -> None:
        from app.vision.multiview.fused_overlay_types import count_overlay_invariants

        payload = {
            "schema_version": "multiview-fused-player-overlay.v1",
            "reference_view_id": "cam_1",
            "frames": [
                {
                    "frame_index": 0,
                    "timestamp_seconds": 0.0,
                    "players": [
                        {"player_id": "track_47", "evidence_type": "base_observed"},  # 非 canonical
                        {"player_id": "Player_2", "evidence_type": "cross_view_projected"},  # 缺 donor
                    ],
                },
                {
                    "frame_index": 1,
                    "timestamp_seconds": 1.0,
                    "players": [  # 单 tick 5 名（expected 4）
                        {"player_id": "Player_1", "evidence_type": "base_observed"},
                        {"player_id": "Player_2", "evidence_type": "base_observed"},
                        {"player_id": "Player_3", "evidence_type": "base_observed"},
                        {"player_id": "Player_4", "evidence_type": "base_observed"},
                        {"player_id": "Player_5", "evidence_type": "base_observed"},
                    ],
                },
            ],
        }
        counts = count_overlay_invariants(payload, expected_player_count=4)
        assert counts["unknown_public_player_id_count"] == 1
        assert counts["cross_view_projected_without_donor"] == 1
        assert counts["overlay_player_count_per_tick_exceeded"] == 1


# ===========================================================================
# fix-multiview-single-view-fallback：单视图 overlay 渲染（D3）
# ===========================================================================


class TestSingleViewOverlayRendering:
    def test_overlay_single_view_real_box(self) -> None:
        """cam_1 单边 strong observation（无 cam_2 观测）→ base_observed/REAL_BOX。"""
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    canonical_tick=1,
                    canonical_timestamp_ms=1000.0,
                    observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.8)),),
                    global_positions=(("global_player_1", (10.0, 20.0)),),
                ),
            ),
        )
        bundle = _make_bundle(f0_snapshot=snapshot)
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert len(frames) == 1
        players = frames[0].players
        assert len(players) == 1
        assert players[0].evidence_type == "base_observed"
        assert players[0].display_state == "REAL_BOX"
        assert players[0].bbox == [100.0, 200.0, 150.0, 300.0]

    def test_overlay_single_view_recover_after_gap(self) -> None:
        """单视图玩家断帧（长 gap）后恢复 strong observation → 重新渲染（不永久隐藏）。"""
        ticks = (
            # tick 1-2: 观测中（REAL_BOX）
            _make_tick(
                canonical_tick=1, canonical_timestamp_ms=1000.0,
                observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.8)),),
                global_positions=(("global_player_1", (10.0, 20.0)),),
            ),
            _make_tick(
                canonical_tick=2, canonical_timestamp_ms=1500.0,
                observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.8)),),
                global_positions=(("global_player_1", (10.0, 20.0)),),
            ),
            # tick 3-4: 断帧（无观测）→ 展示降级
            _make_tick(
                canonical_tick=3, canonical_timestamp_ms=2500.0,
                observations=(("global_player_1", "cam_1", _make_state(observed=False, quality=0.0, origin="missing", bbox=None, canonical_position=None)),),
            ),
            _make_tick(
                canonical_tick=4, canonical_timestamp_ms=3000.0,
                observations=(("global_player_1", "cam_1", _make_state(observed=False, quality=0.0, origin="missing", bbox=None, canonical_position=None)),),
            ),
            # tick 5: 恢复 strong observation → 立即 REAL_BOX
            _make_tick(
                canonical_tick=5, canonical_timestamp_ms=3500.0,
                observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.8)),),
                global_positions=(("global_player_1", (10.0, 20.0)),),
            ),
        )
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=ticks,
        )
        bundle = _make_bundle(f0_snapshot=snapshot)
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert len(frames) == 5
        # tick 5（恢复帧）必须渲染 base_observed/REAL_BOX
        recovered = frames[4].players
        assert len(recovered) == 1
        assert recovered[0].evidence_type == "base_observed"
        assert recovered[0].display_state == "REAL_BOX"


# ===========================================================================
# fix-joint-bootstrap-visual-gap：启动窗口展示回填必须真正注入 fused overlay
# ===========================================================================


def _make_bootstrap_obs(
    player_id: str = "Player_1",
    track_id: int = 3,
    frame_index: int = 0,
    timestamp_seconds: float = 0.0,
    bbox: tuple[float, ...] = (785.0, 89.0, 838.0, 202.0),
    canonical: tuple[float, float] = (3.7, 8.96),
    source_confidence: float = 0.64,
) -> BootstrapBackfillObservation:
    return BootstrapBackfillObservation(
        player_id=player_id,
        track_id=track_id,
        frame_index=frame_index,
        timestamp_seconds=timestamp_seconds,
        bbox=list(bbox),
        court_position_local_ft=(float(canonical[0]), float(canonical[1])),
        canonical_court_position_ft=(float(canonical[0]), float(canonical[1])),
        source_confidence=source_confidence,
        evidence_type="bootstrap_backfill",
        display_only=True,
        metric_eligible=False,
    )


class TestBootstrapBackfillDisplay:
    """启动窗口回填观测必须以 REAL_BOX 渲染，且绝不伪造（无回填则不渲染）。"""

    def test_state_machine_renders_bootstrap_backfill_as_real_box(self) -> None:
        machine = OverlayDisplayStateMachine()
        plan = machine.step(
            player_id="Player_1",
            view_id="cam_1",
            ctx=DisplayContext(
                now_ms=0.0,
                evidence_type="bootstrap_backfill",
                has_real_bbox=True,
                has_valid_point=False,  # 启动窗口无 fused 位置/投影，仅靠真实检测框
                geometry_valid=True,
            ),
        )
        assert plan.render is True
        assert plan.state == "REAL_BOX"

    def test_state_machine_bootstrap_without_real_bbox_shows_no_fabricated_box(self) -> None:
        # 防御：bootstrap 是真实观测，即便底层检测缺 bbox，也应渲染（作为点）而非隐藏；
        # 但不得伪造框几何（preferred_bbox_source 必须为 none）。
        machine = OverlayDisplayStateMachine()
        plan = machine.step(
            player_id="Player_1",
            view_id="cam_1",
            ctx=DisplayContext(now_ms=0.0, evidence_type="bootstrap_backfill", has_real_bbox=False),
        )
        assert plan.render is True
        assert plan.state == "REAL_BOX"
        assert plan.preferred_bbox_source == "none"

    def test_builder_renders_bootstrap_at_pre_lock_frame(self) -> None:
        # 真实场景：Player_1 在快照全局存在（frame 68 锁定），但 frame 0 尚无 f0 观测；
        # 回填携带 frame 0 的真实检测观测，必须渲染为 bootstrap_backfill / REAL_BOX。
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                # frame 0：无 f0 观测（启动窗口身份未锁定），仅有回填
                _make_tick(
                    canonical_tick=0,
                    reference_frame_index=0,
                    canonical_timestamp_ms=0.0,
                    observations=(),
                ),
                # frame 68：锁定后 base_observed
                _make_tick(
                    canonical_tick=68,
                    reference_frame_index=68,
                    canonical_timestamp_ms=1133.0,
                    observations=(("global_player_1", "cam_1", _make_state(origin="base", quality=0.8)),),
                    global_positions=(("global_player_1", (10.0, 20.0)),),
                ),
            ),
        )
        bundle = _make_bundle(
            f0_snapshot=snapshot,
            bootstrap_backfill={("Player_1", 0): _make_bootstrap_obs()},
        )
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert len(frames) == 2

        pre_lock = frames[0].players
        assert len(pre_lock) == 1
        assert pre_lock[0].player_id == "Player_1"
        assert pre_lock[0].evidence_type == "bootstrap_backfill"
        assert pre_lock[0].display_state == "REAL_BOX"
        assert pre_lock[0].bbox == [785.0, 89.0, 838.0, 202.0]
        assert pre_lock[0].canonical_court_position_ft == [3.7, 8.96]

        # 锁定后无缝衔接为 base_observed，且不应重复出现 bootstrap_backfill
        post_lock = frames[1].players
        assert len(post_lock) == 1
        assert post_lock[0].evidence_type == "base_observed"

    def test_builder_no_fabrication_without_bootstrap(self) -> None:
        # 启动窗口无回填观测 → 该帧不渲染任何球员（诚实留空，绝不编造框）
        snapshot = F0RefinementSnapshot(
            run_id="run-1",
            reference_view_id="cam_1",
            view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(
                _make_tick(
                    canonical_tick=0,
                    reference_frame_index=0,
                    canonical_timestamp_ms=0.0,
                    observations=(),
                ),
            ),
        )
        bundle = _make_bundle(f0_snapshot=snapshot)  # 无 bootstrap_backfill
        frames = FusedPlayerOverlayBuilder().build(bundle=bundle)
        assert len(frames) == 1
        assert frames[0].players == []
