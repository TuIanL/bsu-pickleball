"""多目标跟踪器测试 —— 重复重叠 track 抑制（同一目标分身去重）。"""

from app.schemas.tracking import Track
from app.vision.player_tracking_engine.multi_object_tracker import DuplicateTrackSuppressor


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
