#!/usr/bin/env python3
"""可断点续跑的 7 折 CaptureTake 级 RGB+结构化融合 LOO 训练。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_complete(output: Path, split_sha256: str) -> bool:
    run_path = output / "run.json"
    package_path = output / "model_package.json"
    if not run_path.exists() or not package_path.exists():
        return False
    run = load_json(run_path)
    package = load_json(package_path)
    return (
        run.get("status") == "complete"
        and package.get("provenance", {}).get("group_split_sha256") == split_sha256
        and (output / "model.pt").exists()
    )


def execute(command: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{datetime.now(UTC).isoformat()}] {' '.join(command)}\n")
        log.flush()
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"命令失败（exit={result.returncode}），详见 {log_path}")


def command(script: Path, common: dict[str, Path], output: Path, extra: dict[str, Path] | None = None) -> list[str]:
    values = {**common, **(extra or {}), "output-dir": output}
    result = [sys.executable, str(script)]
    for name, value in values.items():
        result.extend((f"--{name}", str(value)))
    result.extend(("--device", "cuda:0", "--code-revision", "loo-v1"))
    return result


def summarize(root: Path, folds: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for fold in folds:
        run_path = root / fold["fold_id"] / "fusion" / "run.json"
        if not run_path.exists():
            continue
        run = load_json(run_path)
        if run.get("status") != "complete":
            continue
        center = run["test_metrics"]["center"]
        timeline = run["test_metrics"]["timeline"]
        rows.append(
            {
                **fold,
                "sample_count": center["sample_count"],
                "center_macro_f1": center["macro_f1"],
                "center_accuracy": center["accuracy"],
                "rally_active_precision": center["rally_active_precision"],
                "rally_active_recall": center["rally_active_recall"],
                "timeline_macro_f1": timeline["macro_f1"],
                "best_epoch": run["best_epoch"],
                "elapsed_seconds": run["elapsed_seconds"],
            }
        )
    metric_names = (
        "center_macro_f1",
        "center_accuracy",
        "rally_active_precision",
        "rally_active_recall",
        "timeline_macro_f1",
    )
    macro = {
        name: sum(float(row[name]) for row in rows) / len(rows) if rows else None for name in metric_names
    }
    weighted = {}
    total = sum(int(row["sample_count"]) for row in rows)
    for name in metric_names:
        weighted[name] = (
            sum(float(row[name]) * int(row["sample_count"]) for row in rows) / total if total else None
        )
    return {
        "schema_version": "match_state_leave_one_take_out_report.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "architecture": "rgb_structured_fusion_v1",
        "protocol": {
            "unit": "capture_take",
            "fold_count": len(folds),
            "validation_policy": "next_take_in_sorted_cycle",
            "leakage_control": "fresh RGB, structured, and fusion weights in every fold",
        },
        "completed_folds": len(rows),
        "folds": rows,
        "macro_average": macro,
        "sample_weighted_average": weighted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="执行最终融合架构 7 折 leave-one-take-out")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-manifest", type=Path, required=True)
    parser.add_argument("--rgb-cache-manifest", type=Path, required=True)
    parser.add_argument("--base-group-split", type=Path, required=True)
    parser.add_argument("--structured-profile", type=Path, required=True)
    parser.add_argument("--rgb-training-profile", type=Path, required=True)
    parser.add_argument("--structured-training-profile", type=Path, required=True)
    parser.add_argument("--fusion-training-profile", type=Path, required=True)
    parser.add_argument("--sequence-manifest", type=Path, required=True)
    parser.add_argument("--tensor-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    base_split = load_json(args.base_group_split)
    take_ids = sorted(str(value) for value in base_split.get("assignment", {}))
    if len(take_ids) != 7:
        raise ValueError(f"LOO 要求恰好 7 个 CaptureTake，实际 {len(take_ids)}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    folds = []
    for index, test_take in enumerate(take_ids):
        validation_take = take_ids[(index + 1) % len(take_ids)]
        fold_id = f"fold-{index + 1:02d}-{test_take}"
        assignment = {
            take_id: "test" if take_id == test_take else "validation" if take_id == validation_take else "train"
            for take_id in take_ids
        }
        split_path = args.output_dir / fold_id / "group-split.json"
        split = {
            "schema_version": "match_state_group_split.v1",
            "split_id": f"loo_{index + 1:02d}_{test_take}",
            "strategy": "leave_one_capture_take_out",
            "source_group_split_sha256": sha256_file(args.base_group_split),
            "test_capture_take_id": test_take,
            "validation_capture_take_id": validation_take,
            "assignment": assignment,
        }
        if not split_path.exists() or load_json(split_path) != split:
            write_json(split_path, split)
        folds.append(
            {
                "fold_id": fold_id,
                "test_capture_take_id": test_take,
                "validation_capture_take_id": validation_take,
            }
        )

    if not args.summarize_only:
        scripts = Path(__file__).resolve().parent
        for fold in folds:
            fold_root = args.output_dir / fold["fold_id"]
            split_path = fold_root / "group-split.json"
            split_sha256 = sha256_file(split_path)
            common = {
                "dataset-manifest": args.dataset_manifest,
                "rgb-manifest": args.rgb_manifest,
                "group-split": split_path,
                "structured-profile": args.structured_profile,
            }
            rgb_output = fold_root / "rgb"
            if not run_complete(rgb_output, split_sha256):
                execute(
                    command(
                        scripts / "train_match_state_rgb.py",
                        common,
                        rgb_output,
                        {
                            "rgb-cache-manifest": args.rgb_cache_manifest,
                            "training-profile": args.rgb_training_profile,
                        },
                    ),
                    fold_root / "rgb.log",
                )
            structured_output = fold_root / "structured"
            if not run_complete(structured_output, split_sha256):
                execute(
                    command(
                        scripts / "train_match_state_structured.py",
                        common,
                        structured_output,
                        {
                            "training-profile": args.structured_training_profile,
                            "sequence-manifest": args.sequence_manifest,
                            "tensor-manifest": args.tensor_manifest,
                        },
                    ),
                    fold_root / "structured.log",
                )
            fusion_output = fold_root / "fusion"
            if not run_complete(fusion_output, split_sha256):
                execute(
                    command(
                        scripts / "train_match_state_fusion.py",
                        common,
                        fusion_output,
                        {
                            "rgb-cache-manifest": args.rgb_cache_manifest,
                            "training-profile": args.fusion_training_profile,
                            "sequence-manifest": args.sequence_manifest,
                            "tensor-manifest": args.tensor_manifest,
                            "rgb-checkpoint": rgb_output / "model.pt",
                            "structured-checkpoint": structured_output / "model.pt",
                        },
                    ),
                    fold_root / "fusion.log",
                )
            write_json(args.output_dir / "report.json", summarize(args.output_dir, folds))

    report = summarize(args.output_dir, folds)
    write_json(args.output_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["completed_folds"] == 7 or not args.summarize_only else 2


if __name__ == "__main__":
    raise SystemExit(main())
