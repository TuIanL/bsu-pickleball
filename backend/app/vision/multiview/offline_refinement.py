"""F1 offline refinement contracts, recovery and formal re-fusion.

F1 is deliberately evidence-only.  It reads an immutable F0 snapshot, creates
      frozen view observations, and runs the normal fusion policy on a new
trajectory.  It never updates the online tracker, registry, or identity map.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from statistics import median
from typing import Any, Callable, Literal, Mapping

from app.vision.multiview.guided_detection import guided_candidate_pre_gate
from app.vision.multiview.joint_types import DetectionOrigin

OfflineOrigin = DetectionOrigin


@dataclass(frozen=True)
class F0TickViewState:
    """Frozen, reusable F0 evidence for one global/view/tick."""

    observed: bool
    quality: float
    canonical_position: tuple[float, float] | None = None
    origin: str = "base"
    source_frame_index: int | None = None
    source_timestamp_ms: float | None = None
    mapped_take_timestamp_ms: float | None = None
    selection_error_ms: float | None = None
    timing_authority: str = "missing"
    sync_quality: str = "unknown"
    view_status: str = "available"
    observation_status: str = "observed"
    view_player_id: str = ""
    detector_confidence: float | None = None
    projection_confidence: float | None = None
    tracking_status: str = "detected"
    bbox: tuple[float, ...] | None = None


@dataclass(frozen=True)
class F0TickSnapshot:
    """One canonical tick in the F0 refinement evidence snapshot."""

    canonical_tick: int
    canonical_timestamp_ms: float
    reference_frame_index: int
    observations: tuple[tuple[str, str, F0TickViewState], ...] = ()
    global_positions: tuple[tuple[str, tuple[float, float]], ...] = ()
    predictions: tuple[tuple[str, tuple[float, float]], ...] = ()
    metric_scope: bool = True

    def view_state(self, view_id: str) -> F0TickViewState | None:
        for _gid, candidate_view_id, state in self.observations:
            if candidate_view_id == view_id:
                return state
        return None

    def state_for(self, global_player_id: str, view_id: str) -> F0TickViewState | None:
        for gid, candidate_view_id, state in self.observations:
            if gid == global_player_id and candidate_view_id == view_id:
                return state
        return None

    def position_for(self, global_player_id: str) -> tuple[float, float] | None:
        return dict(self.global_positions).get(global_player_id)


@dataclass(frozen=True)
class F0RefinementSnapshot:
    """Immutable F0 input to F1.

    Tuples are used at every collection boundary so a failed F1 cannot mutate
    the evidence later consumed by diagnostics or an A/B comparison.
    """

    run_id: str = ""
    capture_take_id: str = ""
    reference_view_id: str = "cam_1"
    view_ids: tuple[str, ...] = ("cam_1", "cam_2")
    global_player_ids: tuple[str, ...] = ()
    ticks: tuple[F0TickSnapshot, ...] = ()
    config_snapshot: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "view_ids", tuple(self.view_ids))
        object.__setattr__(self, "global_player_ids", tuple(self.global_player_ids))
        object.__setattr__(self, "ticks", tuple(self.ticks))
        object.__setattr__(self, "config_snapshot", _freeze_value(self.config_snapshot))

    def tick(self, canonical_tick: int) -> F0TickSnapshot | None:
        return next((item for item in self.ticks if item.canonical_tick == canonical_tick), None)

    def state_for(
        self, global_player_id: str, view_id: str, canonical_tick: int
    ) -> F0TickViewState | None:
        item = self.tick(canonical_tick)
        return item.state_for(global_player_id, view_id) if item is not None else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "f0_refinement_snapshot.v1",
            "run_id": self.run_id,
            "capture_take_id": self.capture_take_id,
            "reference_view_id": self.reference_view_id,
            "view_ids": list(self.view_ids),
            "global_player_ids": list(self.global_player_ids),
            "config_snapshot": _thaw_value(self.config_snapshot),
            "ticks": [
                {
                    "canonical_tick": tick.canonical_tick,
                    "canonical_timestamp_ms": tick.canonical_timestamp_ms,
                    "reference_frame_index": tick.reference_frame_index,
                    "metric_scope": tick.metric_scope,
                    "global_positions": {
                        gid: list(position) for gid, position in tick.global_positions
                    },
                    "predictions": {
                        gid: list(position) for gid, position in tick.predictions
                    },
                    "observations": [
                        {
                            "global_player_id": gid,
                            "view_id": view_id,
                            "state": _state_to_dict(state),
                        }
                        for gid, view_id, state in tick.observations
                    ],
                }
                for tick in self.ticks
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "F0RefinementSnapshot":
        ticks: list[F0TickSnapshot] = []
        for raw_tick in payload.get("ticks", []):
            if not isinstance(raw_tick, Mapping):
                continue
            observations = tuple(
                (
                    str(raw_observation.get("global_player_id", "")),
                    str(raw_observation.get("view_id", "")),
                    _state_from_dict(raw_observation.get("state", {})),
                )
                for raw_observation in raw_tick.get("observations", [])
                if isinstance(raw_observation, Mapping)
                and isinstance(raw_observation.get("state", {}), Mapping)
            )
            if not observations:
                observations = tuple(
                    ("", str(view_id), _state_from_dict(raw_state))
                    for view_id, raw_state in dict(raw_tick.get("views", {})).items()
                    if isinstance(raw_state, Mapping)
                )
            ticks.append(
                F0TickSnapshot(
                    canonical_tick=int(raw_tick.get("canonical_tick", 0)),
                    canonical_timestamp_ms=float(raw_tick.get("canonical_timestamp_ms", 0.0)),
                    reference_frame_index=int(raw_tick.get("reference_frame_index", 0)),
                    observations=observations,
                    global_positions=tuple(
                        (str(gid), (float(position[0]), float(position[1])))
                        for gid, position in dict(raw_tick.get("global_positions", {})).items()
                        if isinstance(position, (list, tuple)) and len(position) >= 2
                    ),
                    predictions=tuple(
                        (str(gid), (float(position[0]), float(position[1])))
                        for gid, position in dict(raw_tick.get("predictions", {})).items()
                        if isinstance(position, (list, tuple)) and len(position) >= 2
                    ),
                    metric_scope=bool(raw_tick.get("metric_scope", True)),
                )
            )
        return cls(
            run_id=str(payload.get("run_id", "")),
            capture_take_id=str(payload.get("capture_take_id", "")),
            reference_view_id=str(payload.get("reference_view_id", "cam_1")),
            view_ids=tuple(str(item) for item in payload.get("view_ids", ("cam_1", "cam_2"))),
            global_player_ids=tuple(str(item) for item in payload.get("global_player_ids", ())),
            ticks=tuple(ticks),
            config_snapshot=dict(payload.get("config_snapshot", {})),
        )


@dataclass(frozen=True)
class RefinementViewContext:
    """All target-view dependencies needed by the offline detector."""

    view_id: str
    frame_provider: Callable[[int], Any] | None
    detector: Any
    homography: list[list[float]]
    inverse_homography: Any
    orientation: Any
    frame_width: int
    frame_height: int
    timing_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "homography", tuple(tuple(row) for row in self.homography))
        object.__setattr__(self, "timing_metadata", _freeze_value(self.timing_metadata))


@dataclass(frozen=True)
class RefinementConfigSnapshot:
    """F1 parameters copied from the online recovery config and diagnostics."""

    min_donor_quality: float = 0.55
    missing_after_ticks: int = 3
    max_residual_ft: float = 3.0
    allowed_jump_delta: int = 2
    allowed_speed_delta: int = 2
    allowed_conflict_delta: int = 2
    max_recovered_residual_p90: float = 3.0
    max_speed_ft_s: float = 30.0
    max_jump_ft: float = 3.0

    @classmethod
    def from_online(
        cls,
        online_config: Mapping[str, Any] | Any | None = None,
        **overrides: Any,
    ) -> "RefinementConfigSnapshot":
        source = (
            online_config.snapshot()
            if hasattr(online_config, "snapshot")
            else dict(online_config or {})
        )
        values = {
            "min_donor_quality": source.get("min_donor_quality", 0.55),
            "missing_after_ticks": source.get("missing_after_ticks", 3),
            "max_residual_ft": source.get("guided_max_residual_ft", source.get("max_residual_ft", 3.0)),
            "allowed_jump_delta": source.get("allowed_jump_delta", 2),
            "allowed_speed_delta": source.get("allowed_speed_delta", 2),
            "allowed_conflict_delta": source.get("allowed_conflict_delta", 2),
            "max_recovered_residual_p90": source.get("max_recovered_residual_p90", 3.0),
            "max_speed_ft_s": source.get("max_speed_ft_s", 30.0),
            "max_jump_ft": source.get("max_jump_ft", 3.0),
        }
        values.update(overrides)
        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        return {
            "min_donor_quality": self.min_donor_quality,
            "missing_after_ticks": self.missing_after_ticks,
            "max_residual_ft": self.max_residual_ft,
            "allowed_jump_delta": self.allowed_jump_delta,
            "allowed_speed_delta": self.allowed_speed_delta,
            "allowed_conflict_delta": self.allowed_conflict_delta,
            "max_recovered_residual_p90": self.max_recovered_residual_p90,
            "max_speed_ft_s": self.max_speed_ft_s,
            "max_jump_ft": self.max_jump_ft,
        }


@dataclass(frozen=True)
class RecoveryTickPlan:
    """Immutable recovery plan copied from F0 timing/evidence."""

    tick_id: str
    take_timestamp_ms: float
    global_player_id: str
    target_view: str
    target_source_frame_index: int | None
    target_source_timestamp_ms: float | None
    donor_view: str
    donor_source_frame_index: int | None
    donor_canonical_position: tuple[float, float] | None
    donor_quality: float
    f0_global_position: tuple[float, float] | None
    target_selection_error_ms: float | None = None
    canonical_tick: int = 0
    target_mapped_take_timestamp_ms: float | None = None
    donor_source_timestamp_ms: float | None = None
    donor_mapped_take_timestamp_ms: float | None = None
    target_timing_authority: str = "missing"
    donor_timing_authority: str = "missing"
    target_sync_quality: str = "unknown"
    donor_sync_quality: str = "unknown"


@dataclass
class RecoveryWindow:
    """A donor-strong, target weak/missing/lost interval."""

    global_player_id: str
    target_view: str
    donor_view: str
    start_tick: int
    end_tick: int
    ticks: list[RecoveryTickPlan] = field(default_factory=list)
    unavailable_ticks: list[int] = field(default_factory=list)

    def freeze(self) -> "FrozenRecoveryWindow":
        return FrozenRecoveryWindow(
            global_player_id=self.global_player_id,
            target_view=self.target_view,
            donor_view=self.donor_view,
            start_tick=self.start_tick,
            end_tick=self.end_tick,
            ticks=tuple(self.ticks),
            unavailable_ticks=tuple(self.unavailable_ticks),
        )


@dataclass(frozen=True)
class FrozenRecoveryWindow:
    """Read-only window passed from planning into the recovery pass."""

    global_player_id: str
    target_view: str
    donor_view: str
    start_tick: int
    end_tick: int
    ticks: tuple[RecoveryTickPlan, ...] = ()
    unavailable_ticks: tuple[int, ...] = ()


@dataclass
class RecoveryTracklet:
    """Window-local continuity proof. It has no F0 state references."""

    recovery_window_id: str
    previous_bbox: list[float] | None = None
    previous_canonical_position: tuple[float, float] | None = None
    consecutive_hits: int = 0


@dataclass(frozen=True)
class RecoveredViewObservation:
    """Frozen target-view measurement evidence produced by F1 recovery."""

    view_id: str
    take_timestamp_ms: float
    source_frame_index: int
    canonical_x_ft: float
    canonical_y_ft: float
    bbox: tuple[float, ...]
    confidence: float
    detection_origin: OfflineOrigin = "offline_refinement"
    global_player_id: str = ""
    canonical_tick: int = 0
    source_timestamp_ms: float | None = None
    mapped_take_timestamp_ms: float | None = None
    selection_error_ms: float | None = None
    timing_authority: str = "missing"
    sync_quality: str = "unknown"
    donor_view: str | None = None
    donor_source_frame_index: int | None = None
    donor_quality: float = 0.0
    expected_global_position: tuple[float, float] | None = None
    residual_ft: float | None = None
    suppression_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bbox", tuple(float(value) for value in self.bbox))


def _freeze_value(value: Any) -> Any:
    from types import MappingProxyType

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    if isinstance(value, frozenset):
        return [_thaw_value(item) for item in value]
    return value


def _state_to_dict(state: F0TickViewState) -> dict[str, object]:
    data = {
        "observed": state.observed,
        "quality": state.quality,
        "canonical_position": list(state.canonical_position) if state.canonical_position else None,
        "origin": state.origin,
        "source_frame_index": state.source_frame_index,
        "source_timestamp_ms": state.source_timestamp_ms,
        "mapped_take_timestamp_ms": state.mapped_take_timestamp_ms,
        "selection_error_ms": state.selection_error_ms,
        "timing_authority": state.timing_authority,
        "sync_quality": state.sync_quality,
        "view_status": state.view_status,
        "observation_status": state.observation_status,
        "view_player_id": state.view_player_id,
        "detector_confidence": state.detector_confidence,
        "projection_confidence": state.projection_confidence,
        "tracking_status": state.tracking_status,
        "bbox": list(state.bbox) if state.bbox else None,
    }
    return data


def _state_from_dict(raw: Mapping[str, Any]) -> F0TickViewState:
    position = raw.get("canonical_position")
    bbox = raw.get("bbox")
    return F0TickViewState(
        observed=bool(raw.get("observed", False)),
        quality=float(raw.get("quality", 0.0)),
        canonical_position=(float(position[0]), float(position[1])) if isinstance(position, (list, tuple)) and len(position) >= 2 else None,
        origin=str(raw.get("origin", "base")),
        source_frame_index=int(raw["source_frame_index"]) if raw.get("source_frame_index") is not None else None,
        source_timestamp_ms=float(raw["source_timestamp_ms"]) if raw.get("source_timestamp_ms") is not None else None,
        mapped_take_timestamp_ms=float(raw["mapped_take_timestamp_ms"]) if raw.get("mapped_take_timestamp_ms") is not None else None,
        selection_error_ms=float(raw["selection_error_ms"]) if raw.get("selection_error_ms") is not None else None,
        timing_authority=str(raw.get("timing_authority", "missing")),
        sync_quality=str(raw.get("sync_quality", "unknown")),
        view_status=str(raw.get("view_status", "available")),
        observation_status=str(raw.get("observation_status", "observed")),
        view_player_id=str(raw.get("view_player_id", "")),
        detector_confidence=float(raw["detector_confidence"]) if raw.get("detector_confidence") is not None else None,
        projection_confidence=float(raw["projection_confidence"]) if raw.get("projection_confidence") is not None else None,
        tracking_status=str(raw.get("tracking_status", "detected")),
        bbox=tuple(float(value) for value in bbox) if isinstance(bbox, (list, tuple)) else None,
    )


def snapshot_from_legacy_trace(
    *,
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]],
    f0_source_frames: dict[str, dict[int, int | None]] | None = None,
    f0_global_positions: dict[str, dict[int, tuple[float, float]]] | None = None,
    tick_metadata: Mapping[int, Mapping[str, Any]] | None = None,
    run_id: str = "",
    capture_take_id: str = "",
    reference_view_id: str = "cam_1",
    views: tuple[str, ...] = ("cam_1", "cam_2"),
    config_snapshot: Mapping[str, Any] | None = None,
) -> F0RefinementSnapshot:
    """Build a frozen snapshot while retaining the old trace API."""
    source_frames = f0_source_frames or {}
    positions = f0_global_positions or {}
    metadata = tick_metadata or {}
    gids = tuple(sorted(f0_trace))
    tick_ids = sorted(
        set(metadata)
        | {
            tick
            for view_states in f0_trace.values()
            for ticks in view_states.values()
            for tick in ticks
        }
    )
    ticks: list[F0TickSnapshot] = []
    for tick_id in tick_ids:
        raw_meta = metadata.get(tick_id, {})
        view_rows: list[tuple[str, str, F0TickViewState]] = []
        for view_id in views:
            # A global can be missing in a view even though the frame exists.
            # Preserve frame timing by copying it into that state where possible.
            frame_info = dict(raw_meta.get("views", {}).get(view_id, {})) if isinstance(raw_meta.get("views", {}), Mapping) else {}
            source_index = frame_info.get("source_frame_index")
            if source_index is None:
                source_index = source_frames.get(view_id, {}).get(tick_id)
            for gid in gids:
                candidate = f0_trace.get(gid, {}).get(view_id, {}).get(tick_id)
                if candidate is None:
                    candidate = F0TickViewState(
                        observed=False,
                        quality=0.0,
                        origin="missing",
                        source_frame_index=source_index,
                        source_timestamp_ms=frame_info.get("source_timestamp_ms"),
                        mapped_take_timestamp_ms=frame_info.get("mapped_take_timestamp_ms"),
                        selection_error_ms=frame_info.get("selection_error_ms"),
                        timing_authority=str(frame_info.get("timing_authority", "missing")),
                        sync_quality=str(frame_info.get("sync_quality", "unknown")),
                        view_status=str(frame_info.get("view_status", "unavailable" if source_index is None else "available")),
                        observation_status="missing",
                    )
                elif candidate.source_frame_index is None and source_index is not None:
                    candidate = replace(candidate, source_frame_index=source_index)
                view_rows.append((gid, view_id, candidate))
        global_positions = tuple(
            (gid, positions.get(gid, {}).get(tick_id))
            for gid in gids
            if positions.get(gid, {}).get(tick_id) is not None
        )
        ticks.append(
            F0TickSnapshot(
                canonical_tick=tick_id,
                canonical_timestamp_ms=float(raw_meta.get("canonical_timestamp_ms", 0.0)),
                reference_frame_index=int(raw_meta.get("reference_frame_index", tick_id)),
                observations=tuple(view_rows),
                global_positions=tuple(global_positions),
                predictions=tuple(),
                metric_scope=bool(raw_meta.get("metric_scope", True)),
            )
        )
    return F0RefinementSnapshot(
        run_id=run_id,
        capture_take_id=capture_take_id,
        reference_view_id=reference_view_id,
        view_ids=views,
        global_player_ids=gids,
        ticks=tuple(ticks),
        config_snapshot=config_snapshot or {},
    )


def _trace_and_snapshot(
    source: F0RefinementSnapshot | dict[str, dict[str, dict[int, F0TickViewState]]],
    *,
    f0_source_frames: dict[str, dict[int, int | None]] | None = None,
    f0_global_positions: dict[str, dict[int, tuple[float, float]]] | None = None,
) -> tuple[dict[str, dict[str, dict[int, F0TickViewState]]], F0RefinementSnapshot]:
    if isinstance(source, F0RefinementSnapshot):
        trace: dict[str, dict[str, dict[int, F0TickViewState]]] = {}
        for tick in source.ticks:
            for gid, view_id, state in tick.observations:
                trace.setdefault(gid, {}).setdefault(view_id, {})[tick.canonical_tick] = state
        return trace, source
    snapshot = snapshot_from_legacy_trace(
        f0_trace=source,
        f0_source_frames=f0_source_frames,
        f0_global_positions=f0_global_positions,
    )
    return source, snapshot


def _target_is_missing(state: F0TickViewState) -> bool:
    return (
        not state.observed
        or state.quality < 0.55
        or state.observation_status in {"weak", "missing", "lost"}
        or state.origin in {"missing", "lost"}
    )


def mine_recovery_windows(
    f0_trace: F0RefinementSnapshot | dict[str, dict[str, dict[int, F0TickViewState]]],
    views: tuple[str, ...] = ("cam_1", "cam_2"),
    missing_after_ticks: int = 3,
    donor_min_quality: float = 0.5,
) -> list[RecoveryWindow]:
    """Mine target gaps, keeping frame-unavailable ticks distinguishable."""
    trace, snapshot = _trace_and_snapshot(f0_trace)
    windows: list[RecoveryWindow] = []
    actual_views = tuple(snapshot.view_ids) if isinstance(f0_trace, F0RefinementSnapshot) else views
    for gid, view_states in trace.items():
        for target_view in actual_views:
            donor_views = tuple(view for view in actual_views if view != target_view)
            if not donor_views:
                continue
            donor_view = donor_views[0]
            donor_state = view_states.get(donor_view, {})
            if not any(
                state.observed and state.origin == "base" and state.quality >= donor_min_quality
                for state in donor_state.values()
            ):
                continue
            target_state = view_states.get(target_view, {})
            run_start: int | None = None
            prev: int | None = None
            unavailable_ticks: list[int] = []
            for tick in sorted(target_state):
                state = target_state[tick]
                if state.source_frame_index is None or state.view_status != "available":
                    unavailable_ticks.append(tick)
                if _target_is_missing(state):
                    if run_start is None:
                        run_start = tick
                    elif prev is not None and tick != prev + 1:
                        if prev - run_start + 1 >= missing_after_ticks:
                            windows.append(RecoveryWindow(gid, target_view, donor_view, run_start, prev, unavailable_ticks=list(unavailable_ticks)))
                        run_start = tick
                    prev = tick
                    continue
                if run_start is not None and prev is not None and prev - run_start + 1 >= missing_after_ticks:
                    windows.append(RecoveryWindow(gid, target_view, donor_view, run_start, prev, unavailable_ticks=list(unavailable_ticks)))
                run_start = None
                prev = None
            if run_start is not None and prev is not None and prev - run_start + 1 >= missing_after_ticks:
                windows.append(RecoveryWindow(gid, target_view, donor_view, run_start, prev, unavailable_ticks=list(unavailable_ticks)))
    return windows


def build_recovery_tick_plans(
    window: RecoveryWindow,
    f0_trace: F0RefinementSnapshot | dict[str, dict[str, dict[int, F0TickViewState]]],
    f0_source_frames: dict[str, dict[int, int | None]] | None = None,
    f0_global_positions: dict[str, dict[int, tuple[float, float]]] | None = None,
    *,
    donor_min_quality: float = 0.5,
) -> RecoveryWindow:
    """Create immutable per-tick plans from F0 timing, never from nominal FPS."""
    trace, snapshot = _trace_and_snapshot(
        f0_trace,
        f0_source_frames=f0_source_frames,
        f0_global_positions=f0_global_positions,
    )
    target_state = trace.get(window.global_player_id, {}).get(window.target_view, {})
    donor_state = trace.get(window.global_player_id, {}).get(window.donor_view, {})
    target_frames = f0_source_frames.get(window.target_view, {}) if f0_source_frames else {}
    donor_frames = f0_source_frames.get(window.donor_view, {}) if f0_source_frames else {}
    plans: list[RecoveryTickPlan] = []
    for tick in range(window.start_tick, window.end_tick + 1):
        target = target_state.get(tick)
        donor = donor_state.get(tick)
        snapshot_tick = snapshot.tick(tick)
        if target is None or donor is None or not _target_is_missing(target):
            continue
        if not donor.observed or donor.origin != "base" or donor.quality < donor_min_quality:
            continue
        target_frame = target.source_frame_index
        if target_frame is None:
            target_frame = target_frames.get(tick)
        donor_frame = donor.source_frame_index
        if donor_frame is None:
            donor_frame = donor_frames.get(tick)
        if target_frame is None or donor_frame is None:
            continue
        # These timestamps are F0 evidence.  A legacy fixture without timing
        # remains usable at 0ms, but no FPS-derived value is ever invented.
        take_ms = snapshot_tick.canonical_timestamp_ms if snapshot_tick is not None else 0.0
        global_position = snapshot_tick.position_for(window.global_player_id) if snapshot_tick else None
        plan = RecoveryTickPlan(
            tick_id=f"{window.global_player_id}:{window.target_view}:{tick}",
            take_timestamp_ms=take_ms,
            global_player_id=window.global_player_id,
            target_view=window.target_view,
            target_source_frame_index=target_frame,
            target_source_timestamp_ms=target.source_timestamp_ms,
            donor_view=window.donor_view,
            donor_source_frame_index=donor_frame,
            donor_canonical_position=donor.canonical_position,
            donor_quality=donor.quality,
            f0_global_position=global_position,
            canonical_tick=tick,
            target_mapped_take_timestamp_ms=target.mapped_take_timestamp_ms,
            donor_source_timestamp_ms=donor.source_timestamp_ms,
            donor_mapped_take_timestamp_ms=donor.mapped_take_timestamp_ms,
            target_selection_error_ms=target.selection_error_ms,
            target_timing_authority=target.timing_authority,
            donor_timing_authority=donor.timing_authority,
            target_sync_quality=target.sync_quality,
            donor_sync_quality=donor.sync_quality,
        )
        plans.append(plan)
    window.ticks = plans
    return window


class OfflineRecovery:
    """Second-pass detector using the target view's own geometry/context."""

    def __init__(
        self,
        *,
        view_contexts: Mapping[str, RefinementViewContext] | None = None,
        homography: list[list[float]] | None = None,
        frame_width: int = 0,
        frame_height: int = 0,
        max_residual_ft: float = 3.0,
        envelope_margin_px: float = 60.0,
    ) -> None:
        self.view_contexts = dict(view_contexts or {})
        self.legacy_homography = homography
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.max_residual_ft = max_residual_ft
        self.envelope_margin_px = envelope_margin_px

    def _context_for(
        self,
        plan: RecoveryTickPlan,
        *,
        detector: Any | None,
        homography: list[list[float]] | None,
        inverse_homography: Any | None,
        orientation: Any | None,
        frame_width: int | None,
        frame_height: int | None,
    ) -> RefinementViewContext:
        context = self.view_contexts.get(plan.target_view)
        if context is not None:
            return context
        if detector is None:
            raise ValueError(f"missing refinement detector for target view {plan.target_view}")
        return RefinementViewContext(
            view_id=plan.target_view,
            frame_provider=None,
            detector=detector,
            homography=homography or self.legacy_homography or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            inverse_homography=inverse_homography,
            orientation=orientation,
            frame_width=int(frame_width or self.frame_width),
            frame_height=int(frame_height or self.frame_height),
        )

    def search_envelope(
        self,
        *,
        donor_position: tuple[float, float] | None,
        forward_position: tuple[float, float] | None,
        backward_position: tuple[float, float] | None,
        inverse_homography: Any,
        orientation: Any,
        frame_width: int | None = None,
        frame_height: int | None = None,
    ) -> tuple[float, float, float, float]:
        """Use donor as the center; anchors only expand uncertainty."""
        from app.vision.multiview.court_frame import canonical_to_local
        from app.vision.multiview.guidance import court_to_image_single

        width = float(frame_width or self.frame_width)
        height = float(frame_height or self.frame_height)
        if donor_position is None:
            return (0.0, 0.0, width, height)
        lx, ly = canonical_to_local(donor_position[0], donor_position[1], orientation)
        ix, iy = court_to_image_single((lx, ly), inverse_homography)
        anchor_distance = max(
            [
                0.0,
                *(
                    ((position[0] - donor_position[0]) ** 2 + (position[1] - donor_position[1]) ** 2) ** 0.5
                    for position in (forward_position, backward_position)
                    if position is not None
                ),
            ]
        )
        margin = self.envelope_margin_px + min(120.0, anchor_distance * 12.0)
        return (
            max(0.0, ix - margin),
            max(0.0, iy - margin),
            min(width, ix + margin),
            min(height, iy + margin),
        )

    def recover(
        self,
        *,
        plan: RecoveryTickPlan,
        frame: Any | None = None,
        detector: Any | None = None,
        inverse_homography: Any | None = None,
        orientation: Any | None = None,
        forward_position: tuple[float, float] | None = None,
        backward_position: tuple[float, float] | None = None,
        tracklet: RecoveryTracklet | None = None,
        candidates: list[Any] | None = None,
    ) -> RecoveredViewObservation | None:
        donor_position = plan.donor_canonical_position
        if donor_position is None:
            return None
        context = self._context_for(
            plan,
            detector=detector,
            homography=None,
            inverse_homography=inverse_homography,
            orientation=orientation,
            frame_width=None,
            frame_height=None,
        )
        if frame is None and context.frame_provider is not None and plan.target_source_frame_index is not None:
            frame = context.frame_provider(plan.target_source_frame_index)
        if frame is None:
            return None
        inverse = context.inverse_homography
        if inverse is None:
            return None
        roi = self.search_envelope(
            donor_position=donor_position,
            forward_position=forward_position,
            backward_position=backward_position,
            inverse_homography=inverse,
            orientation=context.orientation,
            frame_width=context.frame_width,
            frame_height=context.frame_height,
        )
        if candidates is None:
            try:
                candidates = context.detector.detect_regions(frame, [roi])
            except Exception:
                return None
        if not candidates:
            return None
        from app.vision.multiview.court_frame import canonical_to_local, local_to_canonical

        predicted_local = canonical_to_local(donor_position[0], donor_position[1], context.orientation)
        gated = [
            guided_candidate_pre_gate(
                candidate,
                homography=context.homography,
                predicted_local=predicted_local,
                max_residual_ft=self.max_residual_ft,
                frame_width=context.frame_width,
                frame_height=context.frame_height,
            )
            for candidate in candidates
        ]
        accepted = []
        for candidate in gated:
            if not candidate.accepted:
                continue
            canonical = local_to_canonical(candidate.canonical_position[0], candidate.canonical_position[1], context.orientation)
            residual = ((canonical[0] - donor_position[0]) ** 2 + (canonical[1] - donor_position[1]) ** 2) ** 0.5
            if residual <= self.max_residual_ft:
                accepted.append((residual, candidate, canonical))
        if not accepted:
            return None
        residual, best, canonical = min(accepted, key=lambda item: item[0])
        if tracklet is not None:
            tracklet.consecutive_hits += 1
            tracklet.previous_bbox = list(best.detection.bbox)
            tracklet.previous_canonical_position = canonical
        return RecoveredViewObservation(
            view_id=plan.target_view,
            take_timestamp_ms=plan.take_timestamp_ms,
            source_frame_index=int(plan.target_source_frame_index),
            canonical_x_ft=canonical[0],
            canonical_y_ft=canonical[1],
            bbox=list(best.detection.bbox),
            confidence=best.detection.confidence,
            detection_origin="offline_refinement",
            global_player_id=plan.global_player_id,
            canonical_tick=plan.canonical_tick,
            source_timestamp_ms=plan.target_source_timestamp_ms,
            mapped_take_timestamp_ms=plan.target_mapped_take_timestamp_ms,
            selection_error_ms=plan.target_selection_error_ms,
            timing_authority=plan.target_timing_authority,
            sync_quality=plan.target_sync_quality,
            donor_view=plan.donor_view,
            donor_source_frame_index=plan.donor_source_frame_index,
            donor_quality=plan.donor_quality,
            expected_global_position=plan.f0_global_position or donor_position,
            residual_ft=residual,
        )


