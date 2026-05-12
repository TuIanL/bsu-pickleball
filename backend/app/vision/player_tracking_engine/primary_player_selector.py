from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from app.schemas.tracking import PlayerFramePosition, Track
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court


@dataclass(frozen=True)
class PrimaryPlayerSelection:
    track_id: int
    score: float
    confidence: float
    rolling_confidence: float
    appearances: int


@dataclass
class _TrackQuality:
    appearances: int = 0
    confidence_total: float = 0.0

    @property
    def rolling_confidence(self) -> float:
        return self.confidence_total / self.appearances if self.appearances else 0.0


class PrimaryPlayerSelector:
    """Select presentation subjects from tracked people using confidence and persistence."""

    def __init__(
        self,
        min_confidence: float = 0.65,
        max_subjects: int = 4,
        min_box_area_ratio: float = 0.0005,
        max_box_area_ratio: float = 0.85,
        court_margin_ft: float | None = 12.0,
        court: StandardPickleballCourt | None = None,
    ) -> None:
        self.min_confidence = min(max(min_confidence, 0.0), 1.0)
        self.max_subjects = max(1, int(max_subjects))
        self.min_box_area_ratio = max(0.0, min_box_area_ratio)
        self.max_box_area_ratio = max(self.min_box_area_ratio, max_box_area_ratio)
        self.court_margin_ft = court_margin_ft
        self.court = court or standard_court()
        self._qualities: dict[int, _TrackQuality] = {}

    def select(
        self,
        tracks: list[Track],
        positions: list[PlayerFramePosition],
        frame_width: int,
        frame_height: int,
    ) -> list[PrimaryPlayerSelection]:
        active_tracks = [track for track in tracks if not track.lost]
        for track in active_tracks:
            quality = self._qualities.setdefault(track.track_id, _TrackQuality())
            quality.appearances += 1
            quality.confidence_total += track.confidence

        positions_by_track_id = {position.track_id: position for position in positions}
        candidates = [
            selection
            for track in active_tracks
            if (selection := self._score_track(track, positions_by_track_id.get(track.track_id), frame_width, frame_height))
            is not None
        ]
        candidates.sort(key=lambda selection: (selection.score, selection.rolling_confidence, selection.confidence), reverse=True)
        return candidates[: self.max_subjects]

    def _score_track(
        self,
        track: Track,
        position: PlayerFramePosition | None,
        frame_width: int,
        frame_height: int,
    ) -> PrimaryPlayerSelection | None:
        if track.confidence < self.min_confidence:
            return None
        if not self._has_reasonable_box(track, frame_width, frame_height):
            return None
        if not self._passes_scene_sanity(position):
            return None

        quality = self._qualities.get(track.track_id, _TrackQuality())
        rolling_confidence = quality.rolling_confidence
        persistence = min(1.0, quality.appearances / 12.0)
        score = (track.confidence * 0.62) + (rolling_confidence * 0.26) + (persistence * 0.12)
        return PrimaryPlayerSelection(
            track_id=track.track_id,
            score=score,
            confidence=track.confidence,
            rolling_confidence=rolling_confidence,
            appearances=quality.appearances,
        )

    def _has_reasonable_box(self, track: Track, frame_width: int, frame_height: int) -> bool:
        source_area = max(1.0, float(frame_width) * float(frame_height))
        x1, y1, x2, y2 = [float(value) for value in track.bbox]
        if not all(isfinite(value) for value in (x1, y1, x2, y2)):
            return False
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if width <= 0.0 or height <= 0.0:
            return False
        area_ratio = (width * height) / source_area
        return self.min_box_area_ratio <= area_ratio <= self.max_box_area_ratio

    def _passes_scene_sanity(self, position: PlayerFramePosition | None) -> bool:
        if self.court_margin_ft is None or position is None or position.court_position is None:
            return True
        x, y = position.court_position
        margin = self.court_margin_ft
        return (
            -margin <= x <= self.court.width_ft + margin
            and -margin <= y <= self.court.length_ft + margin
        )
