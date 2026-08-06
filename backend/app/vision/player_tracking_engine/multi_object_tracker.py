"""多目标跟踪器 —— 基于 IOU 的简单在线跟踪器，维持帧间检测框的连续性。"""

from __future__ import annotations

# dataclass：定义内部轨迹状态；Detection / Track 为检测与轨迹的数据模型。
from dataclasses import dataclass

from app.schemas.tracking import Detection, Track


@dataclass
class _TrackState:
    # 内部维护的某条轨迹状态：track_id、当前 bbox、置信度、连续未匹配帧计数（lost_count）。
    track_id: int
    bbox: list[float]
    confidence: float
    lost_count: int = 0


class MultiObjectTracker:
    """Simple IOU tracker with a replaceable detection-in / tracks-out contract."""

    def __init__(self, iou_threshold: float = 0.3, max_lost: int = 15) -> None:
        # iou_threshold：匹配所需的最小 IOU；max_lost：超过此未匹配帧数则删除轨迹。
        self.iou_threshold = iou_threshold
        self.max_lost = max_lost
        self._next_track_id = 1  # 自增分配新 track_id
        self._tracks: dict[int, _TrackState] = {}

    def update(self, detections: list[Detection]) -> list[Track]:
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        active: list[Track] = []

        # 1) 枚举所有 (检测, 轨迹) 对的 IOU，作为候选匹配。
        candidates: list[tuple[float, int, int]] = []
        for detection_index, detection in enumerate(detections):
            for track_id, state in self._tracks.items():
                candidates.append((_iou(detection.bbox, state.bbox), track_id, detection_index))

        # 2) 按 IOU 从高到低贪心匹配：IOU 低于阈值则停止；已匹配的跳过。
        candidates.sort(key=lambda item: item[0], reverse=True)
        for score, track_id, detection_index in candidates:
            if score < self.iou_threshold:
                break
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            detection = detections[detection_index]
            state = self._tracks[track_id]
            state.bbox = detection.bbox
            state.confidence = detection.confidence
            state.lost_count = 0
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)
            active.append(_state_to_track(state, lost=False))

        # 3) 未匹配到的检测视为“新目标”，分配新 track_id 并新建轨迹。
        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            state = _TrackState(track_id=track_id, bbox=detection.bbox, confidence=detection.confidence)
            self._tracks[track_id] = state
            matched_tracks.add(track_id)
            active.append(_state_to_track(state, lost=False))

        # 4) 本轮未匹配到的轨迹 lost_count+1；超过 max_lost 则彻底删除。
        for track_id in list(self._tracks):
            if track_id in matched_tracks:
                continue
            state = self._tracks[track_id]
            state.lost_count += 1
            if state.lost_count > self.max_lost:
                del self._tracks[track_id]

        # 按 track_id 升序返回当前活跃轨迹。
        active.sort(key=lambda track: track.track_id)
        return active


class EmptyTracker:
    # 空实现，用于测试或无需真实跟踪的占位场景（永远返回空列表）。
    def update(self, detections: list[Detection]) -> list[Track]:
        return []


def _state_to_track(state: _TrackState, lost: bool) -> Track:
    # 把内部 _TrackState 转成对外 Track 数据模型。
    return Track(track_id=state.track_id, bbox=state.bbox, confidence=state.confidence, lost=lost)


def _iou(a: list[float], b: list[float]) -> float:
    # 计算两个 [x1,y1,x2,y2] 框的交并比（IOU）。
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


class DuplicateTrackSuppressor:
    """抑制同一目标被跟踪器分身出的重复重叠 track（仅作用于球员路径输出）。

    当一个 track 对（如 P2 的 track 41 与其分身 track 50）bbox 重叠度超过阈值并持续
    达到连续帧数时，视为同一目标被重复跟踪，从输出中剔除较新的分身。只过滤输出、
    不改内部轨迹状态：若两目标后续分离（IoU 下降），被抑制 track 可自然重新出现。
    """

    def __init__(self, iou_threshold: float = 0.6, sustain_frames: int = 3) -> None:
        # iou_threshold：判定"同一目标"所需的最小 bbox 重叠度；
        # sustain_frames：重叠需持续的连续帧数（含 1 帧缺席容错），避免误杀真·近距离双人。
        self.iou_threshold = iou_threshold
        self.sustain_frames = sustain_frames
        self._pair_count: dict[frozenset[int], int] = {}

    def filter(self, tracks: list[Track]) -> list[Track]:
        # 两两比较当前帧活跃 track；IoU ≥ 阈值则累加该对持续重叠帧数，否则 -1（容错缺席/短暂分离）。
        # 持续 ≥ sustain_frames 时抑制对中较新的 track（track_id 较大者为分身）；
        # 仅当新 track 置信度显著更高（> 旧 + 0.15）时才反过来保留新 track。
        counts: dict[frozenset[int], int] = {}
        seen_pairs: set[frozenset[int]] = set()
        suppressed: set[int] = set()
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                a = tracks[i]
                b = tracks[j]
                iou = _iou(a.bbox, b.bbox)
                pair = frozenset({a.track_id, b.track_id})
                prev = self._pair_count.get(pair, 0)
                cur = prev + 1 if iou >= self.iou_threshold else max(0, prev - 1)
                counts[pair] = cur
                seen_pairs.add(pair)
                if cur >= self.sustain_frames:
                    older, newer = (a, b) if a.track_id < b.track_id else (b, a)
                    if newer.confidence > older.confidence + 0.15:
                        suppressed.add(older.track_id)
                    else:
                        suppressed.add(newer.track_id)
        # 本帧缺席的 track 对计数衰减 -1，而非清零，避免单帧缺口打断持续重叠累计
        for pair, prev in self._pair_count.items():
            if pair not in seen_pairs:
                counts[pair] = max(0, prev - 1)
        self._pair_count = counts
        return [track for track in tracks if track.track_id not in suppressed]


# 别名：SimpleDetectionTracker 等价于 MultiObjectTracker（保持历史/兼容命名）。
SimpleDetectionTracker = MultiObjectTracker
