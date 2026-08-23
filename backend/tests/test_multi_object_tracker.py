"""Multi-object association and duplicate suppression tests."""

from app.schemas.tracking import Detection, Track
from app.vision.player_tracking_engine.multi_object_tracker import DuplicateTrackSuppressor, MultiObjectTracker


def trk(track_id, bbox, confidence=0.7):
    return Track(track_id=track_id, bbox=bbox, confidence=confidence, lost=False)


_BBOX_A = [100, 100, 200, 300]
_BBOX_B = [110, 105, 210, 305]  # 与 A 高度重叠（IoU ≈ 0.78）


def test_duplicate_suppressor_removes_sustained_overlap_shadow():
    suppressor = DuplicateTrackSuppressor(iou_threshold=0.6, sustain_frames=3)
    out = None
    for _ in range(4):
        out = suppressor.filter([trk(41, _BBOX_A, 0.7), trk(50, _BBOX_B, 0.5)])
    assert sorted(t.track_id for t in out) == [41]  # 较新、较低置信度的分身 50 被抑制


def test_duplicate_suppressor_keeps_newer_when_clearly_better():
    suppressor = DuplicateTrackSuppressor(iou_threshold=0.6, sustain_frames=3)
    out = None
    for _ in range(4):
        # 新 track 置信度显著更高（> 旧 + 0.15）→ 保留新、抑制旧
        out = suppressor.filter([trk(41, _BBOX_A, 0.3), trk(50, _BBOX_B, 0.8)])
    assert sorted(t.track_id for t in out) == [50]


def test_duplicate_suppressor_keeps_both_below_sustain_frames():
    suppressor = DuplicateTrackSuppressor(iou_threshold=0.6, sustain_frames=5)
    out = None
    for _ in range(2):  # 只重叠 2 帧，未达 sustain_frames=5
        out = suppressor.filter([trk(41, _BBOX_A, 0.7), trk(50, _BBOX_B, 0.5)])
    assert sorted(t.track_id for t in out) == [41, 50]


def test_duplicate_suppressor_reemits_after_separation():
    suppressor = DuplicateTrackSuppressor(iou_threshold=0.6, sustain_frames=2)
    for _ in range(3):
        suppressor.filter([trk(41, _BBOX_A, 0.7), trk(50, _BBOX_B, 0.5)])  # 持续重叠 → 抑制 50

    far_bbox = [500, 100, 600, 300]  # 与 A 不再重叠
    out = suppressor.filter([trk(41, _BBOX_A, 0.7), trk(50, far_bbox, 0.5)])
    assert sorted(t.track_id for t in out) == [41]  # 分离第 1 帧计数仍 ≥ sustain，继续抑制
    out2 = suppressor.filter([trk(41, _BBOX_A, 0.7), trk(50, far_bbox, 0.5)])
    assert sorted(t.track_id for t in out2) == [41, 50]  # 连续分离后计数衰减到阈值以下，50 重新出现


def test_duplicate_suppressor_tolerates_single_frame_gap():
    # 真实分身场景常见 1 帧缺席（如 fr=1302 只有 50 没有 41）——缺席帧计数衰减而非清零
    suppressor = DuplicateTrackSuppressor(iou_threshold=0.6, sustain_frames=3)
    suppressor.filter([trk(41, _BBOX_A, 0.7), trk(50, _BBOX_B, 0.5)])  # 重叠 1
    suppressor.filter([trk(50, _BBOX_B, 0.5)])  # 缺席（仅 50）
    out = None
    for _ in range(3):
        out = suppressor.filter([trk(41, _BBOX_A, 0.7), trk(50, _BBOX_B, 0.5)])  # 重叠 2,3,4
    assert sorted(t.track_id for t in out) == [41]  # 单帧缺席不打断累计，持续达到阈值即抑制


def det(x1, y1=10, x2=None, y2=110, confidence=0.9):
    return Detection(bbox=[x1, y1, x1 + 20 if x2 is None else x2, y2], confidence=confidence)


def test_motion_tracker_preserves_ids_through_crossing_with_reversed_detection_order():
    tracker = MultiObjectTracker(iou_threshold=0.2, max_lost=3, algorithm="motion")
    first = tracker.update_with_assignments([det(0), det(80)])
    left_id, right_id = first.detection_to_track[0], first.detection_to_track[1]
    tracker.update_with_assignments([det(20), det(60)])
    crossing = tracker.update_with_assignments([det(44), det(36)])
    assert crossing.detection_to_track[1] == left_id
    assert crossing.detection_to_track[0] == right_id
    separated = tracker.update_with_assignments([det(58), det(22)])
    assert separated.detection_to_track[0] == left_id
    assert separated.detection_to_track[1] == right_id


def test_motion_tracker_reacquires_original_id_after_short_occlusion():
    tracker = MultiObjectTracker(iou_threshold=0.2, max_lost=3, algorithm="motion")
    track_id = tracker.update_with_assignments([det(0)]).detection_to_track[0]
    tracker.update_with_assignments([det(10)])
    tracker.update_with_assignments([])
    recovered = tracker.update_with_assignments([det(29)])
    assert recovered.detection_to_track[0] == track_id


def test_motion_tracker_rejects_implausible_scale_jump():
    tracker = MultiObjectTracker(iou_threshold=0.2, max_lost=3, algorithm="motion")
    original = tracker.update_with_assignments([det(10)]).detection_to_track[0]
    update = tracker.update_with_assignments([det(0, 0, 200, 500)])
    assert update.detection_to_track[0] != original


def test_motion_tracker_assignment_is_deterministic_and_one_to_one():
    sequence = [[det(0), det(80)], [det(15), det(65)], [det(30), det(50), det(31)]]
    results = []
    for _ in range(2):
        tracker = MultiObjectTracker(iou_threshold=0.2, algorithm="motion")
        results.append([tracker.update_with_assignments(frame).detection_to_track for frame in sequence])
    assert results[0] == results[1]
    assert len(set(results[0][-1].values())) == len(results[0][-1])


def test_legacy_feature_flag_and_signature_are_explicit():
    legacy = MultiObjectTracker(algorithm="legacy")
    motion = MultiObjectTracker(algorithm="motion")
    assert legacy.config_signature != motion.config_signature
    assert legacy.update_with_assignments([det(0)]).detection_to_track == {0: 1}
