#!/usr/bin/env python3
"""只用 validation take 选择时间线解码阈值，并重写版本化候选 artifact。"""

from __future__ import annotations

import argparse
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from match_state_timeline import decode_state_timeline, evaluate_timeline


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / max(precision + recall, 1e-9)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证集时间线解码参数搜索")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--validation-session", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    validation_path = args.input_dir / f"{args.validation_session}.timeline.json"
    validation = load(validation_path)
    grid = []
    for confidence, hysteresis, duration in itertools.product(
        (0.50, 0.55, 0.60, 0.65, 0.70, 0.75), (0.0, 0.05, 0.10, 0.15), (500, 750, 1000)
    ):
        parameters = {
            "minimum_confidence": confidence,
            "minimum_coverage": 0.75,
            "minimum_duration_ms": duration,
            "hysteresis": hysteresis,
            "unknown_on_insufficient_evidence": True,
        }
        decoded = decode_state_timeline(validation["windows"], **parameters)
        evaluation = evaluate_timeline(decoded["windows"], decoded["segments"], validation["ground_truth_segments"])
        rally = evaluation["rally"]
        rally_f1 = f1(float(rally["precision"]), float(rally["recall"]))
        score = (rally_f1, float(rally["mean_iou"]), -float(rally["boundary_start_mae_ms"] + rally["boundary_end_mae_ms"]), -float(evaluation["state"]["unknown_rate"]))
        grid.append({"parameters": parameters, "score": list(score), "rally_f1": rally_f1, "evaluation": evaluation})
    best = max(grid, key=lambda item: tuple(item["score"]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for path in sorted(args.input_dir.glob("*.timeline.json")):
        artifact = load(path)
        decoded = decode_state_timeline(artifact["windows"], **best["parameters"])
        evaluation = evaluate_timeline(decoded["windows"], decoded["segments"], artifact["ground_truth_segments"])
        artifact["decoder"] = best["parameters"]
        artifact["decoder_tuning"] = {"selection_split": "validation", "validation_session": args.validation_session, "objective": "rally_f1@iou>=0.5_then_mean_iou_then_boundary_mae", "selected_at": datetime.now(UTC).isoformat()}
        artifact["windows"] = decoded["windows"]
        artifact["candidate_segments"] = decoded["segments"]
        artifact["evaluation"] = evaluation
        (args.output_dir / path.name).write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        rally = evaluation["rally"]
        summaries.append({"source_session_id": artifact["source_session_id"], "candidate_count": len(decoded["segments"]), "unknown_rate": decoded["unknown_rate"], "rally_f1": f1(rally["precision"], rally["recall"]), "evaluation": evaluation})
    report = {"schema_version": "match_state_decoder_tuning.v1", "generated_at": datetime.now(UTC).isoformat(), "selection_split": "validation", "validation_session": args.validation_session, "grid_size": len(grid), "best": best, "per_take": summaries}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "grid_size": len(grid), "best": best, "take_count": len(summaries)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
