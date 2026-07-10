from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from app.vision.pickleball_game_analysis.court_track_types import (
    CourtTrackObservation,
    CourtTrackEvent,
    CourtTrackPostProcessResult,
    CourtTrackSegment,
    ProcessedCourtTracks,
    RenderFrame,
    RenderPlayerMetadata,
    RenderSegmentMetadata,
    RenderSlotOverflowError,
    RenderSource,
    SegmentBreakReason,
    MAX_RENDER_SLOTS,
    canonical_player_id,
)


def _classify_court_side(y_ft: float) -> str:
    """根据球场 y 坐标推导 near/far 侧。"""
    return "far" if y_ft > 22.0 else "near"


_EVENT_BREAK_MAP: dict[str, SegmentBreakReason] = {
    "player_reset_after_prolonged_loss": "identity_reset",
}


@dataclass
class CourtTrackPostProcessor:
    max_interpolation_gap_seconds: float = 0.35
    max_visible_gap_seconds: float = 0.60
    max_spike_displacement_ft: float = 6.0
    max_distance_jump_ft: float = 9.84

    def process(
        self,
        observations: list[CourtTrackObservation],
        events: list[CourtTrackEvent],
        fps: float,
        total_frames: int,
    ) -> CourtTrackPostProcessResult:
        normalized_obs = self._normalize_player_ids(observations)
        events_normalized = [
            CourtTrackEvent(
                frame_index=ev.frame_index,
                timestamp_seconds=ev.timestamp_seconds,
                player_id=canonical_player_id(ev.player_id),
                event_type=ev.event_type,
                previous_track_id=ev.previous_track_id,
                current_track_id=ev.current_track_id,
                reason=ev.reason,
            )
            for ev in events
        ]

        roster = self._build_roster(normalized_obs)
        slot_map = self._assign_render_slots(roster)

        player_metadata = self._build_player_metadata(roster, slot_map, normalized_obs)

        segments_meta, samples = self._build_segments_and_samples(
            normalized_obs, events_normalized, slot_map, fps, total_frames,
        )

        samples.sort(key=lambda rf: (rf.timestamp_seconds, rf.frame_index, rf.player_id))
        for i, s in enumerate(samples):
            object.__setattr__(s, 'sequence_index', i)

        return CourtTrackPostProcessResult(
            players=player_metadata,
            segments=segments_meta,
            samples=samples,
        )

    def build_tracks(
        self,
        observations: list[CourtTrackObservation],
        events: list[CourtTrackEvent],
        fps: float,
        total_frames: int,
    ) -> ProcessedCourtTracks:
        """向后兼容：使用原有基于 epoch 分段 + 插值的逻辑。"""
        normalized_obs = self._normalize_player_ids(observations)
        segments = self._segment_by_epoch(normalized_obs, events)
        render_tracks: list[RenderFrame] = []
        for seg in segments:
            cleaned = self._filter_spikes(seg.observations)
            interpolated = self._interpolate_segment(cleaned, fps, total_frames)
            render_tracks.extend(interpolated)
        render_tracks.sort(key=lambda rf: (rf.frame_index, rf.player_id))
        return ProcessedCourtTracks(render_tracks=render_tracks)

    def _normalize_player_ids(
        self, observations: list[CourtTrackObservation],
    ) -> list[CourtTrackObservation]:
        return [
            CourtTrackObservation(
                frame_index=obs.frame_index,
                timestamp_seconds=obs.timestamp_seconds,
                player_id=canonical_player_id(obs.player_id),
                identity_epoch=obs.identity_epoch,
                track_id=obs.track_id,
                raw_x_ft=obs.raw_x_ft,
                raw_y_ft=obs.raw_y_ft,
                confidence=obs.confidence,
                projection_status=obs.projection_status,
                projection_confidence=obs.projection_confidence,
                footpoint_method=obs.footpoint_method,
                lock_state=obs.lock_state,
                tracking_status=obs.tracking_status,
            )
            for obs in observations
        ]

    def _build_roster(self, observations: list[CourtTrackObservation]) -> list[str]:
        player_ids = sorted(set(obs.player_id for obs in observations), key=_natural_sort_key)
        return player_ids

    def _assign_render_slots(self, roster: list[str]) -> dict[str, str]:
        if len(roster) > MAX_RENDER_SLOTS:
            raise RenderSlotOverflowError(
                observed=len(roster),
                maximum=MAX_RENDER_SLOTS,
            )
        return {p: f"slot_{i + 1}" for i, p in enumerate(roster)}

    def _build_player_metadata(
        self,
        roster: list[str],
        slot_map: dict[str, str],
        observations: list[CourtTrackObservation],
    ) -> list[RenderPlayerMetadata]:
        by_player: dict[str, list[CourtTrackObservation]] = defaultdict(list)
        for obs in observations:
            by_player[obs.player_id].append(obs)

        result: list[RenderPlayerMetadata] = []
        for pid in roster:
            obs_list = by_player.get(pid, [])
            obs_list.sort(key=lambda o: o.frame_index)
            detected = [o for o in obs_list if o.tracking_status == "detected"]
            first_reliable = next((o for o in obs_list if o.tracking_status == "detected"), obs_list[0] if obs_list else None)
            sides = [_classify_court_side(o.raw_y_ft) for o in detected]
            near_count = sides.count("near")
            far_count = sides.count("far")
            if near_count > far_count:
                dominant = "near"
            elif far_count > near_count:
                dominant = "far"
            elif sides and near_count == far_count:
                dominant = "mixed"
            else:
                dominant = "unknown"
            initial = _classify_court_side(first_reliable.raw_y_ft) if first_reliable else "unknown"
            source_track_ids = list(dict.fromkeys(
                o.track_id for o in obs_list if o.track_id is not None
            ))
            result.append(RenderPlayerMetadata(
                player_id=pid,
                render_slot=slot_map[pid],
                initial_side=initial,
                dominant_side=dominant,
                first_frame_index=first_reliable.frame_index if first_reliable else 0,
                source_track_ids=source_track_ids,
            ))
        return result

    def _build_segments_and_samples(
        self,
        observations: list[CourtTrackObservation],
        events: list[CourtTrackEvent],
        slot_map: dict[str, str],
        fps: float,
        total_frames: int,
    ) -> tuple[list[RenderSegmentMetadata], list[RenderFrame]]:
        by_player: dict[str, list[CourtTrackObservation]] = defaultdict(list)
        for obs in observations:
            by_player[obs.player_id].append(obs)
        for pid in by_player:
            by_player[pid].sort(key=lambda o: o.frame_index)

        frame_events: dict[str, set[int]] = defaultdict(set)
        for ev in events:
            frame_events[ev.player_id].add(ev.frame_index)

        all_segments: list[RenderSegmentMetadata] = []
        all_samples: list[RenderFrame] = []

        for player_id in sorted(by_player.keys()):
            obs_list = by_player[player_id]
            if not obs_list:
                continue

            segment_index = 0
            for epoch, epoch_obs in _group_by_epoch(obs_list).items():
                segments_raw = self._split_into_raw_segments(epoch_obs, fps, frame_events.get(player_id, set()))
                for seg_obs in segments_raw:
                    seg_obs.sort(key=lambda o: o.frame_index)
                    cleaned = self._filter_spikes(seg_obs)
                    rendered = self._interpolate_segment(cleaned, fps, total_frames)
                    if not rendered:
                        continue

                    seg_id = f"{player_id}:e{epoch}:s{segment_index}"
                    break_reason = self._determine_break_reason(
                        seg_obs, epoch_obs, segment_index, frame_events.get(player_id, set()),
                    )

                    for rf in rendered:
                        object.__setattr__(rf, 'render_slot', slot_map.get(player_id, ''))
                        object.__setattr__(rf, 'segment_id', seg_id)
                        object.__setattr__(rf, 'identity_epoch', epoch)
                        object.__setattr__(rf, 'side', self._resolve_side(rf, seg_obs, rendered))
                        object.__setattr__(rf, 'source_track_id', seg_obs[0].track_id if rf.source == "observed" else None)
                        object.__setattr__(rf, 'projection_status', seg_obs[0].projection_status if rf.source == "observed" else None)
                        object.__setattr__(rf, 'projection_confidence', seg_obs[0].projection_confidence if rf.source == "observed" else None)
                        object.__setattr__(rf, 'footpoint_method', seg_obs[0].footpoint_method if rf.source == "observed" else None)

                    all_samples.extend(rendered)

                    all_segments.append(RenderSegmentMetadata(
                        segment_id=seg_id,
                        player_id=player_id,
                        identity_epoch=epoch,
                        start_frame_index=rendered[0].frame_index,
                        end_frame_index=rendered[-1].frame_index,
                        start_timestamp_seconds=rendered[0].timestamp_seconds,
                        end_timestamp_seconds=rendered[-1].timestamp_seconds,
                        break_before=break_reason,
                        sample_count=len(rendered),
                    ))
                    segment_index += 1

        return all_segments, all_samples

    def _split_into_raw_segments(
        self,
        obs_list: list[CourtTrackObservation],
        fps: float,
        event_frames: set[int],
    ) -> list[list[CourtTrackObservation]]:
        if not obs_list:
            return []
        obs_list.sort(key=lambda o: o.frame_index)
        segments: list[list[CourtTrackObservation]] = []
        current: list[CourtTrackObservation] = [obs_list[0]]
        for i in range(1, len(obs_list)):
            prev = obs_list[i - 1]
            curr = obs_list[i]
            gap_frames = curr.frame_index - prev.frame_index
            gap_seconds = gap_frames / fps if fps > 0 else float("inf")
            if gap_seconds > self.max_visible_gap_seconds:
                segments.append(current)
                current = [curr]
                continue
            dist = _dist(prev.raw_x_ft, prev.raw_y_ft, curr.raw_x_ft, curr.raw_y_ft)
            if dist > self.max_distance_jump_ft:
                segments.append(current)
                current = [curr]
                continue
            current.append(curr)
        if current:
            segments.append(current)
        return segments

    def _determine_break_reason(
        self,
        seg_obs: list[CourtTrackObservation],
        all_epoch_obs: list[CourtTrackObservation],
        seg_index: int,
        event_frames: set[int],
    ) -> SegmentBreakReason:
        is_first_segment_in_epoch = (seg_index == 0)
        is_very_first_segment = is_first_segment_in_epoch and (seg_obs[0].frame_index == all_epoch_obs[0].frame_index if all_epoch_obs else True)
        if is_very_first_segment and is_first_segment_in_epoch and seg_index == 0:
            first_frame = seg_obs[0].frame_index
            for ev_frame in event_frames:
                if abs(ev_frame - first_frame) <= 1:
                    return "identity_reset"
            return "start"
        if is_first_segment_in_epoch:
            return "identity_reset"
        first_gap = seg_obs[0].frame_index - seg_obs[0].frame_index
        if first_gap > 0:
            return "visible_gap"
        if seg_obs:
            dist = _dist(
                seg_obs[0].raw_x_ft, seg_obs[0].raw_y_ft,
                seg_obs[0].raw_x_ft, seg_obs[0].raw_y_ft,
            )
            return "visible_gap"
        return "visible_gap"

    def _resolve_side(
        self,
        rf: RenderFrame,
        seg_obs: list[CourtTrackObservation],
        all_rendered: list[RenderFrame],
    ) -> str:
        if rf.source == "observed":
            for o in seg_obs:
                if o.frame_index == rf.frame_index:
                    return _classify_court_side(o.raw_y_ft)
        idx = next((i for i, r in enumerate(all_rendered) if r.frame_index == rf.frame_index), None)
        if idx is not None:
            for i in range(idx, -1, -1):
                if all_rendered[i].source == "observed":
                    return all_rendered[i].side
            for i in range(idx, len(all_rendered)):
                if all_rendered[i].source == "observed":
                    return all_rendered[i].side
        return _classify_court_side(rf.y_ft)

    def _segment_by_epoch(
        self,
        observations: list[CourtTrackObservation],
        events: list[CourtTrackEvent],
    ) -> list[CourtTrackSegment]:
        by_player: dict[str, list[CourtTrackObservation]] = defaultdict(list)
        for obs in observations:
            by_player[obs.player_id].append(obs)
        for player_id in by_player:
            by_player[player_id].sort(key=lambda o: o.frame_index)

        frame_resets: dict[str, set[int]] = defaultdict(set)
        for ev in events:
            if ev.event_type == "identity_reset":
                frame_resets[ev.player_id].add(ev.frame_index)

        segments: list[CourtTrackSegment] = []
        for player_id, obs_list in by_player.items():
            current_epoch: int | None = None
            current: list[CourtTrackObservation] = []
            for obs in obs_list:
                if current_epoch is None:
                    current_epoch = obs.identity_epoch
                elif obs.identity_epoch != current_epoch:
                    if current:
                        segments.append(CourtTrackSegment(
                            player_id=player_id,
                            epoch=current_epoch,
                            observations=current,
                        ))
                        current = []
                    current_epoch = obs.identity_epoch
                current.append(obs)
            if current and current_epoch is not None:
                segments.append(CourtTrackSegment(
                    player_id=player_id,
                    epoch=current_epoch,
                    observations=current,
                ))
        return segments

    def _filter_spikes(self, observations: list[CourtTrackObservation]) -> list[CourtTrackObservation]:
        if len(observations) < 3:
            return [
                o for o in observations
                if o.projection_status != "projection_failed"
                and _is_finite(o.raw_x_ft) and _is_finite(o.raw_y_ft)
            ]

        filtered: list[CourtTrackObservation] = []
        for i, obs in enumerate(observations):
            if obs.projection_status == "projection_failed":
                continue
            if not _is_finite(obs.raw_x_ft) or not _is_finite(obs.raw_y_ft):
                continue
            if 0 < i < len(observations) - 1:
                prev = observations[i - 1]
                nxt = observations[i + 1]
                if not _is_finite(prev.raw_x_ft) or not _is_finite(prev.raw_y_ft):
                    filtered.append(obs)
                    continue
                if not _is_finite(nxt.raw_x_ft) or not _is_finite(nxt.raw_y_ft):
                    filtered.append(obs)
                    continue
                d_prev_curr = _dist(prev.raw_x_ft, prev.raw_y_ft, obs.raw_x_ft, obs.raw_y_ft)
                d_curr_next = _dist(obs.raw_x_ft, obs.raw_y_ft, nxt.raw_x_ft, nxt.raw_y_ft)
                d_prev_next = _dist(prev.raw_x_ft, prev.raw_y_ft, nxt.raw_x_ft, nxt.raw_y_ft)
                if (d_prev_curr > self.max_spike_displacement_ft
                        and d_curr_next > self.max_spike_displacement_ft
                        and d_prev_next < self.max_spike_displacement_ft):
                    continue
            filtered.append(obs)
        return filtered

    def _interpolate_segment(
        self,
        observations: list[CourtTrackObservation],
        fps: float,
        total_frames: int,
    ) -> list[RenderFrame]:
        if not observations:
            return []
        result: list[RenderFrame] = []
        player_id = observations[0].player_id

        for i in range(len(observations) - 1):
            left = observations[i]
            right = observations[i + 1]
            gap_frames = right.frame_index - left.frame_index
            gap_seconds = gap_frames / fps if fps > 0 else float("inf")

            result.append(RenderFrame(
                frame_index=left.frame_index,
                timestamp_seconds=left.timestamp_seconds,
                x_ft=left.raw_x_ft,
                y_ft=left.raw_y_ft,
                source="observed",
                confidence=left.confidence,
                player_id=player_id,
            ))

            if gap_frames <= 1:
                continue

            if gap_seconds > self.max_visible_gap_seconds:
                continue

            for mid_frame in range(left.frame_index + 1, right.frame_index):
                ratio = (mid_frame - left.frame_index) / gap_frames if gap_frames > 0 else 0
                x = left.raw_x_ft + ratio * (right.raw_x_ft - left.raw_x_ft)
                y = left.raw_y_ft + ratio * (right.raw_y_ft - left.raw_y_ft)
                mid_time = left.timestamp_seconds + ratio * (right.timestamp_seconds - left.timestamp_seconds)

                conf: float
                source: RenderSource
                if gap_seconds <= self.max_interpolation_gap_seconds:
                    source = "interpolated"
                    conf = min(left.confidence, right.confidence) * 0.95
                else:
                    source = "interpolated"
                    decay = 1.0 - (gap_seconds - self.max_interpolation_gap_seconds) / (
                        self.max_visible_gap_seconds - self.max_interpolation_gap_seconds
                    )
                    decay = max(0.3, decay)
                    conf = min(left.confidence, right.confidence) * decay

                result.append(RenderFrame(
                    frame_index=mid_frame,
                    timestamp_seconds=mid_time,
                    x_ft=x,
                    y_ft=y,
                    source=source,
                    confidence=conf,
                    player_id=player_id,
                ))

        last = observations[-1]
        result.append(RenderFrame(
            frame_index=last.frame_index,
            timestamp_seconds=last.timestamp_seconds,
            x_ft=last.raw_x_ft,
            y_ft=last.raw_y_ft,
            source="observed",
            confidence=last.confidence,
            player_id=player_id,
        ))
        return result


def _dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def _is_finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _natural_sort_key(player_id: str) -> tuple[int, str]:
    parts = player_id.rsplit("_", 1)
    if len(parts) == 2:
        try:
            return (int(parts[1]), player_id)
        except ValueError:
            pass
    return (0, player_id)


def _group_by_epoch(observations: list[CourtTrackObservation]) -> dict[int, list[CourtTrackObservation]]:
    grouped: dict[int, list[CourtTrackObservation]] = {}
    for obs in observations:
        grouped.setdefault(obs.identity_epoch, []).append(obs)
    return grouped