@dataclass
class RefinementMetrics:
    eligible_coverage: float = 0.0
    jump_count: int = 0
    speed_violation_count: int = 0
    conflict_count: int = 0
    recovered_count: int = 0
    recovered_residual_p50: float = 0.0
    recovered_residual_p90: float = 0.0
    donor_inconsistency_count: int = 0
    original_strong_replaced: int = 0
    original_strong_preserved: int = 0


@dataclass(frozen=True)
class RefinementVerdict:
    accepted: bool
    reason: str


class RefinementAcceptanceGate:
    """Configurable F0 → candidate F1 safety gate."""

    def __init__(
        self,
        *,
        allowed_jump_delta: int = 2,
        allowed_speed_delta: int = 2,
        allowed_conflict_delta: int = 2,
        max_recovered_residual_p50: float = 3.0,
        max_recovered_residual_p90: float = 3.0,
    ) -> None:
        self.allowed_jump_delta = allowed_jump_delta
        self.allowed_speed_delta = allowed_speed_delta
        self.allowed_conflict_delta = allowed_conflict_delta
        self.max_recovered_residual_p50 = max_recovered_residual_p50
        self.max_recovered_residual_p90 = max_recovered_residual_p90

    def decide(self, f0: RefinementMetrics, f1: RefinementMetrics) -> RefinementVerdict:
        if f1.recovered_count == 0:
            return RefinementVerdict(False, "no_recovered_observations")
        if f1.eligible_coverage < f0.eligible_coverage:
            return RefinementVerdict(False, "coverage_decreased")
        if f1.jump_count - f0.jump_count > self.allowed_jump_delta:
            return RefinementVerdict(False, "jump_violations_increased")
        if f1.speed_violation_count - f0.speed_violation_count > self.allowed_speed_delta:
            return RefinementVerdict(False, "speed_violations_increased")
        if f1.conflict_count - f0.conflict_count > self.allowed_conflict_delta:
            return RefinementVerdict(False, "conflicts_increased")
        if f1.recovered_residual_p90 > self.max_recovered_residual_p90:
            return RefinementVerdict(False, "recovered_residual_p90_too_high")
        if f1.recovered_residual_p50 > self.max_recovered_residual_p50:
            return RefinementVerdict(False, "recovered_residual_too_high")
        if f1.donor_inconsistency_count > 0:
            return RefinementVerdict(False, "donor_inconsistent")
        if f1.original_strong_replaced > 0:
            return RefinementVerdict(False, "original_strong_replaced")
        return RefinementVerdict(True, "accepted")


