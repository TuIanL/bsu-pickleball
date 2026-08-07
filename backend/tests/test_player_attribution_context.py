"""球员归属上下文（player_attribution_context）的契约测试。"""

from app.schemas.pose import PoseKeypoint, PoseOverlayFrame, PoseSubject
from app.schemas.tracking import (
    DetectionOverlayFrame,
    FrameDetection,
    PlayerTrajectoryArtifact,
    PlayerTrajectorySample,
)
from app.vision.pickleball_game_analysis.player_attribution_context import (
    build_player_attribution_context,
    normalize_track_key,
)


def sample(frame, time, x, y, *, player_id="Player_1", track_id=1):
    return PlayerTrajectorySample(
        frame_index=frame,
        timestamp_seconds=time,
        player_id=player_id,
        track_id=track_id,
        court_x=x,
        court_y=y,
        court_unit="m",
        confidence=0.9,
        bbox=[0, 0, 50, 200],
        image_footpoint=[25, 200],
    )


def pose_frame(frame, time, track_id="17"):
    return PoseOverlayFrame(
        frame_index=frame,
        timestamp_seconds=time,
        subjects=[
            PoseSubject(
                track_id=track_id,
                bbox=[0, 0, 100, 200],
                confidence=0.9,
                keypoints=[PoseKeypoint(name="right_wrist", x=10, y=10, confidence=0.9, visible=True)],
            )
        ],
    )


def test_normalize_track_key():
    assert normalize_track_key(17) == "17"
    assert normalize_track_key("17") == "17"
    assert normalize_track_key(None) is None


def test_contract_mixed_track_id_types_map_to_canonical_player():
    """PlayerTrajectorySample(track_id=17) + PoseSubject("17") + FrameDetection("17")
    均映射到 Player_2。"""
    trajectory = PlayerTrajectoryArtifact(
        job_id="job-1",
        players={"Player_2": [sample(0, 0.0, 5.0, 8.0, player_id="Player_2", track_id=17)]},
    )
    context = build_player_attribution_context(
        player_trajectories=trajectory,
        pose_frames=[pose_frame(0, 0.0)],
        overlay_frames=[
            DetectionOverlayFrame(
                frame_index=0,
                timestamp_seconds=0.0,
                detections=[
                    FrameDetection(
                        frame_index=0,
                        timestamp_seconds=0.0,
                        bbox=[0, 0, 50, 200],
                        confidence=0.9,
                        track_id="17",
                        player_id="Player_2",
                        source_width=1280,
                        source_height=720,
                    )
                ],
            )
        ],
    )
    assert context.player_id_for_track(17) == "Player_2"
    assert context.player_id_for_track("17") == "Player_2"
    assert context.player_ids == ["Player_2"]


def test_roster_render_slot():
    trajectory = PlayerTrajectoryArtifact(
        job_id="job-1",
        players={"Player_1": [sample(0, 0.0, 5.0, 3.0)]},
    )
    render_payload = {
        "players": [
            {"player_id": "Player_1", "render_slot": "slot_2", "initial_side": "near"},
        ]
    }
    context = build_player_attribution_context(
        player_trajectories=trajectory,
        render_trajectory_payload=render_payload,
    )
    assert context.render_slot_for("Player_1") == "slot_2"
    assert context.render_slot_for("Player_9") is None


def test_side_at_uses_dynamic_court_position():
    """半场按球员接触时刻球场坐标推导，而非 roster initial_side。"""
    trajectory = PlayerTrajectoryArtifact(
        job_id="job-1",
        players={
            "Player_1": [sample(0, 0.0, 3.0, 2.0)],  # 近侧（y 小）
            "Player_2": [sample(0, 0.0, 3.0, 11.0)],  # 远侧（y 大，球长 13.41m）
        },
    )
    context = build_player_attribution_context(player_trajectories=trajectory)
    assert context.side_at("Player_1", 0.0) == "near"
    assert context.side_at("Player_2", 0.0) == "far"


def test_samples_in_window():
    trajectory = PlayerTrajectoryArtifact(
        job_id="job-1",
        players={
            "Player_1": [
                sample(0, 0.0, 5.0, 3.0),
                sample(10, 0.5, 6.0, 3.0),
                sample(20, 1.0, 7.0, 3.0),
            ]
        },
    )
    context = build_player_attribution_context(player_trajectories=trajectory)
    window = context.samples_in_window("Player_1", 0.1, 0.6)
    assert [s.frame_index for s in window] == [10]
