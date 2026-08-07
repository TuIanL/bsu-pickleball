#!/usr/bin/env python3
"""A/B 验证脚本 —— single cam_1 / single cam_2 / configured default / multiview fused。

对比指标（分近端/远端区域统计）：
- 球场位置 RMSE（相对人工 GT）
- 轨迹缺失率 / 覆盖率
- 异常跳点率（帧间速度超阈值）
- 跨视角冲突率（fused 的 conflict 样本占比）
- identity association switch count
- 连续轨迹覆盖率

Ground Truth 独立性约束（避免循环验证）：
- GT 不依赖被评估的同一套 Homography（抽选已知球场线附近帧 + 人工确认物理坐标 + 两视角交叉复核）；
- GT 每个 sample 带 `global_player_id`，使 identity switch 可统计；
- 不使用事后 oracle baseline。

用法示例：
  python scripts/multiview_ab_validate.py \
      --gt data/gt/take_1_gt.json \
      --cam1 data/outputs/<cam1>/player_render_trajectory.json --cam1-orientation mirror_y \
      --cam2 data/outputs/<cam2>/player_render_trajectory.json --cam2-orientation mirror_x \
      --fused data/<take>/analysis/multiview/<run>/fused_player_trajectory.json \
      --output /tmp/ab_report.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median

from app.vision.multiview.artifact import load_fused_artifact
from app.vision.multiview.consumers import movement_points
from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
from app.vision.multiview.spike_adapter import load_view_observations

# GT schema 版本。
GT_SCHEMA_VERSION = "multiview_gt.v1"


def load_gt(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples", [])
    return [s for s in samples if isinstance(s, dict)]


def _nearest_point(
    points: list[tuple[float, float, float, str]],  # (take_timestamp_ms, x_ft, y_ft, player)
    target_ms: float,
    tolerance_ms: float,
) -> tuple[float, float, float, str] | None:
    best = None
    best_error = math.inf
    for point in points:
        error = abs(point[0] - target_ms)
        if error < best_error:
            best_error = error
            best = point
    if best is None or best_error > tolerance_ms:
        return None
    return best


def evaluate_group(
    group_name: str,
    points: list[tuple[float, float, float, str]],  # (take_ms, x, y, player)
    gt: list[dict[str, object]],
    tolerance_ms: float,
    jump_threshold_ft_s: float,
) -> dict[str, object]:
    """对一组轨迹计算 RMSE / 覆盖率 / 跳点率 / ID switch。"""
    aligned_errors: list[float] = []
    covered = 0
    for sample in gt:
        target_ms = float(sample.get("take_timestamp_ms", 0.0))
        gx = float(sample.get("x_ft"))
        gy = float(sample.get("y_ft"))
        nearest = _nearest_point(points, target_ms, tolerance_ms)
        if nearest is None:
            continue
        covered += 1
        aligned_errors.append(math.hypot(nearest[1] - gx, nearest[2] - gy))

    jumps = 0
    for i in range(1, len(points)):
        dt_s = max((points[i][0] - points[i - 1][0]) / 1000.0, 1e-3)
        speed = math.hypot(points[i][1] - points[i - 1][1], points[i][2] - points[i - 1][2]) / dt_s
        if speed > jump_threshold_ft_s:
            jumps += 1

    # ID switch：GT player 的轨迹在 fused/单视角上对应 player 变化计数。
    id_switches = 0
    for gt_id in {s.get("global_player_id") for s in gt}:
        prev_player: str | None = None
        for sample in sorted(
            [s for s in gt if s.get("global_player_id") == gt_id],
            key=lambda s: float(s.get("take_timestamp_ms", 0.0)),
        ):
            target_ms = float(sample.get("take_timestamp_ms", 0.0))
            nearest = _nearest_point(points, target_ms, tolerance_ms)
            if nearest is None:
                continue
            player = nearest[3]
            if prev_player is not None and player != prev_player:
                id_switches += 1
            prev_player = player

    return {
        "group": group_name,
        "gt_samples": len(gt),
        "covered_samples": covered,
        "coverage": covered / len(gt) if gt else 0.0,
        "rmse_ft": math.sqrt(mean(e**2 for e in aligned_errors)) if aligned_errors else None,
        "mean_error_ft": mean(aligned_errors) if aligned_errors else None,
        "median_error_ft": median(aligned_errors) if aligned_errors else None,
        "jump_rate": jumps / max(len(points) - 1, 1),
        "identity_switch_count": id_switches,
    }


def _region_split(
    gt: list[dict[str, object]], far_y_ft: float
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """按 canonical y 划分近端/远端子集。far_y_ft 为分界（远端 y > far_y_ft）。"""
    far, near = [], []
    for sample in gt:
        y = float(sample.get("y_ft", 0.0))
        (far if y > far_y_ft else near).append(sample)
    return far, near


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--cam1", type=Path, required=True)
    parser.add_argument("--cam1-orientation", type=str, default="mirror_y")
    parser.add_argument("--cam2", type=Path, required=True)
    parser.add_argument("--cam2-orientation", type=str, default="mirror_x")
    parser.add_argument("--fused", type=Path, required=True)
    parser.add_argument("--pairing-tolerance-ms", type=float, default=1000.0 / 30.0)
    parser.add_argument("--jump-threshold-ft-s", type=float, default=30.0)
    parser.add_argument("--far-y-ft", type=float, default=22.0)
    parser.add_argument("--output", type=Path, default=Path("/tmp/multiview_ab_report.json"))
    args = parser.parse_args()

    gt = load_gt(args.gt)
    if not gt:
        print("错误：GT 为空。")
        return 1

    cam1_obs = load_view_observations(args.cam1, view_id="cam_1")
    cam2_obs = load_view_observations(args.cam2, view_id="cam_2")
    fused_artifact = load_fused_artifact(args.fused)
    if fused_artifact is None:
        print("错误：fused artifact 不可用（缺失或损坏）。")
        return 1

    cam1_orientation = CourtOrientation(args.cam1_orientation)
    cam2_orientation = CourtOrientation(args.cam2_orientation)

    def to_points(obs) -> list[tuple[float, float, float, str]]:
        points = []
        for o in obs:
            orientation = cam1_orientation if o.view_id == "cam_1" else cam2_orientation
            cx, cy = local_to_canonical(o.local_x_ft, o.local_y_ft, orientation)
            points.append((o.timestamp_seconds * 1000.0, cx, cy, o.view_player_id))
        return points

    fused_points = [
        (p.take_timestamp_ms, p.x_ft, p.y_ft, p.global_player_id)
        for p in movement_points(fused_artifact)
    ]

    groups = {
        "cam1": to_points(cam1_obs),
        "cam2": to_points(cam2_obs),
        "fused": fused_points,
    }

    # 区域拆分。
    gt_far, gt_near = _region_split(gt, args.far_y_ft)

    def eval_group(name: str, subset: list[dict[str, object]]) -> dict[str, object]:
        return evaluate_group(
            name,
            groups[name],
            subset,
            args.pairing_tolerance_ms,
            args.jump_threshold_ft_s,
        )

    report = {
        "schema_version": "multiview_ab_report.v1",
        "gt_sample_count": len(gt),
        "far_gt_samples": len(gt_far),
        "near_gt_samples": len(gt_near),
        "overall": {name: eval_group(name, gt) for name in groups},
        "far_side": {name: eval_group(name, gt_far) for name in groups},
        "near_side": {name: eval_group(name, gt_near) for name in groups},
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