@dataclass
class RefusionResult:
    samples: list[Any] = field(default_factory=list)
    metrics: RefinementMetrics = field(default_factory=RefinementMetrics)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    suppressed: list[dict[str, Any]] = field(default_factory=list)


def _canonical_observation(view_id: str, state: F0TickViewState | None):
    from app.vision.multiview.types import CanonicalObservation

    if state is None or not state.observed or state.canonical_position is None:
        return CanonicalObservation(
            view_id=view_id,
            view_status="unavailable",
            source_frame_index=state.source_frame_index if state else None,
            source_timestamp_ms=state.source_timestamp_ms if state else None,
            mapped_take_timestamp_ms=state.mapped_take_timestamp_ms if state else None,
            selection_error_ms=state.selection_error_ms if state else None,
        )
    return CanonicalObservation(
        view_id=view_id,
        view_status="available",
            source_frame_index=state.source_frame_index,
            source_timestamp_ms=state.source_timestamp_ms,
            mapped_take_timestamp_ms=state.mapped_take_timestamp_ms,
            selection_error_ms=state.selection_error_ms,
            timing_authority=state.timing_authority,
            sync_quality=state.sync_quality,
            canonical_x_ft=state.canonical_position[0],
        canonical_y_ft=state.canonical_position[1],
        view_player_id=state.view_player_id,
        detector_confidence=state.detector_confidence if state.detector_confidence is not None else state.quality,
        projection_confidence=state.projection_confidence,
        tracking_status=state.tracking_status,
        is_interpolated=state.origin == "predicted",
        observation_origin=state.origin,
    )


