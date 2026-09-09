#!/usr/bin/env python3
"""用 RGB-only 模型生成可直接进入边界复核工作台的候选时间线。"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

try:
    from .infer_match_state_rgb_timeline import load_json, run_take
    from .train_match_state_rgb import RGBLateFusion
    from .verify_match_state_model_package import validate_package
except ImportError:  # 允许远程节点直接执行 scripts/*.py
    from infer_match_state_rgb_timeline import load_json, run_take
    from train_match_state_rgb import RGBLateFusion
    from verify_match_state_model_package import validate_package


GENERATOR_REVISION = "match-state-rgb-only-candidate-v1-20260906"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact(
    result: dict[str, Any],
    *,
    package: dict[str, Any],
    dataset: dict[str, Any],
    dataset_manifest_path: Path,
    rgb_cache_manifest: dict[str, Any],
    rgb_cache_manifest_path: Path,
) -> dict[str, Any]:
    provenance = package.get("provenance", {})
    input_contract = package.get("input_contract", {})
    return {
        "schema_version": "match_state_candidate_timeline.v1",
        "capture_take_id": result["capture_take_id"],
        "source_session_id": result["source_session_id"],
        "duration_ms": result["duration_ms"],
        "model": {
            "package_id": package["package_id"],
            "model_name": package["model_name"],
            "model_version": package["model_version"],
            "modalities": input_contract.get("modalities", ["rgb"]),
        },
        "source_provenance": {
            "model_package": provenance,
            "dataset_manifest_id": dataset.get("manifest_id"),
            "dataset_manifest_sha256": sha256_file(dataset_manifest_path),
            "rgb_clip_manifest_sha256": provenance.get("rgb_clip_manifest_sha256"),
            "rgb_cache_manifest_id": rgb_cache_manifest.get("manifest_id"),
            "rgb_cache_manifest_sha256": sha256_file(rgb_cache_manifest_path),
            "group_split_sha256": provenance.get("group_split_sha256"),
            "timeline_generator_revision": GENERATOR_REVISION,
        },
        "decoder": package["thresholds"],
        "model_input": result["model_input"],
        "windows": result["windows"],
        "candidate_segments": result["segments"],
        "ground_truth_segments": result["ground_truth_segments"],
        "evaluation": result["evaluation"],
        "review_status": "unreviewed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RGB-only 候选时间线推理")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-cache-manifest", type=Path, required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument("--stride-ms", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--only-session")
    parser.add_argument("--max-windows", type=int)
    args = parser.parse_args()
    if args.stride_ms <= 0 or args.batch_size <= 0 or (args.max_windows is not None and args.max_windows <= 0):
        raise SystemExit("stride-ms、batch-size 和 max-windows 必须为正数")

    package_check = validate_package(args.package_dir, strict=True)
    if package_check["status"] != "passed":
        raise SystemExit(json.dumps(package_check, ensure_ascii=False, indent=2))
    package = load_json(args.package_dir / "model_package.json")
    profile = load_json(args.package_dir / str(package["artifacts"]["training_config"]))
    checkpoint_path = args.package_dir / str(package["artifacts"]["weights"])
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        if not args.allow_cpu:
            raise SystemExit("CUDA 不可用；正式候选时间线应在远程 GPU 执行，如确需 CPU 请显式传 --allow-cpu")
        device = torch.device("cpu")

    model = RGBLateFusion(pretrained=False).to(device)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    dataset = load_json(args.dataset_manifest)
    rgb_cache_manifest = load_json(args.rgb_cache_manifest)
    entries = rgb_cache_manifest.get("entries", {})
    if not isinstance(entries, dict):
        raise SystemExit("RGB cache manifest entries 必须是对象")
    temporal = profile["temporal_input"]
    results: list[dict[str, Any]] = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    for take in dataset.get("takes", []):
        if args.only_session and take.get("source_session_id") != args.only_session:
            continue
        result = run_take(
            model=model,
            take=take,
            cache_entries=entries,
            thresholds=package["thresholds"],
            fps=float(temporal["sampling_fps"]),
            clip_duration_ms=int(temporal["clip_duration_ms"]),
            frame_count=int(temporal["frame_count"]),
            model_frame_count=int(temporal["encoder_frame_count"]),
            stride_ms=args.stride_ms,
            batch_size=args.batch_size,
            device=device,
            max_windows=args.max_windows,
        )
        artifact = build_artifact(
            result,
            package=package,
            dataset=dataset,
            dataset_manifest_path=args.dataset_manifest,
            rgb_cache_manifest=rgb_cache_manifest,
            rgb_cache_manifest_path=args.rgb_cache_manifest,
        )
        output_path = args.output_dir / f"{take['source_session_id']}.timeline.json"
        output_path.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        results.append(
            {
                "capture_take_id": artifact["capture_take_id"],
                "source_session_id": artifact["source_session_id"],
                "candidate_count": len(artifact["candidate_segments"]),
                "evaluation": artifact["evaluation"],
            }
        )
        print(json.dumps(results[-1], ensure_ascii=False))

    report = {
        "schema_version": "match_state_candidate_timeline_report.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "package_id": package["package_id"],
        "model_version": package["model_version"],
        "mode": "rgb_only",
        "generator_revision": GENERATOR_REVISION,
        "device": str(device),
        "take_count": len(results),
        "runtime_seconds": round(time.time() - started, 3),
        "per_take": results,
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
