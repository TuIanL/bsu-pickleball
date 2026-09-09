#!/usr/bin/env python3
"""Build a reproducible three-input match-state ablation report."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def summarize(
    *,
    name: str,
    modalities: list[str],
    training_path: Path,
    timeline_path: Path,
    inference_path: Path | None,
    coverage_basis: str,
) -> dict[str, Any]:
    training = load(training_path)
    timeline = load(timeline_path)
    test = training.get("test", {})
    center = test.get("center", test)
    temporal = test.get("timeline")
    aggregate = timeline.get("aggregate", {})
    state = aggregate.get("state", {})
    rally = aggregate.get("rally", {})
    unknown_rate = float(state.get("unknown_rate", 0.0))
    precision = float(rally.get("precision", 0.0))
    recall = float(rally.get("recall", 0.0))
    runtime_seconds = None
    if inference_path and inference_path.exists():
        runtime_seconds = load(inference_path).get("runtime_seconds")
    return {
        "experiment": name,
        "modalities": modalities,
        "status": "completed",
        "failure_reason": None,
        "coverage": {
            "evidence_coverage_rate": 1.0 - unknown_rate,
            "unknown_rate": unknown_rate,
            "basis": coverage_basis,
        },
        "classification": {
            "center_sample_count": center.get("sample_count"),
            "center_accuracy": center.get("accuracy"),
            "center_macro_f1": center.get("macro_f1"),
            "center_rally_active_precision": center.get("rally_active_precision"),
            "center_rally_active_recall": center.get("rally_active_recall"),
            "dense_timeline_macro_f1": temporal.get("macro_f1") if isinstance(temporal, dict) else None,
        },
        "decoded_timeline": {
            "state_macro_f1_including_unknown": state.get("macro_f1"),
            "ground_truth_rally_count": rally.get("ground_truth_count"),
            "predicted_rally_count": rally.get("predicted_count"),
            "matched_rally_count_iou_gte_0_5": rally.get("matched_count"),
            "missed_rally_count": rally.get("missed_count"),
            "false_positive_rally_count": rally.get("false_positive_count"),
            "rally_precision": precision,
            "rally_recall": recall,
            "rally_f1": f1(precision, recall),
            "mean_iou": rally.get("mean_iou"),
            "boundary_start_mae_ms": rally.get("boundary_start_mae_ms"),
            "boundary_end_mae_ms": rally.get("boundary_end_mae_ms"),
            "boundary_tolerance_hits": rally.get("boundary_tolerance_hits"),
        },
        "runtime_seconds": runtime_seconds,
        "sources": {
            "training_evaluation": str(training_path),
            "timeline_evaluation": str(timeline_path),
            "inference_report": str(inference_path) if inference_path else None,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    rows = []
    for item in report["experiments"]:
        cls = item["classification"]
        timeline = item["decoded_timeline"]
        coverage = item["coverage"]
        rows.append(
            "| {name} | {coverage:.1%} | {unknown:.1%} | {macro:.4f} | {precision:.4f} | {recall:.4f} | {f1:.4f} | {iou:.4f} | {start:.1f} | {end:.1f} | {runtime} |".format(
                name=item["experiment"],
                coverage=coverage["evidence_coverage_rate"],
                unknown=coverage["unknown_rate"],
                macro=float(cls.get("center_macro_f1") or 0),
                precision=float(timeline.get("rally_precision") or 0),
                recall=float(timeline.get("rally_recall") or 0),
                f1=float(timeline.get("rally_f1") or 0),
                iou=float(timeline.get("mean_iou") or 0),
                start=float(timeline.get("boundary_start_mae_ms") or 0),
                end=float(timeline.get("boundary_end_mae_ms") or 0),
                runtime="-" if item.get("runtime_seconds") is None else f'{float(item["runtime_seconds"]):.1f}s',
            )
        )
    lines = [
        "# Match-state input ablation report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "| Input | Evidence coverage | Unknown | Center macro-F1 | Rally P | Rally R | Rally F1 | Mean IoU | Start MAE ms | End MAE ms | Inference |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        "## Interpretation constraints",
        "",
        *[f"- {note}" for note in report["comparison_constraints"]],
        "",
        "## Robustness validation",
        "",
        f"- Leave-one-take-out: {report['leave_one_take_out']['status']}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build three-way match-state input ablation report")
    for prefix in ("rgb", "structured", "fusion"):
        parser.add_argument(f"--{prefix}-training", type=Path, required=True)
        parser.add_argument(f"--{prefix}-timeline", type=Path, required=True)
        parser.add_argument(f"--{prefix}-inference", type=Path)
    parser.add_argument("--leave-one-take-out-report", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    experiments = [
        summarize(name="RGB-only", modalities=["rgb"], training_path=args.rgb_training, timeline_path=args.rgb_timeline, inference_path=args.rgb_inference, coverage_basis="nominal-sync full-video sliding windows"),
        summarize(name="pose+ball", modalities=["pose", "ball", "quality"], training_path=args.structured_training, timeline_path=args.structured_timeline, inference_path=args.structured_inference, coverage_basis="strict authoritative canonical feature ranges"),
        summarize(name="RGB+pose+ball", modalities=["rgb", "pose", "ball", "quality"], training_path=args.fusion_training, timeline_path=args.fusion_timeline, inference_path=args.fusion_inference, coverage_basis="strict authoritative canonical feature ranges"),
    ]
    loo = {"status": "pending", "reason": "7-fold leave-one-take-out has not been executed"}
    if args.leave_one_take_out_report:
        loo = {"status": "completed", "source": str(args.leave_one_take_out_report), "results": load(args.leave_one_take_out_report)}
    report = {
        "schema_version": "match_state_input_ablation.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluation_protocol": {
            "primary_split": "5_train_1_validation_1_test_by_capture_take",
            "decoder_selection": "validation-only grid search",
            "segment_match": "one-to-one greedy matching at IoU >= 0.5",
            "test_take_used_for_threshold_selection": False,
        },
        "experiments": experiments,
        "comparison_constraints": [
            "All three experiments use the same take-level 5/1/1 split and label revision.",
            "RGB-only v1 uses the original nominal-sync full-video clip manifest; pose+ball and fusion use strict authoritative canonical-sync ranges.",
            "Consequently, decoded full-timeline recall and unknown rate are not a like-for-like architecture comparison until canonical RGB v2 retraining is complete.",
            "Center-window classification is the fairest current model comparison; full-timeline metrics additionally measure evidence coverage and decoder behavior.",
        ],
        "leave_one_take_out": loo,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": "written", "json": str(args.output_json), "markdown": str(args.output_markdown)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