def merge_recovery_evidence(
    snapshot: F0RefinementSnapshot,
    recovered: list[RecoveredViewObservation],
) -> tuple[dict[tuple[str, int, str], RecoveredViewObservation], list[dict[str, Any]]]:
    """Deterministically freeze original/recovered precedence diagnostics."""
    selected: dict[tuple[str, int, str], RecoveredViewObservation] = {}
    diagnostics: list[dict[str, Any]] = []
    for item in sorted(recovered, key=lambda value: (value.global_player_id, value.canonical_tick, value.view_id, value.source_frame_index)):
        key = (item.global_player_id, item.canonical_tick, item.view_id)
        original = snapshot.state_for(item.global_player_id, item.view_id, item.canonical_tick)
        if original is not None and original.observed and original.origin == "base" and original.quality >= 0.55:
            diagnostics.append({"key": list(key), "reason": "suppressed_original_strong_priority"})
            continue
        if key in selected:
            diagnostics.append({"key": list(key), "reason": "suppressed_duplicate_recovered"})
            continue
        selected[key] = item
    return selected, diagnostics


def _sample_from_measurement(measurement: Any, *, observation_origin: str = "base"):
    from app.vision.multiview.joint_artifact import FusedSample

    details = dict(measurement.view_observations)
    return FusedSample(
        global_player_id=measurement.global_player_id,
        take_timestamp_ms=measurement.take_timestamp_ms,
        reference_frame_index=measurement.reference_frame_index,
        x_ft=float(measurement.x_ft or 0.0),
        y_ft=float(measurement.y_ft or 0.0),
        fusion_status=measurement.fusion_status,
        metric_eligible=bool(measurement.metric_eligible),
        observation_origin=observation_origin,
        view_observations=details,
        contributing_views=list(measurement.contributing_views),
        identity_status=(
            "confirmed_recovered" if observation_origin == "offline_refinement" else "confirmed_observed"
        ),
    )


