"""BallHitPlayerAttributor 击球球员归属测试。"""

from app.schemas.pose import PoseKeypoint, PoseOverlayFrame, PoseSubject
from app.schemas.tracking import (
    PlayerTrajectoryArtifact,
    PlayerTrajectorySample,
)
from app.vision.pickleball_game_analysis.ball_event_resolver import PrefilteredHitCandidate
from app.vision.pickleball_game_analysis.ball_hit_player_attributor import (
    BallHitPlayerAttributor,
    serve_seeded_attribution,
)
from app.vision.pickleball_game_analysis.player_attribution_context import (
    build_player_attribution_context,
)


def sample(frame, time, x, y, *, player_id, track_id, bbox=None):
    return PlayerTrajectorySample(
        frame_index=frame,
        timestamp_seconds=time,
        player_id=player_id,
        track_id=track_id,
        court_x=x,
        court_y=y,
        court_unit="m",
        confidence=0.9,
        bbox=bbox or [0, 0, 80, 200],
        image_footpoint=[40, 200],
    )


def subject(track_id, wrist_x, wrist_y, motion=None, frame=0, time=0.0, wrist_dx=0.0):
    return PoseSubject(
        track_id=track_id,
        bbox=[0, 0, 100, 200],
        confidence=0.9,
        keypoints=[
            PoseKeypoint(name="right_wrist", x=wrist_x, y=wrist_y, confidence=0.9, visible=True),
            PoseKeypoint(name="left_wrist", x=wrist_x + wrist_dx, y=wrist_y, confidence=0.9, visible=True),
            PoseKeypoint(name="right_elbow", x=wrist_x - 30, y=wrist_y + 20, confidence=0.9, visible=True),
            PoseKeypoint(name="left_elbow", x=wrist_x + 30, y=wrist_y + 20, confidence=0.9, visible=True),
        ],
    )


def candidate(frame=100, timestamp=3.33, xy=(100.0, 100.0)):
    return PrefilteredHitCandidate(
        candidate_id="hit-cand-1",
        frame_index=frame,
        timestamp_sec=timestamp,
        image_xy=xy,
        ball_evidence_confidence=0.8,
        prefilter_status="survived",
    )


def make_context(player_poses, player_samples, render_players=None):
    trajectory = PlayerTrajectoryArtifact(job_id="job-1", players=player_samples)
    return build_player_attribution_context(
        player_trajectories=trajectory,
        pose_frames=player_poses,
        render_trajectory_payload={"players": render_players or []},
    )


def test_wrist_near_plus_motion_peak_confirms_player():
    """P1 手腕靠近球且有挥拍峰值 → confirmed Player_1。"""
    # P1: 球(100,100) 附近手腕，且相邻帧有大幅运动（挥拍）
    p1_frames = [
        PoseOverlayFrame(frame_index=95, timestamp_seconds=3.20, subjects=[subject("1", 30, 30)]),
        PoseOverlayFrame(frame_index=100, timestamp_seconds=3.33, subjects=[subject("1", 110, 100)]),
        PoseOverlayFrame(frame_index=101, timestamp_seconds=3.36, subjects=[subject("1", 180, 170)]),
    ]
    # P2: 手腕在远处（300, 300），几乎不动
    p2_frames = [
        PoseOverlayFrame(frame_index=95, timestamp_seconds=3.20, subjects=[subject("2", 300, 300)]),
        PoseOverlayFrame(frame_index=100, timestamp_seconds=3.33, subjects=[subject("2", 301, 301)]),
        PoseOverlayFrame(frame_index=101, timestamp_seconds=3.36, subjects=[subject("2", 302, 302)]),
    ]
    context = make_context(
        p1_frames + p2_frames,
        {
            "Player_1": [sample(100, 3.33, 5.0, 3.0, player_id="Player_1", track_id=1)],
            "Player_2": [sample(100, 3.33, 5.0, 11.0, player_id="Player_2", track_id=2)],
        },
    )
    attributor = BallHitPlayerAttributor()
    result = attributor.attribute([candidate()], context)
    attribution = result["hit-cand-1"]
    assert attribution.status == "confirmed"
    assert attribution.player_id == "Player_1"


def test_net_two_players_wrist_motion_discriminates():
    """网前 P1/P2 距离很近，但 P2 腕部运动更强 → 归属 Player_2，而非最近框。"""
    # 两人 bbox 几乎重叠；P2 手腕贴球且有大幅挥拍，P1 手腕在旁侧静止
    p1_frames = [
        PoseOverlayFrame(frame_index=99, timestamp_seconds=3.30, subjects=[subject("1", 150, 150)]),
        PoseOverlayFrame(frame_index=100, timestamp_seconds=3.33, subjects=[subject("1", 151, 151)]),
        PoseOverlayFrame(frame_index=101, timestamp_seconds=3.36, subjects=[subject("1", 152, 152)]),
    ]
    p2_frames = [
        PoseOverlayFrame(frame_index=99, timestamp_seconds=3.30, subjects=[subject("2", 110, 100)]),
        PoseOverlayFrame(frame_index=100, timestamp_seconds=3.33, subjects=[subject("2", 150, 100)]),
        PoseOverlayFrame(frame_index=101, timestamp_seconds=3.36, subjects=[subject("2", 190, 100)]),
    ]
    context = make_context(
        p1_frames + p2_frames,
        {
            "Player_1": [sample(100, 3.33, 5.0, 3.0, player_id="Player_1", track_id=1)],
            "Player_2": [sample(100, 3.33, 5.1, 3.1, player_id="Player_2", track_id=2)],
        },
    )
    attributor = BallHitPlayerAttributor()
    result = attributor.attribute([candidate()], context)
    attribution = result["hit-cand-1"]
    assert attribution.player_id == "Player_2"
    assert attribution.status == "confirmed"


