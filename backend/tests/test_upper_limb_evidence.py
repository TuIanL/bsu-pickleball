"""upper_limb_evidence 共享上肢证据模块的单元测试。"""

from app.schemas.pose import PoseKeypoint, PoseOverlayFrame, PoseSubject
from app.vision.pickleball_game_analysis.upper_limb_evidence import (
    build_upper_limb_evidence_index,
    collect_upper_limb_points,
    upper_limb_motion_by_track,
)


def pose_subject(track_id, *points):
    """points: (name, x, y, confidence, visible)"""
    return PoseSubject(
        track_id=track_id,
        bbox=[0, 0, 100, 200],
        confidence=0.9,
        keypoints=[
            PoseKeypoint(name=name, x=x, y=y, confidence=conf, visible=visible) for name, x, y, conf, visible in points
        ],
    )


def frame(index, timestamp, *subjects):
    return PoseOverlayFrame(frame_index=index, timestamp_seconds=timestamp, subjects=list(subjects))


def test_motion_matches_original_semantics():
    """逐帧速度 = 相邻帧上肢关键点最大位移 / 时间差，且首帧无运动值。"""
    frames = [
        frame(0, 0.0, pose_subject("1", ("right_wrist", 10, 50, 0.9, True))),
        frame(1, 0.1, pose_subject("1", ("right_wrist", 60, 50, 0.9, True))),
        frame(2, 0.2, pose_subject("1", ("right_wrist", 60, 50, 0.9, True))),
    ]
    motion = upper_limb_motion_by_track(frames, smooth_window_frames=1)
    assert motion["1"] == {1: 500.0, 2: 0.0}
    assert 0 not in motion["1"]


def test_keypoints_preserved_in_index():
    """共享索引必须保留 wrist/elbow 坐标，而非只留运动标量。"""
    frames = [
        frame(
            0,
            0.0,
            pose_subject(
                "1",
                ("left_wrist", 1, 2, 0.9, True),
                ("right_wrist", 3, 4, 0.9, True),
                ("left_elbow", 5, 6, 0.9, True),
                ("right_elbow", 7, 8, 0.9, True),
            ),
        )
    ]
    index = build_upper_limb_evidence_index(frames, smooth_window_frames=1)
    evidence = index.evidence_for("1", 0)
    assert evidence is not None
    assert evidence.left_wrist_xy == (1, 2)
    assert evidence.right_wrist_xy == (3, 4)
    assert evidence.left_elbow_xy == (5, 6)
    assert evidence.right_elbow_xy == (7, 8)


def test_keypoint_filtering():
    """不可见或低置信度关键点必须被剔除。"""
    subject = pose_subject(
        "1",
        ("right_wrist", 1, 2, 0.9, True),
        ("left_wrist", 3, 4, 0.2, True),  # 低置信度
        ("right_elbow", 5, 6, 0.9, False),  # 不可见
        ("left_elbow", 7, 8, 0.9, True),
    )
    points = collect_upper_limb_points(subject)
    assert set(points) == {"right_wrist", "left_elbow"}


def test_motion_smoothing_centered_average():
    """滑动平均窗口前后各半，中间帧取自身与邻居均值。"""
    frames = [
        frame(0, 0.0, pose_subject("1", ("right_wrist", 0, 0, 0.9, True))),
        frame(1, 1.0, pose_subject("1", ("right_wrist", 100, 0, 0.9, True))),
        frame(2, 2.0, pose_subject("1", ("right_wrist", 100, 0, 0.9, True))),
        frame(3, 3.0, pose_subject("1", ("right_wrist", 200, 0, 0.9, True))),
    ]
    motion = upper_limb_motion_by_track(frames, smooth_window_frames=5)
    # 原始运动：帧1=100，帧2=0，帧3=100；窗口半径=2 时三者互相平均
    assert motion["1"][1] == (100.0 + 0.0 + 100.0) / 3
    assert motion["1"][2] == (100.0 + 0.0 + 100.0) / 3
    assert motion["1"][3] == (100.0 + 0.0 + 100.0) / 3


def test_missing_frames_handled():
    """缺帧（时间差 <= 0 或 dt 无变化）不产生错误运动值。"""
    frames = [
        frame(0, 0.0, pose_subject("1", ("right_wrist", 0, 0, 0.9, True))),
        frame(1, 0.0, pose_subject("1", ("right_wrist", 50, 0, 0.9, True))),  # dt=0
        frame(3, 0.4, pose_subject("1", ("right_wrist", 100, 0, 0.9, True))),
    ]
    index = build_upper_limb_evidence_index(frames, smooth_window_frames=1)
    assert index.motion_for("1", 1) is None  # dt=0 帧无运动
    assert index.motion_for("1", 3) == 125.0  # 50px / 0.4s


def test_window_query():
    """时间窗查询返回窗口内的证据且按时间升序。"""
    frames = [
        frame(0, 0.0, pose_subject("1", ("right_wrist", 0, 0, 0.9, True))),
        frame(1, 0.1, pose_subject("1", ("right_wrist", 10, 0, 0.9, True))),
        frame(2, 0.5, pose_subject("1", ("right_wrist", 20, 0, 0.9, True))),
    ]
    index = build_upper_limb_evidence_index(frames, smooth_window_frames=1)
    window = index.evidence_in_window("1", 0.05, 0.2)
    assert [e.frame_index for e in window] == [1]
    assert index.evidence_in_window("1", 0.05, 0.6) == [index.evidence_for("1", 1), index.evidence_for("1", 2)]


def test_track_key_normalization_for_queries():
    """int/str track_id 查询等价。"""
    frames = [
        frame(0, 0.0, pose_subject("17", ("right_wrist", 0, 0, 0.9, True))),
        frame(1, 0.1, pose_subject("17", ("right_wrist", 10, 0, 0.9, True))),
    ]
    index = build_upper_limb_evidence_index(frames, smooth_window_frames=1)
    assert index.motion_for(17, 1) == 100.0
    assert index.motion_for("17", 1) == 100.0
    assert index.evidence_for(17, 0) is index.evidence_for("17", 0)


def test_empty_input():
    """空输入返回空索引。"""
    index = build_upper_limb_evidence_index([], smooth_window_frames=5)
    assert index.tracks == []
    assert index.motion_by_track() == {}
    assert index.evidence_in_window("1", 0.0, 1.0) == []