def refusion_frozen_snapshot(
    *,
    snapshot: F0RefinementSnapshot,
    recovered: list[RecoveredViewObservation],
    reference_view_id: str | None = None,
    secondary_view_id: str | None = None,
    f0_samples: list[Any] | None = None,
    fusion_config: Any | None = None,
    sync_quality: str = "unknown",
) -> RefusionResult:
    """Run formal pair/quality/conflict fusion and a fresh temporal filter."""
    from dataclasses import replace as dc_replace

    from app.vision.multiview.fusion import FusionConfig, fuse_observation
    from app.vision.multiview.global_filter import GlobalTrackFilter
    from app.vision.multiview.quality import intrinsic_from_canonical, pair_consistency, view_intrinsic_quality

    reference = reference_view_id or snapshot.reference_view_id
    other_views = [view for view in snapshot.view_ids if view != reference]
    secondary = secondary_view_id or (other_views[0] if other_views else "cam_2")
    config = fusion_config or FusionConfig()
    recovered_by_key, suppressed = merge_recovery_evidence(snapshot, recovered)
    filter_ = GlobalTrackFilter()
    samples: list[Any] = []
    for tick in snapshot.ticks:
        if not tick.metric_scope:
            continue
        for gid in snapshot.global_player_ids:
            ref_state = snapshot.state_for(gid, reference, tick.canonical_tick)
            sec_state = snapshot.state_for(gid, secondary, tick.canonical_tick)
            ref_obs = _canonical_observation(reference, ref_state)
            sec_obs = _canonical_observation(secondary, sec_state)
            selected_recovered: list[RecoveredViewObservation] = []
            for view_id, current in ((reference, ref_obs), (secondary, sec_obs)):
                item = recovered_by_key.get((gid, tick.canonical_tick, view_id))
                if item is None:
                    continue
                selected_recovered.append(item)
                replacement = _canonical_observation(
                    view_id,
                    F0TickViewState(
                        observed=True,
                        quality=item.confidence,
                        canonical_position=(item.canonical_x_ft, item.canonical_y_ft),
                        origin="offline_refinement",
                        source_frame_index=item.source_frame_index,
                        source_timestamp_ms=item.source_timestamp_ms,
                        mapped_take_timestamp_ms=item.mapped_take_timestamp_ms,
                        selection_error_ms=item.selection_error_ms,
                        timing_authority=item.timing_authority,
                        sync_quality=item.sync_quality,
                        detector_confidence=item.confidence,
                        bbox=tuple(item.bbox),
                        observation_status="observed",
                    ),
                )
                if view_id == reference:
                    ref_obs = replacement
                else:
                    sec_obs = replacement
            predicted = filter_.predict(tick.canonical_timestamp_ms / 1000.0).get(gid)
            pair = pair_consistency(
                (ref_obs.canonical_x_ft, ref_obs.canonical_y_ft) if ref_obs.view_status == "available" and ref_obs.canonical_x_ft is not None else None,
                (sec_obs.canonical_x_ft, sec_obs.canonical_y_ft) if sec_obs.view_status == "available" and sec_obs.canonical_x_ft is not None else None,
                predicted,
                max_plausible_distance_ft=config.max_plausible_distance_ft,
            )
            measurement = fuse_observation(
                global_player_id=gid,
                timestamp_seconds=tick.canonical_timestamp_ms / 1000.0,
                take_timestamp_ms=tick.canonical_timestamp_ms,
                reference_frame_index=tick.reference_frame_index,
                reference_obs=ref_obs,
                secondary_obs=sec_obs,
                reference_intrinsic=view_intrinsic_quality(intrinsic_from_canonical(ref_obs)),
                secondary_intrinsic=view_intrinsic_quality(intrinsic_from_canonical(sec_obs)),
                pair=pair,
                predicted=predicted,
                sync_quality=sync_quality,
                config=config,
                reference_label=reference,
                secondary_label=secondary,
            )
            if measurement is None:
                if predicted is None:
                    continue
                from app.vision.multiview.joint_artifact import FusedSample

                samples.append(
                    FusedSample(
                        global_player_id=gid,
                        take_timestamp_ms=tick.canonical_timestamp_ms,
                        reference_frame_index=tick.reference_frame_index,
                        x_ft=predicted[0],
                        y_ft=predicted[1],
                        fusion_status="predicted",
                        metric_eligible=False,
                        observation_origin="base",
                        view_observations={},
                        contributing_views=[],
                        identity_status="unresolved",
                        quarantine_reason="predicted_without_observation",
                    )
                )
                continue
            if measurement.metric_eligible and measurement.x_ft is not None and measurement.y_ft is not None:
                smoothed = filter_.update(gid, measurement.x_ft, measurement.y_ft, tick.canonical_timestamp_ms / 1000.0)
                measurement = dc_replace(measurement, x_ft=smoothed[0], y_ft=smoothed[1])
            origin = "offline_refinement" if selected_recovered else "base"
            for item in selected_recovered:
                for detail in measurement.view_observations.values():
                    if detail.get("view_id") == item.view_id:
                        detail["observation_origin"] = "offline_refinement"
                        detail["residual_ft"] = item.residual_ft
                        detail["donor_view"] = item.donor_view
            samples.append(_sample_from_measurement(measurement, observation_origin=origin))
    samples.sort(key=lambda sample: (sample.take_timestamp_ms, sample.global_player_id))
    f0_metric = _trajectory_metrics(f0_samples or [], recovered=[], snapshot=snapshot)
    f1_metric = _trajectory_metrics(samples, recovered=recovered, snapshot=snapshot)
    return RefusionResult(
        samples=samples,
        metrics=f1_metric,
        suppressed=suppressed,
        diagnostics={"f0_metrics": _metrics_to_dict(f0_metric), "f1_metrics": _metrics_to_dict(f1_metric)},
    )


