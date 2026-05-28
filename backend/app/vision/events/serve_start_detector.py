"""上下文发球时刻候选检测器。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import hypot
from typing import Any

from app.schemas.events import (
    ServeDebugArtifactRefs,
    ServeEventCandidate,
    ServeEventsArtifact,
    ServeSignal,
    ServeSignalScores,
)
from app.schemas.pose import PoseOverlayFrame, PoseSubject
from app.schemas.tracking import PlayerTrajectoryArtifact, PlayerTrajectorySample, TrackingResult
from app.vision.courtvision_calibration_engine.court_units import (
    court_dimensions_for_unit,
    feet_value_for_unit,
    normalize_court_unit,
)


@dataclass(frozen=True)
class ServeStartDetectorConfig:
    min_gap_seconds: float = 6.0
    pre_roll_seconds: float = 1.5
    min_confidence: float = 0.35
    baseline_margin_ft: float = 6.0
    pre_still_window_seconds: float = 1.5
    pre_still_gap_seconds: float = 0.2
    post_rally_window_seconds: float = 3.0
    still_speed_threshold: float = 0.8
    rally_speed_threshold: float = 0.9
    arm_speed_peak_threshold: float = 120.0
    roi_speed_peak_threshold: float = 30.0
    pose_smooth_window_frames: int = 5
    clip_pre_seconds: float = 2.0
    clip_post_seconds: float = 4.0


@dataclass
class ServeDetectionDebug:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    score_series: list[dict[str, Any]] = field(default_factory=list)
    thresholds: dict[str, Any] = field(default_factory=dict)
    debug_artifacts: ServeDebugArtifactRefs | None = None


@dataclass(frozen=True)
class _CourtContext:
    unit: str
    width: float
    length: float
    baseline_margin: float


@dataclass
class _CandidateDraft:
    sample: PlayerTrajectorySample
    confidence: float
    reason: str
    source_signals: list[ServeSignal]
    detection_mode: str
    signals: ServeSignalScores


class ServeStartDetector:
    version = "serve-moment-context-v1"

    def __init__(self, config: ServeStartDetectorConfig | None = None) -> None:
        self.config = config or ServeStartDetectorConfig()
        self.last_debug = ServeDetectionDebug()

    def detect(
        self,
        *,
        job_id: str,
        video_id: str | None,
        tracking: TrackingResult | None = None,
        player_trajectories: PlayerTrajectoryArtifact | None = None,
        pose_frames: list[PoseOverlayFrame] | None = None,
        debug_artifacts: ServeDebugArtifactRefs | None = None,
    ) -> ServeEventsArtifact:
        self.last_debug = ServeDetectionDebug(debug_artifacts=debug_artifacts)
        duration_seconds = self._duration_seconds(tracking)
        if not tracking or tracking.processed_frame_count == 0:
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="unavailable",
                detail="缺少可用 tracking 帧，无法识别发球时刻候选",
                tracking=tracking,
                duration_seconds=duration_seconds,
            )

        samples_by_player = self._trajectory_samples(player_trajectories)
        court_context = self._court_context(player_trajectories)
        if samples_by_player and court_context is None:
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="unavailable",
                detail="缺少或无法识别 court_unit，无法安全应用底线阈值",
                tracking=tracking,
                duration_seconds=duration_seconds,
                debug_artifacts=debug_artifacts,
            )

        pose_by_track = self._pose_motion_by_track(pose_frames or [])
        if samples_by_player and court_context is not None:
            drafts = self._drafts_from_context(samples_by_player, court_context, pose_by_track)
            events = self._dedupe([self._candidate(index + 1, draft, duration_seconds) for index, draft in enumerate(drafts)])
            detection_mode = self._artifact_detection_mode(events)
            status = "available" if events and any(event.detection_mode == "pose" for event in events) else "partial" if events else "no_candidates"
            detail = (
                f"已基于底线站位、发球前静止、局部运动峰值和后续回合状态识别 {len(events)} 个发球时刻候选"
                if events
                else "上下文发球检测已运行，但没有达到阈值的发球时刻候选"
            )
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status=status,
                detail=detail,
                tracking=tracking,
                duration_seconds=duration_seconds,
                events=events,
                detection_mode=detection_mode,
                available_signals=self._available_signals(events, pose_available=bool(pose_by_track)),
                debug_artifacts=debug_artifacts,
            )

        events = self._events_from_tracking_frames(tracking.overlay_frames, pose_available=bool(pose_by_track))
        if events:
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="partial",
                detail=f"缺少可用球员轨迹，已基于人体框动态识别 {len(events)} 个低信息量发球时刻候选",
                tracking=tracking,
                duration_seconds=duration_seconds,
                events=events,
                detection_mode="tracking",
                available_signals=["tracking"] + (["pose"] if pose_by_track else []),
                debug_artifacts=debug_artifacts,
            )

        return self._artifact(
            job_id=job_id,
            video_id=video_id,
            status="no_candidates",
            detail="上下文发球检测已运行，但没有达到阈值的发球时刻候选",
            tracking=tracking,
            duration_seconds=duration_seconds,
            debug_artifacts=debug_artifacts,
        )

    def unavailable(
        self,
        *,
        job_id: str,
        video_id: str | None,
        detail: str,
    ) -> ServeEventsArtifact:
        return self._artifact(job_id=job_id, video_id=video_id, status="unavailable", detail=detail)

    def _drafts_from_context(
        self,
        samples_by_player: dict[str, list[PlayerTrajectorySample]],
        court: _CourtContext,
        pose_by_track: dict[str, dict[int, float]],
    ) -> list[_CandidateDraft]:
        drafts: list[_CandidateDraft] = []
        for player_id, samples in samples_by_player.items():
            if len(samples) < 3:
                continue
            for index, sample in enumerate(samples):
                baseline_score = self._baseline_position_score(sample, court)
                if baseline_score <= 0:
                    self._record_rejection(sample, "not_near_baseline", baseline_position_score=baseline_score)
                    continue
                pre_stillness_score = self._pre_stillness_score(samples, index)
                if pre_stillness_score < 0.55:
                    self._record_rejection(
                        sample,
                        "missing_pre_serve_stillness",
                        baseline_position_score=baseline_score,
                        pre_stillness_score=pre_stillness_score,
                    )
                    continue
                arm_score = self._pose_peak_score(sample, pose_by_track)
                roi_score = self._trajectory_peak_score(samples, index)
                rally_score = self._rally_after_score(samples_by_player, sample.timestamp_seconds)
                receiver_score = self._receiver_waiting_score(samples_by_player, sample.timestamp_seconds, player_id)
                peak_score = max(arm_score, roi_score)
                if peak_score < 0.35:
                    self._record_rejection(
                        sample,
                        "no_local_motion_peak",
                        baseline_position_score=baseline_score,
                        pre_stillness_score=pre_stillness_score,
                        arm_motion_peak_score=arm_score,
                        roi_motion_peak_score=roi_score,
                    )
                    continue
                confidence = min(
                    0.96,
                    0.18
                    + baseline_score * 0.12
                    + pre_stillness_score * 0.18
                    + peak_score * 0.38
                    + rally_score * 0.18
                    + receiver_score * 0.06,
                )
                if rally_score <= 0:
                    confidence = min(confidence, 0.68)
                elif rally_score < 0.5:
                    confidence = min(confidence, 0.78)
                if confidence < self.config.min_confidence:
                    self._record_rejection(sample, "low_confidence", confidence=confidence)
                    continue
                detection_mode = "pose" if arm_score >= roi_score and arm_score > 0 else "roi" if roi_score > 0 else "trajectory"
                signals = ServeSignalScores(
                    baseline_position_score=round(baseline_score, 3),
                    pre_stillness_score=round(pre_stillness_score, 3),
                    arm_motion_peak_score=round(arm_score, 3),
                    roi_motion_peak_score=round(roi_score, 3),
                    rally_after_score=round(rally_score, 3),
                    receiver_waiting_score=round(receiver_score, 3),
                )
                source_signals: list[ServeSignal] = ["trajectory", "tracking"]
                if arm_score > 0:
                    source_signals.append("pose")
                if detection_mode == "roi":
                    source_signals.append("roi")
                reason = self._candidate_reason(player_id, detection_mode, signals)
                draft = _CandidateDraft(
                    sample=sample,
                    confidence=confidence,
                    reason=reason,
                    source_signals=source_signals,
                    detection_mode=detection_mode,
                    signals=signals,
                )
                drafts.append(draft)
                self._record_candidate(draft)
                self.last_debug.score_series.append(
                    {
                        "timestamp_seconds": round(sample.timestamp_seconds, 3),
                        "frame_index": sample.frame_index,
                        "player_id": player_id,
                        "baseline_position_score": signals.baseline_position_score,
                        "pre_stillness_score": signals.pre_stillness_score,
                        "arm_motion_peak_score": signals.arm_motion_peak_score,
                        "roi_motion_peak_score": signals.roi_motion_peak_score,
                        "rally_after_score": signals.rally_after_score,
                        "receiver_waiting_score": signals.receiver_waiting_score,
                        "confidence": round(confidence, 3),
                    }
                )
        self.last_debug.thresholds = {
            "baseline_margin": court.baseline_margin,
            "court_unit": court.unit,
            "court_width": court.width,
            "court_length": court.length,
            "pre_still_window_seconds": self.config.pre_still_window_seconds,
            "post_rally_window_seconds": self.config.post_rally_window_seconds,
            "min_gap_seconds": self.config.min_gap_seconds,
        }
        return drafts

    def _candidate(self, index: int, draft: _CandidateDraft, duration_seconds: float | None) -> ServeEventCandidate:
        sample = draft.sample
        timestamp = max(0.0, float(sample.timestamp_seconds))
        start_time = max(0.0, timestamp - self.config.clip_pre_seconds)
        end_time = timestamp + self.config.clip_post_seconds
        if duration_seconds is not None:
            end_time = min(duration_seconds, end_time)
        return ServeEventCandidate(
            id=f"serve-{index:03d}",
            timestamp_seconds=timestamp,
            frame_index=sample.frame_index,
            confidence=round(draft.confidence, 3),
            seek_time_seconds=max(0.0, timestamp - self.config.pre_roll_seconds),
            start_time_seconds=start_time,
            end_time_seconds=max(timestamp, end_time),
            reason=draft.reason,
            source_signals=draft.source_signals,
            track_id=str(sample.track_id) if sample.track_id is not None else None,
            player_id=sample.player_id,
            detection_mode=draft.detection_mode,  # type: ignore[arg-type]
            context_state="ready_to_serve",
            court_position=[round(sample.court_x, 4), round(sample.court_y, 4)],
            court_unit=sample.court_unit,
            signals=draft.signals,
        )

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
                if still_speed > 25.0 or burst_speed < self.config.roi_speed_peak_threshold:
                    continue
                roi_score = self._clamp01(burst_speed / max(1.0, self.config.roi_speed_peak_threshold * 2))
                confidence = min(0.68, 0.34 + roi_score * 0.26 + (0.08 if pose_available else 0))
                candidates.append(
                    ServeEventCandidate(
                        id=f"serve-{len(candidates) + 1:03d}",
                        timestamp_seconds=current[1],
                        frame_index=current[0],
                        confidence=round(confidence, 3),
                        seek_time_seconds=max(0.0, current[1] - self.config.pre_roll_seconds),
                        start_time_seconds=max(0.0, current[1] - self.config.clip_pre_seconds),
                        end_time_seconds=current[1] + self.config.clip_post_seconds,
                        reason=f"Track {track_id} 人体框短暂稳定后出现局部运动峰值",
                        source_signals=["tracking"] + (["pose"] if pose_available else []),
                        track_id=str(track_id),
                        player_id=current[4],
                        detection_mode="tracking",
                        context_state="candidate",
                        signals=ServeSignalScores(roi_motion_peak_score=round(roi_score, 3)),
                    )
                )
        return self._dedupe(candidates)

    def _dedupe(self, candidates: list[ServeEventCandidate]) -> list[ServeEventCandidate]:
        result: list[ServeEventCandidate] = []
        for candidate in sorted(candidates, key=lambda item: (-item.confidence, item.timestamp_seconds)):
            if any(abs(candidate.timestamp_seconds - existing.timestamp_seconds) < self.config.min_gap_seconds for existing in result):
                continue
            result.append(candidate)
        result.sort(key=lambda item: item.timestamp_seconds)
        return [candidate.model_copy(update={"id": f"serve-{index:03d}"}) for index, candidate in enumerate(result, start=1)]

    def _court_context(self, player_trajectories: PlayerTrajectoryArtifact | None) -> _CourtContext | None:
        if player_trajectories is None:
            return None
        unit = normalize_court_unit(player_trajectories.court.court_unit)
        dimensions = court_dimensions_for_unit(unit)
        margin = feet_value_for_unit(self.config.baseline_margin_ft, unit)
        if unit is None or dimensions is None or margin is None:
            return None
        return _CourtContext(unit=unit, width=dimensions[0], length=dimensions[1], baseline_margin=margin)

    @staticmethod
    def _trajectory_samples(player_trajectories: PlayerTrajectoryArtifact | None) -> dict[str, list[PlayerTrajectorySample]]:
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

    def _baseline_position_score(self, sample: PlayerTrajectorySample, court: _CourtContext) -> float:
        distance = min(abs(sample.court_y), abs(court.length - sample.court_y))
        if distance > court.baseline_margin:
            return 0.0
        return self._clamp01(1.0 - distance / max(0.001, court.baseline_margin))

    def _pre_stillness_score(self, samples: list[PlayerTrajectorySample], index: int) -> float:
        current = samples[index]
        start = current.timestamp_seconds - self.config.pre_still_window_seconds
        end = current.timestamp_seconds - self.config.pre_still_gap_seconds
        window = [sample for sample in samples[: index + 1] if start <= sample.timestamp_seconds <= end]
        if len(window) < 2 and index >= 2:
            window = samples[max(0, index - 2):index]
        if len(window) < 2:
            return 0.0
        speeds = [self._sample_speed(a, b) for a, b in zip(window, window[1:])]
        if not speeds:
            return 0.0
        mean_speed = sum(speeds) / len(speeds)
        return self._clamp01(1.0 - mean_speed / max(0.001, self.config.still_speed_threshold))

    def _trajectory_peak_score(self, samples: list[PlayerTrajectorySample], index: int) -> float:
        if index >= len(samples) - 1:
            return 0.0
        speed = self._sample_speed(samples[index], samples[index + 1])
        return self._clamp01(speed / max(0.001, self.config.rally_speed_threshold * 2.5))

    def _rally_after_score(self, samples_by_player: dict[str, list[PlayerTrajectorySample]], timestamp: float) -> float:
        active_players = 0
        for samples in samples_by_player.values():
            window = [sample for sample in samples if timestamp <= sample.timestamp_seconds <= timestamp + self.config.post_rally_window_seconds]
            if len(window) < 2:
                continue
            speeds = [self._sample_speed(a, b) for a, b in zip(window, window[1:])]
            if speeds and sum(speeds) / len(speeds) >= self.config.rally_speed_threshold:
                active_players += 1
        return self._clamp01(active_players / 2.0)

    def _receiver_waiting_score(
        self,
        samples_by_player: dict[str, list[PlayerTrajectorySample]],
        timestamp: float,
        server_player_id: str,
    ) -> float:
        waiting = 0
        considered = 0
        start = timestamp - self.config.pre_still_window_seconds
        end = timestamp - self.config.pre_still_gap_seconds
        for player_id, samples in samples_by_player.items():
            if player_id == server_player_id:
                continue
            window = [sample for sample in samples if start <= sample.timestamp_seconds <= end]
            if len(window) < 2:
                continue
            considered += 1
            speeds = [self._sample_speed(a, b) for a, b in zip(window, window[1:])]
            if speeds and sum(speeds) / len(speeds) <= self.config.still_speed_threshold:
                waiting += 1
        if considered == 0:
            return 0.0
        return self._clamp01(waiting / considered)

    def _pose_peak_score(self, sample: PlayerTrajectorySample, pose_by_track: dict[str, dict[int, float]]) -> float:
        if sample.track_id is None:
            return 0.0
        track_motion = pose_by_track.get(str(sample.track_id))
        if not track_motion:
            return 0.0
        raw = track_motion.get(sample.frame_index, 0.0)
        return self._clamp01(raw / max(1.0, self.config.arm_speed_peak_threshold))

    def _pose_motion_by_track(self, pose_frames: list[PoseOverlayFrame]) -> dict[str, dict[int, float]]:
        raw: dict[str, list[tuple[int, float, dict[str, tuple[float, float]]]]] = defaultdict(list)
        keypoint_names = {"left_wrist", "right_wrist", "left_elbow", "right_elbow"}
        for frame in pose_frames:
            for subject in frame.subjects:
                points = self._subject_points(subject, keypoint_names)
                if points:
                    raw[subject.track_id].append((frame.frame_index, frame.timestamp_seconds, points))
        motion_by_track: dict[str, dict[int, float]] = {}
        for track_id, items in raw.items():
            items.sort(key=lambda item: item[1])
            frame_motion: dict[int, float] = {}
            previous = None
            for frame_index, timestamp, points in items:
                if previous is None:
                    previous = (timestamp, points)
                    continue
                previous_timestamp, previous_points = previous
                dt = timestamp - previous_timestamp
                if dt <= 0:
                    previous = (timestamp, points)
                    continue
                speeds = []
                for name, point in points.items():
                    previous_point = previous_points.get(name)
                    if previous_point is None:
                        continue
                    speeds.append(hypot(point[0] - previous_point[0], point[1] - previous_point[1]) / dt)
                frame_motion[frame_index] = max(speeds) if speeds else 0.0
                previous = (timestamp, points)
            motion_by_track[track_id] = self._smooth_motion(frame_motion)
        return motion_by_track

    @staticmethod
    def _subject_points(subject: PoseSubject, names: set[str]) -> dict[str, tuple[float, float]]:
        return {
            keypoint.name: (keypoint.x, keypoint.y)
            for keypoint in subject.keypoints
            if keypoint.name in names and keypoint.visible and keypoint.confidence >= 0.25
        }

    def _smooth_motion(self, motion: dict[int, float]) -> dict[int, float]:
        if not motion:
            return {}
        items = sorted(motion.items())
        radius = max(0, self.config.pose_smooth_window_frames // 2)
        smoothed: dict[int, float] = {}
        for index, (frame_index, _value) in enumerate(items):
            start = max(0, index - radius)
            end = min(len(items), index + radius + 1)
            values = [value for _frame, value in items[start:end]]
            smoothed[frame_index] = sum(values) / len(values)
        return smoothed

    @staticmethod
    def _sample_speed(current: PlayerTrajectorySample, next_sample: PlayerTrajectorySample) -> float:
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

    @staticmethod
    def _clamp01(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    @staticmethod
    def _artifact_detection_mode(events: list[ServeEventCandidate]) -> str | None:
        if any(event.detection_mode == "pose" for event in events):
            return "pose"
        if any(event.detection_mode == "roi" for event in events):
            return "roi"
        if any(event.detection_mode == "tracking" for event in events):
            return "tracking"
        if events:
            return "trajectory"
        return None

    @staticmethod
    def _available_signals(events: list[ServeEventCandidate], *, pose_available: bool) -> list[ServeSignal]:
        signals: list[ServeSignal] = ["trajectory", "tracking"]
        if pose_available:
            signals.append("pose")
        if any(event.detection_mode == "roi" for event in events):
            signals.append("roi")
        return list(dict.fromkeys(signals))

    @staticmethod
    def _candidate_reason(player_id: str, detection_mode: str, signals: ServeSignalScores) -> str:
        mode_label = "手腕/肘部峰值" if detection_mode == "pose" else "ROI/轨迹局部运动峰值"
        return (
            f"{player_id} 位于底线附近，发球前低速准备后出现{mode_label}，"
            f"后续回合激活分 {signals.rally_after_score or 0:.2f}"
        )

    def _record_candidate(self, draft: _CandidateDraft) -> None:
        sample = draft.sample
        self.last_debug.candidates.append(
            {
                "timestamp_seconds": round(sample.timestamp_seconds, 3),
                "frame_index": sample.frame_index,
                "player_id": sample.player_id,
                "track_id": sample.track_id,
                "bbox": sample.bbox,
                "court_position": [sample.court_x, sample.court_y],
                "court_unit": sample.court_unit,
                "confidence": round(draft.confidence, 3),
                "detection_mode": draft.detection_mode,
                "reason": draft.reason,
                "signals": draft.signals.model_dump(mode="json"),
            }
        )

    def _record_rejection(self, sample: PlayerTrajectorySample, reason: str, **signals: Any) -> None:
        if len(self.last_debug.rejected) >= 200:
            return
        self.last_debug.rejected.append(
            {
                "timestamp_seconds": round(sample.timestamp_seconds, 3),
                "frame_index": sample.frame_index,
                "player_id": sample.player_id,
                "track_id": sample.track_id,
                "court_position": [sample.court_x, sample.court_y],
                "court_unit": sample.court_unit,
                "reason": reason,
                "signals": signals,
            }
        )
        self.last_debug.score_series.append(
            {
                "timestamp_seconds": round(sample.timestamp_seconds, 3),
                "frame_index": sample.frame_index,
                "player_id": sample.player_id,
                "baseline_position_score": signals.get("baseline_position_score"),
                "pre_stillness_score": signals.get("pre_stillness_score"),
                "arm_motion_peak_score": signals.get("arm_motion_peak_score"),
                "roi_motion_peak_score": signals.get("roi_motion_peak_score"),
                "rally_after_score": signals.get("rally_after_score"),
                "receiver_waiting_score": signals.get("receiver_waiting_score"),
                "rejected_reason": reason,
            }
        )

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
        detection_mode: str | None = None,
        available_signals: list[ServeSignal] | None = None,
        debug_artifacts: ServeDebugArtifactRefs | None = None,
    ) -> ServeEventsArtifact:
        return ServeEventsArtifact(
            job_id=job_id,
            video_id=video_id,
            status=status,  # type: ignore[arg-type]
            detail=detail,
            detector_version=self.version,
            duration_seconds=duration_seconds,
            fps=tracking.fps if tracking else 0.0,
            frame_count=tracking.frame_count if tracking else 0,
            processed_frame_count=tracking.processed_frame_count if tracking else 0,
            frame_stride=tracking.frame_stride if tracking else 1,
            detection_mode=detection_mode,  # type: ignore[arg-type]
            available_signals=available_signals or [],
            debug_artifacts=debug_artifacts,
            events=events or [],
        )
