"""MVP 发球开始候选检测器。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import hypot

from app.schemas.events import ServeEventCandidate, ServeEventsArtifact
from app.schemas.pose import PoseOverlayFrame
from app.schemas.tracking import PlayerTrajectoryArtifact, TrackingResult


@dataclass(frozen=True)
class ServeStartDetectorConfig:
    min_gap_seconds: float = 6.0
    pre_roll_seconds: float = 1.5
    min_confidence: float = 0.35
    still_speed_threshold: float = 0.8
    burst_speed_threshold: float = 2.2
    stable_window: int = 2


class ServeStartDetector:
    version = "serve-start-mvp-v1"

    def __init__(self, config: ServeStartDetectorConfig | None = None) -> None:
        self.config = config or ServeStartDetectorConfig()

    def detect(
        self,
        *,
        job_id: str,
        video_id: str | None,
        tracking: TrackingResult | None = None,
        player_trajectories: PlayerTrajectoryArtifact | None = None,
        pose_frames: list[PoseOverlayFrame] | None = None,
    ) -> ServeEventsArtifact:
        tracking_frames = tracking.overlay_frames if tracking else []
        pose_count = sum(len(frame.subjects) for frame in (pose_frames or []))
        duration_seconds = self._duration_seconds(tracking)
        if not tracking or tracking.processed_frame_count == 0:
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="unavailable",
                detail="缺少可用 tracking 帧，无法识别发球开始候选点",
                tracking=tracking,
                duration_seconds=duration_seconds,
            )

        samples_by_player = self._trajectory_samples(player_trajectories)
        if samples_by_player:
            events = self._events_from_trajectories(samples_by_player, pose_available=pose_count > 0)
            status = "available" if pose_count > 0 else "partial"
            detail = (
                f"已基于球员轨迹{'和姿态' if pose_count > 0 else ''}识别 {len(events)} 个发球开始候选点"
                if events
                else "检测器已运行，但没有达到阈值的发球开始候选点"
            )
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status=status if events else "no_candidates",
                detail=detail,
                tracking=tracking,
                duration_seconds=duration_seconds,
                events=events,
            )

        events = self._events_from_tracking_frames(tracking_frames, pose_available=pose_count > 0)
        if events:
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="partial",
                detail=f"已基于人体框动态识别 {len(events)} 个低信息量发球开始候选点",
                tracking=tracking,
                duration_seconds=duration_seconds,
                events=events,
            )

        return self._artifact(
            job_id=job_id,
            video_id=video_id,
            status="no_candidates",
            detail="检测器已运行，但没有达到阈值的发球开始候选点",
            tracking=tracking,
            duration_seconds=duration_seconds,
        )

    def unavailable(
        self,
        *,
        job_id: str,
        video_id: str | None,
        detail: str,
    ) -> ServeEventsArtifact:
        return self._artifact(job_id=job_id, video_id=video_id, status="unavailable", detail=detail)

    def _events_from_trajectories(self, samples_by_player, *, pose_available: bool) -> list[ServeEventCandidate]:
        candidates: list[ServeEventCandidate] = []
        for player_id, samples in samples_by_player.items():
            if len(samples) < self.config.stable_window + 2:
                continue
            for index in range(self.config.stable_window, len(samples) - 1):
                previous = samples[index - self.config.stable_window:index]
                current = samples[index]
                next_sample = samples[index + 1]
                previous_speeds = [self._sample_speed(a, b) for a, b in zip(previous, previous[1:] + [current])]
                burst_speed = self._sample_speed(current, next_sample)
                if not previous_speeds:
                    continue
                still_speed = max(previous_speeds)
                if still_speed > self.config.still_speed_threshold or burst_speed < self.config.burst_speed_threshold:
                    continue
                confidence = min(0.92, 0.48 + burst_speed * 0.08 + (0.1 if pose_available else 0))
                if confidence < self.config.min_confidence:
                    continue
                candidates.append(
                    self._candidate(
                        index=len(candidates) + 1,
                        timestamp=current.timestamp_seconds,
                        frame_index=current.frame_index,
                        confidence=confidence,
                        reason=f"{player_id} 稳定站位后出现移动速度突增",
                        source_signals=["trajectory", "tracking"] + (["pose"] if pose_available else []),
                        track_id=str(current.track_id) if current.track_id is not None else None,
                        player_id=player_id,
                    )
                )
        return self._dedupe(candidates)

    def _events_from_tracking_frames(self, frames, *, pose_available: bool) -> list[ServeEventCandidate]:
        by_track = defaultdict(list)
        for frame in frames:
            for detection in frame.detections:
                if detection.track_id is None:
                    continue
                x1, y1, x2, y2 = detection.bbox
                by_track[detection.track_id].append(
                    (frame.frame_index, frame.timestamp_seconds, (x1 + x2) / 2, (y1 + y2) / 2, detection.player_id)
                )

        candidates: list[ServeEventCandidate] = []
        for track_id, points in by_track.items():
            points.sort(key=lambda item: item[1])
            if len(points) < 3:
                continue
            for previous, current, next_point in zip(points, points[1:], points[2:]):
                still_speed = self._point_speed(previous, current)
                burst_speed = self._point_speed(current, next_point)
                if still_speed > 25.0 or burst_speed < 45.0:
                    continue
                confidence = min(0.68, 0.38 + burst_speed / 500 + (0.08 if pose_available else 0))
                candidates.append(
                    self._candidate(
                        index=len(candidates) + 1,
                        timestamp=current[1],
                        frame_index=current[0],
                        confidence=confidence,
                        reason=f"Track {track_id} 人体框短暂稳定后出现位置突变",
                        source_signals=["tracking"] + (["pose"] if pose_available else []),
                        track_id=str(track_id),
                        player_id=current[4],
                    )
                )
        return self._dedupe(candidates)

    def _candidate(
        self,
        *,
        index: int,
        timestamp: float,
        frame_index: int,
        confidence: float,
        reason: str,
        source_signals: list,
        track_id: str | None = None,
        player_id: str | None = None,
    ) -> ServeEventCandidate:
        timestamp = max(0.0, float(timestamp))
        return ServeEventCandidate(
            id=f"serve-{index:03d}",
            timestamp_seconds=timestamp,
            frame_index=frame_index,
            confidence=round(confidence, 3),
            seek_time_seconds=max(0.0, timestamp - self.config.pre_roll_seconds),
            reason=reason,
            source_signals=source_signals,
            track_id=track_id,
            player_id=player_id,
        )

    def _dedupe(self, candidates: list[ServeEventCandidate]) -> list[ServeEventCandidate]:
        result: list[ServeEventCandidate] = []
        for candidate in sorted(candidates, key=lambda item: (-item.confidence, item.timestamp_seconds)):
            if any(abs(candidate.timestamp_seconds - existing.timestamp_seconds) < self.config.min_gap_seconds for existing in result):
                continue
            result.append(candidate)
        result.sort(key=lambda item: item.timestamp_seconds)
        return [candidate.model_copy(update={"id": f"serve-{index:03d}"}) for index, candidate in enumerate(result, start=1)]

    @staticmethod
    def _trajectory_samples(player_trajectories: PlayerTrajectoryArtifact | None):
        if player_trajectories is None:
            return {}
        return {
            player_id: sorted(
                [sample for sample in samples if not sample.is_interpolated],
                key=lambda sample: sample.timestamp_seconds,
            )
            for player_id, samples in player_trajectories.players.items()
            if samples
        }

    @staticmethod
    def _sample_speed(current, next_sample) -> float:
        dt = next_sample.timestamp_seconds - current.timestamp_seconds
        if dt <= 0:
            return 0.0
        return hypot(next_sample.court_x - current.court_x, next_sample.court_y - current.court_y) / dt

    @staticmethod
    def _point_speed(current, next_point) -> float:
        dt = next_point[1] - current[1]
        if dt <= 0:
            return 0.0
        return hypot(next_point[2] - current[2], next_point[3] - current[3]) / dt

    @staticmethod
    def _duration_seconds(tracking: TrackingResult | None) -> float | None:
        if tracking is None:
            return None
        if tracking.fps > 0 and tracking.frame_count > 0:
            return tracking.frame_count / tracking.fps
        timestamps = [frame.timestamp_seconds for frame in tracking.overlay_frames]
        return max(timestamps) if timestamps else None

    def _artifact(
        self,
        *,
        job_id: str,
        video_id: str | None,
        status: str,
        detail: str,
        tracking: TrackingResult | None = None,
        duration_seconds: float | None = None,
        events: list[ServeEventCandidate] | None = None,
    ) -> ServeEventsArtifact:
        return ServeEventsArtifact(
            job_id=job_id,
            video_id=video_id,
            status=status,
            detail=detail,
            detector_version=self.version,
            duration_seconds=duration_seconds,
            fps=tracking.fps if tracking else 0.0,
            frame_count=tracking.frame_count if tracking else 0,
            processed_frame_count=tracking.processed_frame_count if tracking else 0,
            frame_stride=tracking.frame_stride if tracking else 1,
            events=events or [],
        )