def _trajectory_metrics(
    samples: list[Any],
    *,
    recovered: list[RecoveredViewObservation],
    snapshot: F0RefinementSnapshot,
    max_jump_ft: float = 3.0,
    max_speed_ft_s: float = 30.0,
) -> RefinementMetrics:
    eligible = [sample for sample in samples if sample.metric_eligible and sample.fusion_status != "predicted"]
    total = max(1, sum(1 for tick in snapshot.ticks if tick.metric_scope) * max(1, len(snapshot.global_player_ids)))
    by_gid: dict[str, list[Any]] = {}
    for sample in samples:
        by_gid.setdefault(sample.global_player_id, []).append(sample)
    jumps = 0
    speeds = 0
    for rows in by_gid.values():
        rows.sort(key=lambda sample: sample.take_timestamp_ms)
        for previous, current in zip(rows, rows[1:], strict=False):
            distance = ((current.x_ft - previous.x_ft) ** 2 + (current.y_ft - previous.y_ft) ** 2) ** 0.5
            if distance > max_jump_ft:
                jumps += 1
            dt = max((current.take_timestamp_ms - previous.take_timestamp_ms) / 1000.0, 1e-3)
            if distance / dt > max_speed_ft_s:
                speeds += 1
    residuals = sorted(item.residual_ft for item in recovered if item.residual_ft is not None)
    p50 = float(median(residuals)) if residuals else 0.0
    p90 = float(residuals[min(len(residuals) - 1, int(len(residuals) * 0.9))]) if residuals else 0.0
    original_strong_keys = _snapshot_original_strong_keys(snapshot)
    tick_by_timestamp = {
        round(tick.canonical_timestamp_ms, 3): tick.canonical_tick
        for tick in snapshot.ticks
        if tick.metric_scope
    }
    preserved_keys: set[tuple[str, int, str]] = set()
    for sample in samples:
        canonical_tick = tick_by_timestamp.get(round(float(sample.take_timestamp_ms), 3))
        if canonical_tick is None:
            continue
        for view_id, detail in sample.view_observations.items():
            if detail.get("observation_origin", detail.get("origin", "base")) == "base":
                key = (sample.global_player_id, canonical_tick, view_id)
                if key in original_strong_keys:
                    preserved_keys.add(key)
    conflicts = sum(1 for sample in samples if sample.fusion_status == "conflict")
    donor_inconsistency = sum(
        1
        for item in recovered
        if item.expected_global_position is not None
        and item.residual_ft is not None
        and item.residual_ft > max_jump_ft
    )
    return RefinementMetrics(
        eligible_coverage=len(eligible) / total,
        jump_count=jumps,
        speed_violation_count=speeds,
        conflict_count=conflicts,
        recovered_count=len(recovered),
        recovered_residual_p50=p50,
        recovered_residual_p90=p90,
        donor_inconsistency_count=donor_inconsistency,
        original_strong_preserved=len(preserved_keys),
    )


