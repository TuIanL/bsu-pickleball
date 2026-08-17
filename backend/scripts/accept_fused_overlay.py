"""fused overlay 真实素材验收脚本（task 8.1/8.2）。

从真实 joint run 产物（debug trace + fused trajectory）重建 F0/F1 evidence，
运行 FusedPlayerOverlayBuilder 生成 `multiview-fused-player-overlay.v1`，
度量：
- `reference_observed_coverage`（baseline：reference view 自身真实观测覆盖率）
- `fused_overlay_coverage`（measured：最终可靠 overlay 覆盖率）
- 硬不变量计数（spec multiview-visual-acceptance）

用法：
    python scripts/accept_fused_overlay.py \
        --trace <joint_debug_trace.v1.json> \
        --trajectory <fused_player_trajectory.f0.v2.json> \
        [--recovered <recovered_view_observations.v1.json>] \
        [--reference-view cam_1] [--roster global_player_1=Player_1,...]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING)

from app.vision.multiview.fused_overlay_builder import FusedPlayerOverlayBuilder, OverlayBuilderConfig
from app.vision.multiview.fused_overlay_bundle import (
    ViewGeometry,
    build_overlay_evidence_bundle,
)
from app.vision.multiview.fused_overlay_types import count_overlay_invariants
from app.vision.multiview.offline_refinement import (
    F0RefinementSnapshot,
    F0TickSnapshot,
    F0TickViewState,
    RecoveredViewObservation,
)
from app.vision.multiview.court_frame import CourtOrientation

# 默认 10x 缩放的假想 homography 不可用——真实验收必须传 homography；
# 未传时 geometry 缺失 → cross_view/predicted 投影降级为 unavailable（如实反映）。
_DEFAULT_ROSTER = {}


def _orientation(value: str) -> CourtOrientation | None:
    try:
        return CourtOrientation(value)
    except ValueError:
        return None


def build_f0_snapshot(trace: dict) -> F0RefinementSnapshot:
    """从 joint_debug_trace.v1 重建 F0RefinementSnapshot。"""
    ticks: list[F0TickSnapshot] = []
    global_ids: set[str] = set()
    view_ids: set[str] = set()
    for tick in trace["ticks"]:
        observations: list[tuple[str, str, F0TickViewState]] = []
        for raw in tick.get("canonical_observations", []):
            if not isinstance(raw, dict):
                continue
            gid = str(raw.get("global_player_id", ""))
            view_id = str(raw.get("view_id", ""))
            if not gid or not view_id:
                continue
            global_ids.add(gid)
            view_ids.add(view_id)
            bbox = raw.get("bbox")
            state = F0TickViewState(
                observed=True,
                quality=float(raw.get("confidence") or 0.0),
                canonical_position=(
                    float(raw.get("canonical_x_ft") or 0.0),
                    float(raw.get("canonical_y_ft") or 0.0),
                ),
                origin=str(raw.get("detection_origin") or "base"),
                source_frame_index=int(raw.get("source_frame_index") or 0),
                source_timestamp_ms=_opt_float(raw.get("source_timestamp_ms")),
                mapped_take_timestamp_ms=_opt_float(raw.get("mapped_take_timestamp_ms")),
                selection_error_ms=_opt_float(raw.get("selection_error_ms")),
                timing_authority=str(raw.get("timing_authority") or "missing"),
                sync_quality=str(raw.get("sync_quality") or "unknown"),
                view_status="available",
                observation_status="observed",
                view_player_id=str(raw.get("view_player_id") or ""),
                detector_confidence=float(raw.get("confidence") or 0.0),
                projection_confidence=None,
                tracking_status=str(raw.get("tracking_status") or "detected"),
                bbox=tuple(float(v) for v in bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else None,
            )
            observations.append((gid, view_id, state))
        fused = tick.get("fused") or {}
        global_positions = tuple(
            (str(gid), (float(pos["x_ft"]), float(pos["y_ft"])))
            for gid, pos in fused.items()
            if isinstance(pos, dict) and pos.get("x_ft") is not None
        )
        predictions = tuple(
            (str(gid), (float(v[0]), float(v[1])))
            for gid, v in (tick.get("global_predictions") or {}).items()
            if isinstance(v, (list, tuple)) and len(v) >= 2
        )
        ticks.append(
            F0TickSnapshot(
                canonical_tick=int(tick.get("canonical_tick") or 0),
                canonical_timestamp_ms=float(tick.get("canonical_timestamp_ms") or 0.0),
                reference_frame_index=int(tick.get("reference_frame_index") or 0),
                observations=tuple(observations),
                global_positions=global_positions,
                predictions=predictions,
            )
        )
    return F0RefinementSnapshot(
        run_id=str(trace.get("run_id", "")),
        capture_take_id=str(trace.get("capture_take_id", "")),
        reference_view_id=str(trace.get("reference_view_id", "cam_1")),
        view_ids=tuple(sorted(view_ids)) or ("cam_1", "cam_2"),
        global_player_ids=tuple(sorted(global_ids)),
        ticks=tuple(ticks),
    )


def build_geometry(
    frame_width: int,
    frame_height: int,
    orientations: dict[str, CourtOrientation],
    homographies: dict[str, list[list[float]] | None],
) -> dict[str, ViewGeometry]:
    geometry: dict[str, ViewGeometry] = {}
    for view_id, orientation in orientations.items():
        inverse = homographies.get(view_id)
        if inverse is None:
            continue
        geometry[view_id] = ViewGeometry(
            view_id=view_id,
            orientation=orientation,
            inverse_homography=inverse,
            frame_width=frame_width,
            frame_height=frame_height,
        )
    return geometry


def _opt_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def measure(payload: dict, total_ticks: int, reference_view_id: str) -> dict:
    """度量双覆盖率与硬不变量。"""
    reference_observed = 0
    fused_covered = 0
    per_tick_player_counts: list[int] = []
    for frame in payload["frames"]:
        players = frame.get("players", [])
        # reference 观测覆盖：该 tick 是否有任何 reference view 真实观测（base/guided/refined）
        observed_ref = any(
            p.get("evidence_type") in {"base_observed", "guided_observed", "refined_observed"}
            for p in players
        )
        if observed_ref:
            reference_observed += 1
        # fused overlay 覆盖：该 tick 是否有任何可见 overlay 实体
        if players:
            fused_covered += 1
            per_tick_player_counts.append(len(players))
    return {
        "total_ticks": total_ticks,
        "reference_observed_coverage": round(reference_observed / max(1, total_ticks), 4),
        "fused_overlay_coverage": round(fused_covered / max(1, total_ticks), 4),
        "coverage_gain_pp": round((fused_covered - reference_observed) / max(1, total_ticks) * 100, 2),
        "avg_players_per_tick": round(sum(per_tick_player_counts) / max(1, len(per_tick_player_counts)), 2),
        "invariants": count_overlay_invariants(payload, expected_player_count=4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="fused overlay 真实素材验收")
    parser.add_argument("--trace", required=True, help="joint_debug_trace.v1.json 路径")
    parser.add_argument("--trajectory", required=True, help="fused_player_trajectory 路径（f0 或 f1）")
    parser.add_argument("--recovered", default=None, help="recovered_view_observations.v1.json（可选）")
    parser.add_argument("--reference-view", default="cam_1")
    parser.add_argument("--frame-width", type=int, default=1920)
    parser.add_argument("--frame-height", type=int, default=1080)
    parser.add_argument("--orientation", action="append", default=[], help="view_id=identity 形式")
    parser.add_argument("--homography", action="append", default=[], help="view_id=<path-to-homography-json>")
    parser.add_argument("--roster", default=None, help="global_player_1=Player_1,...")
    args = parser.parse_args()

    trace = json.loads(Path(args.trace).read_text(encoding="utf-8"))
    trajectory = json.loads(Path(args.trajectory).read_text(encoding="utf-8"))

    f0_snapshot = build_f0_snapshot(trace)

    orientations: dict[str, CourtOrientation] = {}
    for item in args.orientation:
        view_id, value = item.split("=", 1)
        orientation = _orientation(value)
        if orientation is not None:
            orientations[view_id] = orientation
    # 默认取 trace 的 timing_authority_by_view keys + reference
    if not orientations:
        for view_id in f0_snapshot.view_ids:
            orientations[view_id] = CourtOrientation.identity

    homographies: dict[str, list[list[float]] | None] = {}
    for item in args.homography:
        view_id, path = item.split("=", 1)
        homographies[view_id] = json.loads(Path(path).read_text(encoding="utf-8"))
    if not homographies:
        logging.warning("未提供 homography：cross_view/predicted 投影将降级为 unavailable")

    geometry = build_geometry(args.frame_width, args.frame_height, orientations, homographies)

    recovered: list[RecoveredViewObservation] = []
    if args.recovered:
        recovered_payload = json.loads(Path(args.recovered).read_text(encoding="utf-8"))
        for raw in recovered_payload.get("observations", []):
            recovered.append(
                RecoveredViewObservation(
                    view_id=str(raw.get("view_id", "")),
                    take_timestamp_ms=float(raw.get("take_timestamp_ms", 0.0)),
                    source_frame_index=int(raw.get("source_frame_index", 0)),
                    canonical_x_ft=float(raw.get("canonical_x_ft", 0.0)),
                    canonical_y_ft=float(raw.get("canonical_y_ft", 0.0)),
                    bbox=tuple(float(v) for v in raw.get("bbox", [])),
                    confidence=float(raw.get("confidence", 0.0)),
                    global_player_id=str(raw.get("global_player_id", "")),
                    canonical_tick=int(raw.get("canonical_tick", 0)),
                )
            )

    roster_map: dict[str, str] = {}
    if args.roster:
        for item in args.roster.split(","):
            gid, pid = item.split("=", 1)
            roster_map[gid] = pid

    bundle = build_overlay_evidence_bundle(
        f0_snapshot=f0_snapshot,
        reference_view_id=args.reference_view,
        roster_map=roster_map,
        view_geometry=geometry,
        fused_trajectory=trajectory,
        recovered_observations=recovered,
        final_source="refined_f1" if args.recovered else "first_pass_f0",
    )
    builder = FusedPlayerOverlayBuilder(OverlayBuilderConfig())
    frames = builder.build(bundle=bundle)

    from app.vision.multiview.fused_overlay_types import build_fused_player_overlay_payload

    payload = build_fused_player_overlay_payload(
        job_id="acceptance",
        video_id=None,
        reference_view_id=args.reference_view,
        frame_size={"width": args.frame_width, "height": args.frame_height},
        frames=frames,
    )
    report = measure(payload, total_ticks=len(f0_snapshot.ticks), reference_view_id=args.reference_view)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
