"""共享上肢运动证据模块（upper_limb_evidence）。

从姿态帧（PoseOverlayFrame）提取每名球员（track）逐帧的腕部/肘部关键点位置
与手臂运动强度，供发球检测与击球球员归属共同消费。

与 `ServeStartDetector` 的职责边界：
  - 本模块只负责"证据索引构建与查询"，不参与任何事件判定；
  - 发球检测读取运动强度标量（行为与迁移前完全一致）；
  - 击球归属同时读取关键点坐标与运动强度。

关键点筛选规则（与迁移前一致）：仅保留可见且置信度 >= 0.25 的关键点。
运动强度定义（与迁移前一致）：相邻姿态帧之间 4 个关键点（左右手腕/左右肘）
逐点速度的最大值，再做"以自身为中心"的滑动平均平滑。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from app.schemas.pose import PoseOverlayFrame, PoseSubject

# 上肢证据使用的关键点名集合（与迁移前一致）
UPPER_LIMB_KEYPOINT_NAMES = frozenset({"left_wrist", "right_wrist", "left_elbow", "right_elbow"})

# 关键点可见且置信度达标的门槛（与迁移前一致）
KEYPOINT_MIN_CONFIDENCE = 0.25


@dataclass(frozen=True)
class UpperLimbFrameEvidence:
    """某个 track 在某一帧的上肢证据。

    坐标均为图像像素（与姿态关键点一致）；运动强度为像素/秒。
    """

    track_id: str
    frame_index: int
    timestamp_seconds: float
    left_wrist_xy: tuple[float, float] | None = None
    right_wrist_xy: tuple[float, float] | None = None
    left_elbow_xy: tuple[float, float] | None = None
    right_elbow_xy: tuple[float, float] | None = None
    arm_motion_px_per_second: float = 0.0


def collect_upper_limb_points(
    subject: PoseSubject,
    min_confidence: float = KEYPOINT_MIN_CONFIDENCE,
) -> dict[str, tuple[float, float]]:
    """从姿态对象中取出可靠的上肢关键点坐标（关键点名 -> (x, y)）。

    与迁移前 `_subject_points` 行为一致：只保留可见且置信度达标的
    左右手腕 / 左右肘。
    """
    return {
        keypoint.name: (keypoint.x, keypoint.y)
        for keypoint in subject.keypoints
        if keypoint.name in UPPER_LIMB_KEYPOINT_NAMES and keypoint.visible and keypoint.confidence >= min_confidence
    }


def _smooth_motion(motion: dict[int, float], smooth_window_frames: int) -> dict[int, float]:
    """对每帧运动强度做"以自身为中心"的滑动平均平滑。

    半径 = smooth_window_frames // 2，按帧序排序后逐点取窗口均值；
    与迁移前 `ServeStartDetector._smooth_motion` 行为一致。
    """
    if not motion:
        return {}
    items = sorted(motion.items())
    radius = max(0, smooth_window_frames // 2)
    smoothed: dict[int, float] = {}
    for index, (frame_index, _value) in enumerate(items):
        start = max(0, index - radius)
        end = min(len(items), index + radius + 1)
        values = [value for _frame, value in items[start:end]]
        smoothed[frame_index] = sum(values) / len(values)
    return smoothed


class UpperLimbEvidenceIndex:
    """上肢证据索引：按 track 组织的逐帧证据 + 运动强度查询。

    每个 track 的证据按时间升序排列，支持：
      - 按帧取运动强度（serve 检测兼容）；
      - 按时间窗取证据（击球归属用，含关键点坐标）。
    """

    def __init__(
        self,
        evidence_by_track: dict[str, list[UpperLimbFrameEvidence]],
        motion_by_track: dict[str, dict[int, float]],
    ) -> None:
        self._evidence_by_track = evidence_by_track
        self._motion_by_track = motion_by_track

    @property
    def tracks(self) -> list[str]:
        return list(self._evidence_by_track.keys())

    def motion_for(self, track_id: str | int | None, frame_index: int) -> float | None:
        """某 track 某帧的运动强度（无数据返回 None）。"""
        if track_id is None:
            return None
        track_motion = self._motion_by_track.get(str(track_id))
        if not track_motion:
            return None
        return track_motion.get(frame_index)

    def evidence_for(self, track_id: str | int | None, frame_index: int) -> UpperLimbFrameEvidence | None:
        """某 track 某帧的完整证据（无数据返回 None）。"""
        if track_id is None:
            return None
        for evidence in self._evidence_by_track.get(str(track_id), []):
            if evidence.frame_index == frame_index:
                return evidence
        return None

    def evidence_in_window(
        self,
        track_id: str | int | None,
        start_sec: float,
        end_sec: float,
    ) -> list[UpperLimbFrameEvidence]:
        """某 track 在 [start_sec, end_sec] 时间窗内的证据（按时间升序）。"""
        if track_id is None:
            return []
        return [
            evidence
            for evidence in self._evidence_by_track.get(str(track_id), [])
            if start_sec <= evidence.timestamp_seconds <= end_sec
        ]

    def motion_by_track(self) -> dict[str, dict[int, float]]:
        """兼容视图：track_id -> {frame_index: 平滑运动强度}（迁移前形状）。"""
        return self._motion_by_track


def build_upper_limb_evidence_index(
    pose_frames: list[PoseOverlayFrame],
    *,
    smooth_window_frames: int,
    min_confidence: float = KEYPOINT_MIN_CONFIDENCE,
) -> UpperLimbEvidenceIndex:
    """从姿态帧构建上肢证据索引。

    方法（与迁移前 `_pose_motion_by_track` 一致）：
      1. 提取每个 subject 的 4 个上肢关键点（可见且置信度达标）；
      2. 按帧顺序计算相邻帧之间这些关键点的平均速度，取最大值作为运动强度；
      3. 运动强度用滑动平均平滑（radius = smooth_window_frames // 2）。
    """
    raw: dict[str, list[tuple[int, float, dict[str, tuple[float, float]]]]] = {}
    for frame in pose_frames:
        for subject in frame.subjects:
            points = collect_upper_limb_points(subject, min_confidence=min_confidence)
            if points:
                raw.setdefault(subject.track_id, []).append((frame.frame_index, frame.timestamp_seconds, points))

    evidence_by_track: dict[str, list[UpperLimbFrameEvidence]] = {}
    motion_by_track: dict[str, dict[int, float]] = {}
    for track_id, items in raw.items():
        items.sort(key=lambda item: item[1])
        frame_motion: dict[int, float] = {}
        evidence_by_frame: dict[int, UpperLimbFrameEvidence] = {}
        previous: tuple[float, dict[str, tuple[float, float]]] | None = None
        for frame_index, timestamp, points in items:
            if previous is not None:
                previous_timestamp, previous_points = previous
                dt = timestamp - previous_timestamp
                if dt > 0:
                    speeds = []
                    for name, point in points.items():
                        previous_point = previous_points.get(name)
                        if previous_point is None:
                            continue
                        speeds.append(hypot(point[0] - previous_point[0], point[1] - previous_point[1]) / dt)
                    frame_motion[frame_index] = max(speeds) if speeds else 0.0
            previous = (timestamp, points)
            evidence_by_frame[frame_index] = UpperLimbFrameEvidence(
                track_id=track_id,
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                left_wrist_xy=points.get("left_wrist"),
                right_wrist_xy=points.get("right_wrist"),
                left_elbow_xy=points.get("left_elbow"),
                right_elbow_xy=points.get("right_elbow"),
            )
        smoothed = _smooth_motion(frame_motion, smooth_window_frames)
        motion_by_track[track_id] = smoothed
        for evidence in evidence_by_frame.values():
            evidence_by_frame[evidence.frame_index] = UpperLimbFrameEvidence(
                track_id=evidence.track_id,
                frame_index=evidence.frame_index,
                timestamp_seconds=evidence.timestamp_seconds,
                left_wrist_xy=evidence.left_wrist_xy,
                right_wrist_xy=evidence.right_wrist_xy,
                left_elbow_xy=evidence.left_elbow_xy,
                right_elbow_xy=evidence.right_elbow_xy,
                arm_motion_px_per_second=smoothed.get(evidence.frame_index, 0.0),
            )
        evidence_by_track[track_id] = [evidence_by_frame[frame_index] for frame_index in sorted(evidence_by_frame)]
    return UpperLimbEvidenceIndex(evidence_by_track, motion_by_track)


def upper_limb_motion_by_track(
    pose_frames: list[PoseOverlayFrame],
    *,
    smooth_window_frames: int,
    min_confidence: float = KEYPOINT_MIN_CONFIDENCE,
) -> dict[str, dict[int, float]]:
    """兼容入口：直接返回 track_id -> {frame_index: 平滑运动强度}。

    供 `ServeStartDetector._pose_motion_by_track` 迁移使用，输出形状一致。
    """
    return build_upper_limb_evidence_index(
        pose_frames,
        smooth_window_frames=smooth_window_frames,
        min_confidence=min_confidence,
    ).motion_by_track()