def _metrics_to_dict(metrics: RefinementMetrics) -> dict[str, object]:
    return {
        "eligible_coverage": metrics.eligible_coverage,
        "jump_violation_count": metrics.jump_count,
        "speed_violation_count": metrics.speed_violation_count,
        "conflict_count": metrics.conflict_count,
        "recovered_count": metrics.recovered_count,
        "recovered_residual_p50": metrics.recovered_residual_p50,
        "recovered_residual_p90": metrics.recovered_residual_p90,
        "donor_inconsistency_count": metrics.donor_inconsistency_count,
        "original_strong_preserved": metrics.original_strong_preserved,
        "original_strong_replaced": metrics.original_strong_replaced,
    }


def _snapshot_original_strong_count(snapshot: F0RefinementSnapshot) -> int:
    return len(_snapshot_original_strong_keys(snapshot))


def _snapshot_original_strong_keys(
    snapshot: F0RefinementSnapshot,
) -> set[tuple[str, int, str]]:
    """Stable F0 strong-evidence keys used by both F0 and F1 metrics."""
    return {
        (global_player_id, tick.canonical_tick, view_id)
        for tick in snapshot.ticks
        if tick.metric_scope
        for global_player_id, view_id, state in tick.observations
        if state.observed and state.origin == "base" and state.quality >= 0.55
    }


@dataclass
class RefinementOutcome:
    status: Literal["skipped_no_windows", "completed", "rejected_by_safety_gate", "failed_fallback"]
    final_source: Literal["refined_f1", "first_pass_f0"]
    recovered: list[RecoveredViewObservation] = field(default_factory=list)
    candidate_samples: list[Any] = field(default_factory=list)
    metrics: RefinementMetrics = field(default_factory=RefinementMetrics)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    # stabilize-joint-global-player-roster：F1 冻结 roster 映射——refinement 输出
    # 的 global_player_id 必须是 F0 snapshot 的子集（不新增 slot、不改映射）。
    roster_frozen: bool = True


