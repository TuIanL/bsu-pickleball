#!/usr/bin/env python3
"""对模型生成的候选时间线做回合级和窗口级评估。"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .match_state_timeline import evaluate_timeline
except ImportError:  # 允许直接执行脚本
    from match_state_timeline import evaluate_timeline


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def ground_truth_for_take(take: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"segment_id": item.get("segment_id"), "start_ms": float(item["start_ms"]), "end_ms": float(item["end_ms"])}
        for item in take.get("labels", [])
        if item.get("start_ms") is not None
        and item.get("end_ms") is not None
        and float(item["end_ms"]) > float(item["start_ms"])
    ]


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    state_classes = ("rally_active", "non_play", "unknown")
    matrix = [[0 for _ in state_classes] for _ in state_classes]
    rally_keys = ("ground_truth_count", "predicted_count", "matched_count", "missed_count", "false_positive_count")
    rally = {key: sum(int(item["rally"].get(key, 0)) for item in results) for key in rally_keys}
    match_count = rally["matched_count"]
    iou_sum = sum(float(item["rally"].get("mean_iou", 0.0)) * len(item["rally"].get("matches", [])) for item in results)
    start_sum = sum(
        float(item["rally"].get("boundary_start_mae_ms", 0.0)) * len(item["rally"].get("matches", []))
        for item in results
    )
    end_sum = sum(
        float(item["rally"].get("boundary_end_mae_ms", 0.0)) * len(item["rally"].get("matches", [])) for item in results
    )
    tolerance_hits: dict[str, int] = {}
    for item in results:
        for key, value in item["rally"].get("boundary_tolerance_hits", {}).items():
            tolerance_hits[key] = tolerance_hits.get(key, 0) + int(value)
        current = item["state"].get("confusion_matrix", [])
        for actual in range(min(3, len(current))):
            for predicted in range(min(3, len(current[actual]))):
                matrix[actual][predicted] += int(current[actual][predicted])
    per_class: dict[str, dict[str, float]] = {}
    for index, label in enumerate(state_classes):
        tp = matrix[index][index]
        fp = sum(matrix[actual][index] for actual in range(3)) - tp
        fn = sum(matrix[index]) - tp
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / max(precision + recall, 1e-9),
        }
    state_count = sum(sum(row) for row in matrix)
    rally.update(
        {
            "precision": rally["matched_count"] / max(rally["predicted_count"], 1),
            "recall": rally["matched_count"] / max(rally["ground_truth_count"], 1),
            "mean_iou": iou_sum / max(match_count, 1),
            "boundary_start_mae_ms": start_sum / max(match_count, 1),
            "boundary_end_mae_ms": end_sum / max(match_count, 1),
            "boundary_tolerance_hits": tolerance_hits,
        }
    )
    return {
        "state": {
            "sample_count": state_count,
            "macro_f1": sum(item["f1"] for item in per_class.values()) / 3,
            "unknown_rate": (matrix[0][2] + matrix[1][2] + matrix[2][2]) / max(state_count, 1),
            "per_class": per_class,
            "confusion_matrix": matrix,
        },
        "rally": rally,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="评估模型候选时间线的分类和边界指标")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--timeline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset = load_json(args.dataset_manifest)
    per_take = []
    missing = []
    for take in dataset.get("takes", []):
        timeline_path = args.timeline_dir / f"{take['source_session_id']}.timeline.json"
        if not timeline_path.is_file():
            missing.append(take["source_session_id"])
            continue
        timeline = load_json(timeline_path)
        windows = timeline.get("windows", [])
        predicted = timeline.get("candidate_segments", timeline.get("segments", []))
        evaluation = evaluate_timeline(windows, predicted, ground_truth_for_take(take))
        per_take.append(
            {"capture_take_id": take["capture_take_id"], "source_session_id": take["source_session_id"], **evaluation}
        )
    aggregate = aggregate_results(per_take) if per_take else None
    report = {
        "schema_version": "match_state_timeline_evaluation.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "take_count": len(per_take),
        "missing_takes": missing,
        "status": "passed" if not missing else "incomplete",
        "aggregate": aggregate,
        "per_take": per_take,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
