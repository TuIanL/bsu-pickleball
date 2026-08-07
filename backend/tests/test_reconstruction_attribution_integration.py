"""重建链端到端集成测试：球员归属 → Shot 组装 → v2 产物；无上下文降级。"""

from app.schemas.pose import PoseKeypoint, PoseOverlayFrame, PoseSubject
from app.schemas.tracking import PlayerTrajectoryArtifact, PlayerTrajectorySample
from app.vision.pickleball_game_analysis.player_attribution_context import (
    build_player_attribution_context,
)
from app.vision.pickleball_game_analysis.reconstruction_engine import reconstruct_ball_trajectory
from app.vision.pickleball_game_analysis.schemas import BounceEvent, TrajectoryPoint


def point(frame: int, u: float, v: float) -> TrajectoryPoint:
    return TrajectoryPoint(
        frame_index=frame,
        timestamp_sec=frame / 30.0,
        image_xy=(float(u), float(v)),
        court_xy=None,
        confidence=0.85,
        source="detected",
    )


def bounce(frame: int, u: float, v: float) -> BounceEvent:
    return BounceEvent(
        event_id=f"bounce-{frame}",
        frame_index=frame,
        timestamp_sec=frame / 30.0,
        image_xy=(float(u), float(v)),
        court_xy=None,
        confidence=0.9,
        detection_method="test",
    )


def context_with_player1_near_hit(frame: int = 15, ts: float = 0.5):
    """P1 手腕贴近击球点且有挥拍。"""
    trajectory = PlayerTrajectoryArtifact(
        job_id="job-1",
        players={
            "Player_1": [
                PlayerTrajectorySample(
                    frame_index=frame,
                    timestamp_seconds=ts,
                    player_id="Player_1",
                    track_id=1,
                    court_x=5.0,
                    court_y=3.0,
                    court_unit="m",
                    confidence=0.9,
                    bbox=[0, 0, 80, 200],
                    image_footpoint=[40, 200],
                )
            ]
        },
    )
    pose_frames = [
        PoseOverlayFrame(
            frame_index=frame - 1,
            timestamp_seconds=ts - 1 / 30.0,
            subjects=[
                PoseSubject(
                    track_id="1",
                    bbox=[0, 0, 80, 200],
                    confidence=0.9,
                    keypoints=[PoseKeypoint(name="right_wrist", x=105, y=98, confidence=0.9, visible=True)],
                )
            ],
        ),
        PoseOverlayFrame(
            frame_index=frame,
            timestamp_seconds=ts,
            subjects=[
                PoseSubject(
                    track_id="1",
                    bbox=[0, 0, 80, 200],
                    confidence=0.9,
                    keypoints=[PoseKeypoint(name="right_wrist", x=150, y=100, confidence=0.9, visible=True)],
                )
            ],
        ),
        PoseOverlayFrame(
            frame_index=frame + 1,
            timestamp_seconds=ts + 1 / 30.0,
            subjects=[
                PoseSubject(
                    track_id="1",
                    bbox=[0, 0, 80, 200],
                    confidence=0.9,
                    keypoints=[PoseKeypoint(name="right_wrist", x=195, y=102, confidence=0.9, visible=True)],
                )
            ],
        ),
    ]
    return build_player_attribution_context(
        player_trajectories=trajectory,
        pose_frames=pose_frames,
        render_trajectory_payload={
            "players": [{"player_id": "Player_1", "render_slot": "slot_1", "initial_side": "near"}]
        },
    )


def _trajectory_with_hit_and_bounce():
    """方向反转（击球，位置贴近 P1 手腕 150,100）+ 弹地。"""
    points = []
    for i in range(40):
        if i <= 15:
            points.append(point(i, 110 + 3 * i, 60 + 3 * i))
        elif i <= 30:
            points.append(point(i, 155 - 3 * (i - 15), 105 - 2 * (i - 15)))
        else:
            points.append(point(i, 110 - 3 * (i - 30), 75 - 2 * (i - 30)))
    bounces = [bounce(22, 134.0, 91.0)]
    return points, bounces


def test_full_chain_attribution_and_shot():
    """球员上下文存在：事件带归属，段带 shot_id 与 hitter。"""
    points, bounces = _trajectory_with_hit_and_bounce()
    payload = reconstruct_ball_trajectory(
        job_id="job-e2e-1",
        cleaned_points=points,
        bounce_events=bounces,
        homography=None,
        fps=30,
        player_context=context_with_player1_near_hit(),
    )
    assert payload["status"] == "available"
    assert payload["schema_version"] == "reconstructed_ball_trajectory.v2"
    assert payload["player_roster"][0]["player_id"] == "Player_1"
    assert payload["player_roster"][0]["render_slot"] == "slot_1"

    hits = [e for e in payload["events"] if e["event_type"] == "hit"]
    assert hits
    assert hits[0]["ownership_status"] == "confirmed"
    assert hits[0]["hitter_player_id"] == "Player_1"
    assert hits[0]["attribution"]["method"] in {"pose_bbox_fused", "bbox_fused"}

    owned_segments = [s for s in payload["segments"] if s["ownership_status"] != "not_applicable"]
    assert owned_segments
    shot_ids = {s["shot_id"] for s in owned_segments}
    assert len(shot_ids) == 1
    for s in owned_segments:
        assert s["hitter_player_id"] == "Player_1"
        assert s["ownership_confidence"] is not None
        assert s["ownership_source_event_id"] is not None


def test_no_context_degrades_without_fabrication():
    """无球员上下文：仍完成切段重建，归属为 unassigned/not_applicable。"""
    points, bounces = _trajectory_with_hit_and_bounce()
    payload = reconstruct_ball_trajectory(
        job_id="job-e2e-2",
        cleaned_points=points,
        bounce_events=bounces,
        homography=None,
        fps=30,
        player_context=None,
    )
    assert payload["status"] == "available"
    assert payload["player_roster"] == []
    for segment in payload["segments"]:
        assert segment["hitter_player_id"] is None
    for event in payload["events"]:
        if event["event_type"] == "hit":
            assert event["hitter_player_id"] is None
            assert event["ownership_status"] == "unassigned"


def test_serve_seeding_end_to_end():
    """serve 事件携带 player_id：serve_reset 保留并播种 shot。"""
    points = [point(i, 100 + i * 3, 200) for i in range(30)]
    serve_events = [
        {
            "frame_index": 5,
            "timestamp_seconds": 5 / 30.0,
            "confidence": 0.9,
            "player_id": "Player_2",
        }
    ]
    payload = reconstruct_ball_trajectory(
        job_id="job-e2e-3",
        cleaned_points=points,
        bounce_events=[],
        serve_events=serve_events,
        homography=None,
        fps=30,
    )
    serves = [e for e in payload["events"] if e["event_type"] == "serve_reset"]
    assert serves
    assert serves[0]["hitter_player_id"] == "Player_2"
    assert serves[0]["ownership_status"] == "confirmed"