def run_offline_refinement(
    *,
    snapshot: F0RefinementSnapshot | None = None,
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]] | None = None,
    f0_source_frames: dict[str, dict[int, int | None]] | None = None,
    f0_global_positions: dict[str, dict[int, tuple[float, float]]] | None = None,
    tick_metadata: Mapping[int, Mapping[str, Any]] | None = None,
    view_contexts: Mapping[str, RefinementViewContext] | None = None,
    frame_provider: Any | None = None,
    detector: Any | None = None,
    homography: list[list[float]] | None = None,
    inverse_homography: Any | None = None,
    orientation_by_view: dict[str, Any] | None = None,
    frame_width: int = 0,
    frame_height: int = 0,
    f0_samples: list[Any] | None = None,
    config: RefinementConfigSnapshot | None = None,
    missing_after_ticks: int = 3,
    donor_min_quality: float = 0.5,
    max_residual_ft: float = 3.0,
    views: tuple[str, ...] = ("cam_1", "cam_2"),
    reference_view_id: str = "cam_1",
    secondary_view_id: str = "cam_2",
    sync_quality: str = "unknown",
) -> RefinementOutcome:
    """Execute Recovery → freeze → formal Refusion → safety gate."""
    try:
        if snapshot is None:
            snapshot = snapshot_from_legacy_trace(
                f0_trace=f0_trace or {},
                f0_source_frames=f0_source_frames,
                f0_global_positions=f0_global_positions,
                tick_metadata=tick_metadata,
                views=views,
                config_snapshot=(config.to_dict() if config else {}),
            )
        config = config or RefinementConfigSnapshot.from_online(
            {"min_donor_quality": donor_min_quality, "missing_after_ticks": missing_after_ticks, "max_residual_ft": max_residual_ft}
        )
        trace, _ = _trace_and_snapshot(snapshot)
        windows = mine_recovery_windows(
            snapshot,
            views=views,
            missing_after_ticks=config.missing_after_ticks,
            donor_min_quality=config.min_donor_quality,
        )
        if not windows:
            return RefinementOutcome(
                status="skipped_no_windows",
                final_source="first_pass_f0",
                diagnostics={"config": config.to_dict(), "windows": 0},
            )
        frozen_windows: list[FrozenRecoveryWindow] = []
        for window in windows:
            build_recovery_tick_plans(
                window,
                snapshot,
                f0_source_frames=f0_source_frames,
                f0_global_positions=f0_global_positions,
                donor_min_quality=config.min_donor_quality,
            )
            frozen_windows.append(window.freeze())
        recovery = OfflineRecovery(
            view_contexts=view_contexts,
            homography=homography,
            frame_width=frame_width,
            frame_height=frame_height,
            max_residual_ft=config.max_residual_ft,
        )
        recovered: list[RecoveredViewObservation] = []
        work_items: list[dict[str, Any]] = []
        for window in frozen_windows:
            tracklet = RecoveryTracklet(
                recovery_window_id=f"{window.global_player_id}:{window.target_view}:{window.start_tick}"
            )
            positions = {
                tick.canonical_tick: tick.position_for(window.global_player_id)
                for tick in snapshot.ticks
                if tick.position_for(window.global_player_id) is not None
            }
            for plan in tuple(window.ticks):
                target_context = (view_contexts or {}).get(plan.target_view)
                if (
                    plan.target_source_frame_index is None
                    or (
                        target_context is None
                        and frame_provider is None
                    )
                    or (
                        target_context is not None
                        and target_context.frame_provider is None
                        and frame_provider is None
                    )
                ):
                    continue
                prior_ticks = [tick for tick in positions if tick < plan.canonical_tick]
                next_ticks = [tick for tick in positions if tick > plan.canonical_tick]
                before = positions[max(prior_ticks)] if prior_ticks else None
                after = positions[min(next_ticks)] if next_ticks else None
                work_items.append(
                    {
                        "plan": plan,
                        "tracklet": tracklet,
                        "context": target_context,
                        "before": before,
                        "after": after,
                    }
                )

        # Real F1 runs commonly contain several global targets in the same
        # source frame. Cache each seek and batch ROI inference when the
        # detector supports it; test/legacy detectors keep the old path.
        legacy_items: list[dict[str, Any]] = []
        grouped_items: dict[tuple[str, int, int], list[tuple[int, dict[str, Any]]]] = {}
        for index, item in enumerate(work_items):
            plan = item["plan"]
            context = item["context"]
            selected_detector = context.detector if context is not None else detector
            if context is None:
                legacy_items.append(item)
                continue
            key = (plan.target_view, int(plan.target_source_frame_index), id(selected_detector))
            grouped_items.setdefault(key, []).append((index, item))

        for items in sorted(
            grouped_items.values(),
            key=lambda group: (
                group[0][1]["plan"].target_view,
                int(group[0][1]["plan"].target_source_frame_index or -1),
            ),
        ):
            first_item = items[0][1]
            first_plan = first_item["plan"]
            context = first_item["context"]
            if context is not None and context.frame_provider is not None:
                frame = context.frame_provider(int(first_plan.target_source_frame_index))
            elif frame_provider is not None:
                frame = frame_provider(first_plan.target_view, int(first_plan.target_source_frame_index))
            else:
                frame = None
            if frame is None:
                continue

            regions: list[tuple[float, float, float, float]] = []
            for _index, item in items:
                plan = item["plan"]
                if context is None or plan.donor_canonical_position is None:
                    regions.append((0.0, 0.0, 0.0, 0.0))
                    continue
                regions.append(
                    recovery.search_envelope(
                        donor_position=plan.donor_canonical_position,
                        forward_position=item["before"],
                        backward_position=item["after"],
                        inverse_homography=context.inverse_homography,
                        orientation=context.orientation,
                        frame_width=context.frame_width,
                        frame_height=context.frame_height,
                    )
                )

            selected_detector = context.detector if context is not None else detector
            batch_detector = getattr(selected_detector, "detect_regions_batch", None)
            try:
                if callable(batch_detector):
                    grouped = batch_detector(frame, regions)
                else:
                    grouped = [selected_detector.detect_regions(frame, [region]) for region in regions]
            except Exception:
                grouped = [[] for _ in regions]
            for (index, item), candidates in zip(items, grouped, strict=False):
                plan = item["plan"]
                target_context = item["context"]
                result = recovery.recover(
                    plan=plan,
                    frame=frame,
                    detector=selected_detector,
                    inverse_homography=(target_context.inverse_homography if target_context else inverse_homography),
                    orientation=(target_context.orientation if target_context else (orientation_by_view or {}).get(plan.target_view)),
                    forward_position=item["before"],
                    backward_position=item["after"],
                    tracklet=item["tracklet"],
                    candidates=list(candidates),
                )
                if result is not None:
                    recovered.append(result)

        for item in legacy_items:
            plan = item["plan"]
            frame = (
                frame_provider(plan.target_view, int(plan.target_source_frame_index))
                if frame_provider is not None and plan.target_source_frame_index is not None
                else None
            )
            result = recovery.recover(
                plan=plan,
                frame=frame,
                detector=detector,
                inverse_homography=inverse_homography,
                orientation=(orientation_by_view or {}).get(plan.target_view),
                forward_position=item["before"],
                backward_position=item["after"],
                tracklet=item["tracklet"],
            )
            if result is not None:
                recovered.append(result)
        if not recovered:
            return RefinementOutcome(
                status="skipped_no_windows",
                final_source="first_pass_f0",
                diagnostics={"config": config.to_dict(), "windows": len(windows), "recovered_count": 0},
            )
        frozen_recovered = list(recovered)
        refusion = refusion_frozen_snapshot(
            snapshot=snapshot,
            recovered=frozen_recovered,
            reference_view_id=reference_view_id,
            secondary_view_id=secondary_view_id,
            f0_samples=f0_samples,
            sync_quality=sync_quality,
        )
        f0_metrics = _trajectory_metrics(f0_samples or [], recovered=[], snapshot=snapshot)
        refusion.metrics.original_strong_replaced = max(
            0,
            _snapshot_original_strong_count(snapshot) - refusion.metrics.original_strong_preserved,
        )
        gate = RefinementAcceptanceGate(
            allowed_jump_delta=config.allowed_jump_delta,
            allowed_speed_delta=config.allowed_speed_delta,
            allowed_conflict_delta=config.allowed_conflict_delta,
            max_recovered_residual_p90=config.max_recovered_residual_p90,
        )
        verdict = gate.decide(f0_metrics, refusion.metrics)
        # F1 冻结 roster 映射（stabilize-joint-global-player-roster）：refusion 样本的
        # global_player_id 必须 ⊆ F0 snapshot 的 global_player_ids，绝不新增/重映射。
        f0_gids = set(snapshot.global_player_ids)
        refined_gids = {getattr(s, "global_player_id", None) for s in refusion.samples}
        roster_frozen = all(gid in f0_gids for gid in refined_gids if gid)
        diagnostics = {
            "config": config.to_dict(),
            "windows": len(windows),
            "metrics": {"f0": _metrics_to_dict(f0_metrics), "f1": _metrics_to_dict(refusion.metrics)},
            "thresholds": config.to_dict(),
            "verdict": "accepted" if verdict.accepted else "rejected",
            "reject_reason": None if verdict.accepted else verdict.reason,
            "suppressed": refusion.suppressed,
            "roster_frozen": roster_frozen,
        }
        return RefinementOutcome(
            status="completed" if verdict.accepted else "rejected_by_safety_gate",
            final_source="refined_f1" if verdict.accepted else "first_pass_f0",
            recovered=frozen_recovered,
            candidate_samples=refusion.samples,
            metrics=refusion.metrics,
            diagnostics=diagnostics,
            reason=verdict.reason,
            roster_frozen=roster_frozen,
        )
    except Exception as exc:  # noqa: BLE001
        return RefinementOutcome(
            status="failed_fallback",
            final_source="first_pass_f0",
            reason=str(exc),
            diagnostics={"error": str(exc)},
        )


def _tick_of(plan: RecoveryTickPlan) -> int:
    return plan.canonical_tick


def _coverage(f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]]) -> float:
    total = sum(len(ticks) for views in f0_trace.values() for ticks in views.values())
    observed = sum(
        sum(1 for state in ticks.values() if state.observed)
        for views in f0_trace.values()
        for ticks in views.values()
    )
    return observed / max(1, total)


def _coverage_with(
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]],
    recovered: list[RecoveredViewObservation],
) -> float:
    total = max(1, sum(len(ticks) for views in f0_trace.values() for ticks in views.values()))
    observed = sum(
        sum(1 for state in ticks.values() if state.observed)
        for views in f0_trace.values()
        for ticks in views.values()
    )
    return min(1.0, (observed + len(recovered)) / total)


def refuse_f1(
    f0_samples: list[Any],
    recovered: list[RecoveredViewObservation],
    *,
    original_strong_priority: bool = True,
) -> list[Any]:
    """Deprecated compatibility helper; executor must use formal refusion.

    It remains only for old artifact readers/tests.  It never labels a fused
    sample with ``offline_refinement`` and never forces metric eligibility.
    """
    from app.vision.multiview.joint_artifact import FusedSample

    samples = list(f0_samples)
    for item in recovered:
        duplicate = any(
            sample.global_player_id == item.global_player_id
            and abs(sample.take_timestamp_ms - item.take_timestamp_ms) < 1.0
            for sample in samples
        )
        if duplicate and original_strong_priority:
            continue
        samples.append(
            FusedSample(
                global_player_id=item.global_player_id,
                take_timestamp_ms=item.take_timestamp_ms,
                reference_frame_index=item.source_frame_index,
                x_ft=item.canonical_x_ft,
                y_ft=item.canonical_y_ft,
                fusion_status="single_view_fallback",
                metric_eligible=False,
                observation_origin="offline_refinement",
                view_observations={item.view_id: {"view_id": item.view_id, "observation_origin": "offline_refinement"}},
                contributing_views=[item.view_id],
                identity_status="confirmed_recovered",
            )
        )
    return samples
