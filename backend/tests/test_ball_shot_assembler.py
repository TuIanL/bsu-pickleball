"""BallShotAssembler 与 ShotSequenceValidator 测试（Shot 生命周期 / 归属传播 / 半场交替）。"""

from app.schemas.tracking import PlayerTrajectoryArtifact, PlayerTrajectorySample
from app.vision.pickleball_game_analysis.ball_shot_assembler import (
    BallShotAssembler,
    ShotSequenceValidator,
)
from app.vision.pickleball_game_analysis.player_attribution_context import (
    build_player_attribution_context,
)
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    FlightSegment,
    OwnershipStatus,
    PlayerAttribution,
    TrajectoryEvent,
    TrajectoryEventType,
)


def event(event_id, event_type, frame, ts, *, hitter=None, ownership="unassigned", confidence=None, attribution=None):
    return TrajectoryEvent(
        event_id=event_id,
        event_type=event_type,
        frame_index=frame,
        timestamp_sec=ts,
        confidence=0.9,
        hitter_player_id=hitter,
        ownership_status=ownership,
        ownership_confidence=confidence,
        attribution=attribution,
    )


def segment(segment_id, start_event_id, end_event_id, start_type, end_type, boundary_reason=""):
    return FlightSegment(
        segment_id=segment_id,
        start_index=0,
        end_index=10,
        start_event_id=start_event_id,
        end_event_id=end_event_id,
        start_event_type=start_type,
        end_event_type=end_type,
        boundary_reason=boundary_reason,
    )


def attribution(player, confidence, margin):
    return PlayerAttribution(
        candidate_id="hit-cand-x",
        status=OwnershipStatus.CONFIRMED.value,
        player_id=player,
        confidence=confidence,
        score_margin=margin,
        method="pose_bbox_fused",
    )


def test_shot_propagates_owner_across_bounce():
    """hit(P1) → bounce → next hit(P3)：bounce 前后段同属 P1 的 shot。"""
    events = {
        "hit-1": event(
            "hit-1",
            TrajectoryEventType.HIT,
            100,
            3.33,
            hitter="Player_1",
            ownership="confirmed",
            confidence=0.9,
            attribution=attribution("Player_1", 0.9, 0.5),
        ),
        "bounce-1": event("bounce-1", TrajectoryEventType.BOUNCE, 130, 4.33),
        "hit-2": event(
            "hit-2",
            TrajectoryEventType.HIT,
            160,
            5.33,
            hitter="Player_3",
            ownership="confirmed",
            confidence=0.95,
            attribution=attribution("Player_3", 0.95, 0.6),
        ),
    }
    segments = [
        segment("flight-1", "hit-1", "bounce-1", TrajectoryEventType.HIT, TrajectoryEventType.BOUNCE),
        segment("flight-2", "bounce-1", "hit-2", TrajectoryEventType.BOUNCE, TrajectoryEventType.HIT),
    ]
    assembler = BallShotAssembler()
    shots = assembler.assemble(segments, events)
    assert segments[0].shot_id == segments[1].shot_id
    assert segments[0].hitter_player_id == "Player_1"
    assert segments[1].hitter_player_id == "Player_1"
    assert segments[0].ownership_status == "confirmed"
    assert segments[1].ownership_source_event_id == "hit-1"
    assert shots[0].shot_id == segments[0].shot_id


def test_suppressed_hit_does_not_break_shot():
    """suppressed/rejected 候选不出现在事件列表 → shot 不中断（I11）。"""
    events = {
        "hit-1": event(
            "hit-1",
            TrajectoryEventType.HIT,
            100,
            3.33,
            hitter="Player_1",
            ownership="confirmed",
            confidence=0.9,
            attribution=attribution("Player_1", 0.9, 0.5),
        ),
        "bounce-1": event("bounce-1", TrajectoryEventType.BOUNCE, 130, 4.33),
        "hit-2": event(
            "hit-2",
            TrajectoryEventType.HIT,
            136,
            4.53,
            hitter="Player_3",
            ownership="confirmed",
            confidence=0.9,
            attribution=attribution("Player_3", 0.9, 0.5),
        ),
    }
    segments = [
        segment("flight-1", "hit-1", "bounce-1", TrajectoryEventType.HIT, TrajectoryEventType.BOUNCE),
        segment("flight-2", "bounce-1", "hit-2", TrajectoryEventType.BOUNCE, TrajectoryEventType.HIT),
    ]
    assembler = BallShotAssembler()
    shots = assembler.assemble(segments, events)
    # bounce 后快速击球（I12）：flight-2 属于 shot-1（P1），下一个段将属于 shot-2（P3）
    assert segments[1].shot_id == shots[0].shot_id
    assert len(shots) == 2


def test_long_loss_creates_orphan_segment():
    """long loss 后残余段为 shot_id=null / not_applicable 的孤立段。"""
    events = {
        "hit-1": event(
            "hit-1",
            TrajectoryEventType.HIT,
            100,
            3.33,
            hitter="Player_1",
            ownership="confirmed",
            confidence=0.9,
            attribution=attribution("Player_1", 0.9, 0.5),
        ),
    }
    segments = [
        segment("flight-1", "hit-1", None, TrajectoryEventType.HIT, TrajectoryEventType.LOSS, "long_loss"),
        segment("flight-2", None, None, TrajectoryEventType.LOSS, TrajectoryEventType.END_OF_STREAM, "reacquired"),
    ]
    assembler = BallShotAssembler()
    shots = assembler.assemble(segments, events)
    assert segments[0].shot_id is not None
    assert segments[0].hitter_player_id == "Player_1"
    assert segments[1].shot_id is None
    assert segments[1].ownership_status == OwnershipStatus.NOT_APPLICABLE.value
    assert segments[1].hitter_player_id is None
    assert len(shots) == 1


