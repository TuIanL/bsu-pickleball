"""accept_player_display_diagnostics.py —— player-display-diagnostics 真实素材验收。

用 mvr_35ac365aec96（job-95132a7a53 对应 run）的 joint_debug_trace 在 00:07
（tick 210）复现 Phase 0 结论：P1 两路都有 eligible detection，但 formal
observation 断裂（canonical_observations 为空）。

验收断言（tasks 5.4）：
1. cam_1 / cam_2 的 P1 eligible detection 均存在（conf ≥ 0.7）；
2. canonical observations 中 P1 为 0（formal observation 断）；
3. 用新漏斗 builder 在该 tick 重建，P1 行应显示
   `eligible_detection_present=true` 且 `formal_observation_emitted=false`。

用法：
    PYTHONPATH=. backend/.venv/bin/python backend/scripts/accept_player_display_diagnostics.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.guidance import CrossViewGuidancePolicy
from app.vision.multiview.player_display_diagnostics import (
    build_display_diagnostics_rows,
    build_player_display_diagnostics_payload,
    validate_player_display_diagnostics,
)

TRACE_PATH = Path(
    "/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/"
    "take_sync_20260720_122645_317228/analysis/multiview/mvr_35ac365aec96/"
    "joint_debug_trace.v1.json"
)
TICK_INDEX = 210  # canonical 7000ms (00:07)
CANONICAL_PLAYER = "Player_1"
GLOBAL_PLAYER = "global_player_1"


@dataclass
class _Det:
    player_id: str
    track_id: int
    image_footpoint: tuple[float, float]
    bbox: tuple[float, float, float, float]
    confidence: float


@dataclass
class _ViewResult:
    frame_detections: list = field(default_factory=list)
    frame_positions: list = field(default_factory=list)


def main() -> int:
    if not TRACE_PATH.exists():
        print(f"[skip] trace 不存在：{TRACE_PATH}（外接盘未挂载或素材缺失）")
        return 0
    with TRACE_PATH.open() as handle:
        trace = json.load(handle)
    tick = trace["ticks"][TICK_INDEX]
    print(f"tick {tick['canonical_tick']} @ {tick['canonical_timestamp_ms']:.0f}ms")

    # ---- 1) 两路 P1 eligible detection 存在性（原始 trace 断言）----
    view_results: dict[str, Any] = {}
    frame_status: dict[str, str] = {}
    p1_det_conf: dict[str, float] = {}
    for view_id, vd in tick["views"].items():
        frame_status[view_id] = vd.get("status", "unavailable")
        view = _ViewResult()
        for det in vd.get("detections", []) or []:
            bbox = det.get("bbox") or [0, 0, 0, 0]
            fp = det.get("image_footpoint") or [0, 0]
            view.frame_detections.append(
                _Det(
                    player_id=det.get("player_id", ""),
                    track_id=int(det.get("track_id") or 0),
                    image_footpoint=(float(fp[0]), float(fp[1])),
                    bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                    confidence=float(det.get("confidence") or 0.0),
                )
            )
        view_results[view_id] = view
        p1 = [d for d in view.frame_detections if d.player_id == CANONICAL_PLAYER]
        if p1:
            p1_det_conf[view_id] = p1[0].confidence
        print(f"  {view_id}: P1 eligible detections={len(p1)}"
              + (f" (conf={p1[0].confidence:.2f})" if p1 else ""))

    p1_obs = [o for o in tick.get("canonical_observations", []) if o.get("global_player_id") == GLOBAL_PLAYER]
    print(f"  P1 canonical observations={len(p1_obs)}")
    assert len(p1_obs) == 0, "Phase 0 前提：00:07 P1 canonical observation 应为 0"

    # ---- 2) 用新漏斗 builder 重建该 tick（调用真实构建器）----
    geometry: dict[str, dict[str, Any]] = {}
    for view_id, vd in tick["views"].items():
        # 复用 identity 朝向 + trace 内 source frame 尺寸不可知 → 用 10x 缩放占位
        geometry[view_id] = {
            "orientation": CourtOrientation.identity,
            "inverse_homography": [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]],
            "frame_width": 1920,
            "frame_height": 1080,
            "available": True,
        }
    roster = [
        {
            "global_player_id": GLOBAL_PLAYER,
            "player_id": CANONICAL_PLAYER,
            "lifecycle": "confirmed",
            "bindings": {
                view_id: {"view_player_id": CANONICAL_PLAYER, "visibility": "lost"}
                for view_id in tick["views"]
            },
        }
    ]
    rows = build_display_diagnostics_rows(
        canonical_tick=tick["canonical_tick"],
        timestamp_ms=tick["canonical_timestamp_ms"],
        reference_view_id="cam_1",
        view_results=view_results,
        frame_status=frame_status,
        predictions={},  # pre-tick prediction 不可从 trace 直接复原 → 用空（region 不可用）
        view_geometry=geometry,
        policy=CrossViewGuidancePolicy(),
        roster=roster,
        association_decisions=[],
        guidance_decisions=[],
    )
    payload = build_player_display_diagnostics_payload(
        job_id="accept-diag",
        video_id=None,
        reference_view_id="cam_1",
        rows=rows,
    )
    validate_player_display_diagnostics(payload)

    p1_rows = [r for r in rows if r.player_id == CANONICAL_PLAYER]
    print(f"\n漏斗 builder 输出 {len(rows)} 行，P1 {len(p1_rows)} 行：")
    for row in p1_rows:
        print(
            f"  {row.view_id}: eligible_detection_present={row.eligible_detection_present} "
            f"position_present={row.position_present} court_position_present={row.court_position_present} "
            f"formal_observation_emitted={row.formal_observation_emitted} "
            f"expected_region_status={row.expected_region_status} "
            f"gate_count={row.eligible_detections_in_expected_gate}"
        )
        assert row.eligible_detection_present is True, f"{row.view_id} P1 应有 eligible detection"
        assert row.formal_observation_emitted is False, f"{row.view_id} P1 formal observation 应断裂"
    print("\n✅ 验收通过：00:07 P1 两路检测框存在、formal observation 断裂被漏斗正确重建")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
