#!/usr/bin/env python3
"""P0 Spike 验证脚本 —— 用真实双摄 render trajectory 验证核心假设。

三个假设：
  (a) 同一球员两路 canonical 化后空间接近（canonical 配对距离小）；
  (b) 跨视角关联稳定（需按 player 拆分做时间窗 best-match，Phase 4 关联器落地后闭环）；
  (c) 近端机位确实改善远端轨迹（需 Ground Truth；脚本给出可跑代理指标，
      完整 A/B 验证在 Phase 9 用人工标注完成）。

复用 CanonicalTimelineBuilder 完成 sync 配对（max_pairing_error_ms 门控）。

用法示例：
  python scripts/multiview_spike_validate.py \
      --reference-artifact data/outputs/<cam1>/player_render_trajectory.json \
      --secondary-artifact data/outputs/<cam2>/player_render_trajectory.json \
      --reference-orientation mirror_y \
      --secondary-orientation mirror_x \
      --sync-calibration data/recordings/<take>/timeline/sync_calibration.json \
      --output /tmp/spike_report.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median

from app.vision.multiview.canonical_timeline import CanonicalTimelineBuilder
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.spike_adapter import load_view_observations
from app.vision.multiview.sync import load_sync_calibration


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-artifact", type=Path, required=True)
    parser.add_argument("--secondary-artifact", type=Path, required=True)
    parser.add_argument("--reference-orientation", type=str, required=True)
    parser.add_argument("--secondary-orientation", type=str, required=True)
    parser.add_argument("--reference-camera-id", type=str, default="cam_1")
    parser.add_argument("--secondary-camera-id", type=str, default="cam_2")
    parser.add_argument("--sync-calibration", type=Path, default=None)
    parser.add_argument("--max-pairing-error-ms", type=float, default=1000.0 / 30.0)
    parser.add_argument("--output", type=Path, default=Path("/tmp/multiview_spike_report.json"))
    args = parser.parse_args()

    ref_orientation = CourtOrientation(args.reference_orientation)
    sec_orientation = CourtOrientation(args.secondary_orientation)
    orientations = {args.reference_camera_id: ref_orientation, args.secondary_camera_id: sec_orientation}

    ref_obs = load_view_observations(args.reference_artifact, view_id=args.reference_camera_id)
    sec_obs = load_view_observations(args.secondary_artifact, view_id=args.secondary_camera_id)
    if not ref_obs or not sec_obs:
        print("错误：某一路没有 observed 样本。")
        return 1

    sync = load_sync_calibration(args.sync_calibration) if args.sync_calibration else None
    builder = CanonicalTimelineBuilder(max_pairing_error_ms=args.max_pairing_error_ms)
    ticks = builder.build(
        reference_view_id=args.reference_camera_id,
        reference_observations=ref_obs,
        secondary_view_id=args.secondary_camera_id,
        secondary_observations=sec_obs,
        sync=sync,
        secondary_camera_id=args.secondary_camera_id,
        orientations=orientations,
    )

    paired_distances: list[float] = []
    dual_count = 0
    sec_unavailable_count = 0
    for tick in ticks:
        ref_obs_c = tick.observations[args.reference_camera_id]
        sec_obs_c = tick.observations[args.secondary_camera_id]
        if (
            ref_obs_c.canonical_x_ft is not None
            and sec_obs_c.canonical_x_ft is not None
            and sec_obs_c.view_status == "available"
        ):
            dual_count += 1
            paired_distances.append(
                math.hypot(
                    ref_obs_c.canonical_x_ft - sec_obs_c.canonical_x_ft,
                    ref_obs_c.canonical_y_ft - sec_obs_c.canonical_y_ft,
                )
            )
        else:
            sec_unavailable_count += 1

    # (c) 代理指标：两路观测密度 / 投影置信度（近端机位应更高）。
    ref_proj_conf = [o.projection_confidence for o in ref_obs if o.projection_confidence is not None]
    sec_proj_conf = [o.projection_confidence for o in sec_obs if o.projection_confidence is not None]

    report = {
        "schema_version": "multiview_spike_report.v1",
        "reference_artifact": str(args.reference_artifact),
        "secondary_artifact": str(args.secondary_artifact),
        "reference_orientation": args.reference_orientation,
        "secondary_orientation": args.secondary_orientation,
        "sync_available": sync is not None,
        "max_pairing_error_ms": args.max_pairing_error_ms,
        "reference_observed_count": len(ref_obs),
        "secondary_observed_count": len(sec_obs),
        "canonical_ticks": len(ticks),
        "hypothesis_a": {
            "dual_observed_ticks": dual_count,
            "paired_count": len(paired_distances),
            "median_canonical_distance_ft": median(paired_distances) if paired_distances else None,
            "p90_canonical_distance_ft": (
                sorted(paired_distances)[int(len(paired_distances) * 0.9) - 1] if paired_distances else None
            ),
            "note": "同一球员两路 canonical 化后空间接近（需同球员对齐后距离小；"
                    "当前为整路配对分布，按 player 拆分后应更小）",
        },
        "hypothesis_c_proxy": {
            "reference_mean_projection_confidence": (
                sum(ref_proj_conf) / len(ref_proj_conf) if ref_proj_conf else None
            ),
            "secondary_mean_projection_confidence": (
                sum(sec_proj_conf) / len(sec_proj_conf) if sec_proj_conf else None
            ),
            "note": "近端机位投影置信度应更高；完整 A/B 需 Phase 9 人工 GT",
        },
        "hypothesis_b": {
            "note": "跨视角关联稳定性需按 player 分组后做时间窗 best-match 计数；"
                    "Phase 4 CrossViewPlayerAssociator 落地后闭环",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