def test_close_evidence_ambiguous():
    """两名球员证据接近 → ambiguous，不强制归属。"""
    # P1 与 P2 手腕都贴近球、运动强度相近
    p1_frames = [
        PoseOverlayFrame(frame_index=99, timestamp_seconds=3.30, subjects=[subject("1", 95, 98)]),
        PoseOverlayFrame(frame_index=100, timestamp_seconds=3.33, subjects=[subject("1", 120, 100)]),
        PoseOverlayFrame(frame_index=101, timestamp_seconds=3.36, subjects=[subject("1", 145, 102)]),
    ]
    p2_frames = [
        PoseOverlayFrame(frame_index=99, timestamp_seconds=3.30, subjects=[subject("2", 98, 95)]),
        PoseOverlayFrame(frame_index=100, timestamp_seconds=3.33, subjects=[subject("2", 123, 97)]),
        PoseOverlayFrame(frame_index=101, timestamp_seconds=3.36, subjects=[subject("2", 148, 99)]),
    ]
    context = make_context(
        p1_frames + p2_frames,
        {
            "Player_1": [sample(100, 3.33, 5.0, 3.0, player_id="Player_1", track_id=1)],
            "Player_2": [sample(100, 3.33, 5.1, 3.1, player_id="Player_2", track_id=2)],
        },
    )
    attributor = BallHitPlayerAttributor()
    result = attributor.attribute([candidate()], context)
    attribution = result["hit-cand-1"]
    assert attribution.status == "ambiguous"
    assert attribution.player_id is None


def test_bbox_only_degradation():
    """无姿态数据但检测框明确 → bbox 降级仍可归属。"""
    context = make_context(
        [],
        {
            "Player_1": [sample(100, 3.33, 5.0, 3.0, player_id="Player_1", track_id=1, bbox=[60, 40, 140, 160])],
            "Player_2": [sample(100, 3.33, 5.0, 11.0, player_id="Player_2", track_id=2, bbox=[400, 40, 480, 160])],
        },
    )
    attributor = BallHitPlayerAttributor()
    result = attributor.attribute([candidate(xy=(100.0, 100.0))], context)
    attribution = result["hit-cand-1"]
    assert attribution.status == "confirmed"
    assert attribution.player_id == "Player_1"
    assert attribution.method == "bbox_fused"


def test_no_evidence_unassigned():
    """无球员证据 → unassigned，不强制选择。"""
    context = build_player_attribution_context(player_trajectories=None)
    attributor = BallHitPlayerAttributor()
    result = attributor.attribute([candidate()], context)
    attribution = result["hit-cand-1"]
    assert attribution.status == "unassigned"
    assert attribution.player_id is None


def test_track_switch_keeps_canonical_player():
    """球员中途更换底层 track_id：归属仍保持 canonical Player_1（I4 / I9）。"""
    # P1 前半段 track=1，后半段 track=9；击球窗口内只有 track 9 有姿态证据
    trajectory = PlayerTrajectoryArtifact(
        job_id="job-1",
        players={
            "Player_1": [
                sample(80, 2.66, 5.0, 3.0, player_id="Player_1", track_id=1),
                sample(100, 3.33, 5.0, 3.0, player_id="Player_1", track_id=9),
            ],
            "Player_2": [sample(100, 3.33, 5.0, 11.0, player_id="Player_2", track_id=2, bbox=[300, 300, 380, 500])],
        },
    )
    pose_frames = [
        PoseOverlayFrame(frame_index=99, timestamp_seconds=3.30, subjects=[subject("9", 100, 98)]),
        PoseOverlayFrame(frame_index=100, timestamp_seconds=3.33, subjects=[subject("9", 130, 100)]),
        PoseOverlayFrame(frame_index=101, timestamp_seconds=3.36, subjects=[subject("9", 160, 102)]),
    ]
    context = build_player_attribution_context(
        player_trajectories=trajectory,
        pose_frames=pose_frames,
    )
    attributor = BallHitPlayerAttributor()
    result = attributor.attribute([candidate()], context)
    attribution = result["hit-cand-1"]
    assert attribution.status == "confirmed"
    assert attribution.player_id == "Player_1"


def test_serve_seeded():
    """serve 播种直接归属，method = serve_seeded。"""
    context = build_player_attribution_context(player_trajectories=None)
    attribution = serve_seeded_attribution(candidate(), "Player_3", context)
    assert attribution.status == "confirmed"
    assert attribution.player_id == "Player_3"
    assert attribution.method == "serve_seeded"
    assert attribution.confidence == 1.0