def test_serve_seeds_shot():
    """serve 事件携带 player_id 时直接播种 shot owner。"""
    events = {
        "serve-1": event("serve-1", TrajectoryEventType.SERVE_RESET, 10, 0.33, hitter="Player_2"),
    }
    segments = [
        segment("flight-1", "serve-1", None, TrajectoryEventType.SERVE_RESET, TrajectoryEventType.END_OF_STREAM),
    ]
    assembler = BallShotAssembler()
    shots = assembler.assemble(segments, events)
    assert segments[0].shot_id == shots[0].shot_id
    assert segments[0].hitter_player_id == "Player_2"
    assert segments[0].ownership_status == "confirmed"


def _context_with_players():
    trajectory = PlayerTrajectoryArtifact(
        job_id="job-1",
        players={
            "Player_1": [
                PlayerTrajectorySample(
                    frame_index=100,
                    timestamp_seconds=3.33,
                    player_id="Player_1",
                    track_id=1,
                    court_x=5.0,
                    court_y=3.0,
                    court_unit="m",
                )
            ],
            "Player_2": [
                PlayerTrajectorySample(
                    frame_index=100,
                    timestamp_seconds=3.33,
                    player_id="Player_2",
                    track_id=2,
                    court_x=5.0,
                    court_y=3.5,
                    court_unit="m",
                )
            ],
            "Player_3": [
                PlayerTrajectorySample(
                    frame_index=100,
                    timestamp_seconds=3.33,
                    player_id="Player_3",
                    track_id=3,
                    court_x=5.0,
                    court_y=10.0,
                    court_unit="m",
                )
            ],
            "Player_4": [
                PlayerTrajectorySample(
                    frame_index=100,
                    timestamp_seconds=3.33,
                    player_id="Player_4",
                    track_id=4,
                    court_x=5.0,
                    court_y=10.5,
                    court_unit="m",
                )
            ],
        },
    )
    return build_player_attribution_context(player_trajectories=trajectory)


def _two_shots_same_side(context, confidence=0.7, margin=0.1):
    """两个同侧 Shot（P1 → P2，都在近场）。"""
    events = {
        "hit-1": event(
            "hit-1",
            TrajectoryEventType.HIT,
            100,
            3.33,
            hitter="Player_1",
            ownership="confirmed",
            confidence=confidence,
            attribution=attribution("Player_1", confidence, margin),
        ),
        "hit-2": event(
            "hit-2",
            TrajectoryEventType.HIT,
            200,
            6.66,
            hitter="Player_2",
            ownership="confirmed",
            confidence=confidence,
            attribution=attribution("Player_2", confidence, margin),
        ),
    }
    segments = [
        segment("flight-1", "hit-1", "hit-2", TrajectoryEventType.HIT, TrajectoryEventType.HIT),
        segment("flight-2", "hit-2", None, TrajectoryEventType.HIT, TrajectoryEventType.END_OF_STREAM),
    ]
    assembler = BallShotAssembler()
    shots = assembler.assemble(segments, events)
    return shots, segments


def test_same_side_weak_evidence_downgraded():
    """连续同半场且证据弱 → 当前 Shot 降级 ambiguous，player_id 置 None。"""
    context = _context_with_players()
    shots, segments = _two_shots_same_side(context, confidence=0.7, margin=0.1)
    validator = ShotSequenceValidator()
    downgraded = validator.validate(shots, segments, context)
    assert [shot.shot_id for shot in downgraded] == ["shot-002"]
    assert segments[1].hitter_player_id is None
    assert segments[1].ownership_status == "ambiguous"
    assert "side_alternation_downgraded" in segments[1].boundary_reason


def test_same_side_strong_evidence_kept_with_diagnostic():
    """连续同半场但证据强 → 保留结论并记录 side_alternation_violation。"""
    context = _context_with_players()
    shots, segments = _two_shots_same_side(context, confidence=0.95, margin=0.5)
    validator = ShotSequenceValidator()
    downgraded = validator.validate(shots, segments, context)
    assert downgraded == []
    assert segments[1].hitter_player_id == "Player_2"
    assert segments[1].ownership_status == "confirmed"
    assert "side_alternation_violation" in segments[1].boundary_reason


def test_alternating_sides_no_violation():
    """半场交替正常 → 无降级无诊断。"""
    context = _context_with_players()
    events = {
        "hit-1": event(
            "hit-1",
            TrajectoryEventType.HIT,
            100,
            3.33,
            hitter="Player_1",
            ownership="confirmed",
            confidence=0.7,
            attribution=attribution("Player_1", 0.7, 0.1),
        ),
        "hit-2": event(
            "hit-2",
            TrajectoryEventType.HIT,
            200,
            6.66,
            hitter="Player_3",
            ownership="confirmed",
            confidence=0.7,
            attribution=attribution("Player_3", 0.7, 0.1),
        ),
    }
    segments = [
        segment("flight-1", "hit-1", "hit-2", TrajectoryEventType.HIT, TrajectoryEventType.HIT),
        segment("flight-2", "hit-2", None, TrajectoryEventType.HIT, TrajectoryEventType.END_OF_STREAM),
    ]
    assembler = BallShotAssembler()
    shots = assembler.assemble(segments, events)
    validator = ShotSequenceValidator()
    assert validator.validate(shots, segments, context) == []
    assert segments[1].hitter_player_id == "Player_3"
