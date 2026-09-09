#!/usr/bin/env python3
"""从 structured/fusion 时序模型生成概率、unknown 和候选回合时间线。"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from match_state_structured_model import CLASSES, StructuredSequenceDataset, StructuredTemporalModel, load_json, read_sequences
from match_state_timeline import decode_state_timeline, evaluate_timeline
from train_match_state_fusion import FusionDataset, FusionTemporalModel
from train_match_state_rgb import read_clips
from train_match_state_structured import load_tensor_cache
from verify_match_state_model_package import validate_package


def ground_truth(take: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in take.get("labels", []):
        start, end = item.get("start_ms"), item.get("end_ms")
        if start is not None and end is not None and float(end) > float(start):
            result.append({"segment_id": item.get("segment_id"), "start_ms": float(start), "end_ms": float(end)})
    return sorted(result, key=lambda item: item["start_ms"])


def full_timeline_windows(take: dict[str, Any], aggregate: dict[float, list[float]], fps: float) -> list[dict[str, Any]]:
    step = 1000.0 / fps
    count = int(math.floor(float(take["duration_ms"]) / step)) + 1
    result = []
    for index in range(count):
        timestamp = round(index * step, 3)
        values = aggregate.get(timestamp)
        if values:
            samples = values[-1]
            probabilities = {CLASSES[i]: values[i] / samples for i in range(len(CLASSES))}
            coverage, insufficient = 1.0, False
        else:
            probabilities = {label: 0.0 for label in CLASSES}
            coverage, insufficient = 0.0, True
        result.append({"center_ms": timestamp, "state_probabilities": probabilities, "coverage": coverage, "insufficient_evidence": insufficient, "evidence_window_count": int(values[-1]) if values else 0})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="结构化/融合模型全量时间线推理")
    parser.add_argument("--mode", choices=("structured", "fusion"), required=True)
    for name in ("dataset-manifest", "sequence-manifest", "tensor-manifest", "training-profile", "package-dir", "output-dir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--rgb-manifest", type=Path)
    parser.add_argument("--rgb-cache-manifest", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--num-workers", type=int, default=8)
    args = parser.parse_args()
    package_check = validate_package(args.package_dir, strict=True)
    if package_check["status"] != "passed":
        raise SystemExit(json.dumps(package_check, ensure_ascii=False, indent=2))
    package = load_json(args.package_dir / "model_package.json")
    profile = load_json(args.training_profile)
    sequence_manifest, sequences = read_sequences(args.sequence_manifest)
    tensors, tensor_manifest = load_tensor_cache(args.tensor_manifest, sequence_manifest)
    device = torch.device(args.device)
    structured_config = profile["model"]["structured_encoder"]
    temporal_config = profile["model"]["temporal_head"]
    structured = StructuredTemporalModel(int(structured_config["hidden_dim"]), int(temporal_config["hidden_dim"]), int(temporal_config["layers"]), float(temporal_config["dropout"]))
    if args.mode == "fusion":
        if args.rgb_manifest is None or args.rgb_cache_manifest is None:
            raise SystemExit("fusion 模式需要 --rgb-manifest 和 --rgb-cache-manifest")
        model = FusionTemporalModel(structured, None, float(temporal_config["dropout"]))
    else:
        model = structured
    checkpoint = torch.load(args.package_dir / package["artifacts"]["weights"], map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device).eval()
    dataset_manifest = load_json(args.dataset_manifest)
    take_map = {str(item["capture_take_id"]): item for item in dataset_manifest["takes"]}
    aggregate: dict[str, dict[float, list[float]]] = defaultdict(dict)
    started = time.time()
    for split in ("train", "validation", "test"):
        if args.mode == "fusion":
            dataset = FusionDataset(sequences, split, tensors, read_clips(args.rgb_manifest), load_json(args.rgb_cache_manifest)["entries"], float(profile["temporal_input"]["sampling_fps"]), int(profile["temporal_input"]["frame_count"]), int(profile["temporal_input"]["encoder_frame_count"]))
            items = dataset.structured.items
        else:
            dataset = StructuredSequenceDataset(sequences, split, tensors)
            items = dataset.items
        loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=True, persistent_workers=args.num_workers > 0)
        cursor = 0
        with torch.inference_mode():
            for batch in loader:
                if args.mode == "fusion":
                    rgb, players, player_mask, ball, quality = [value.to(device, non_blocking=True) for value in batch[:5]]
                    logits = model(rgb, players, player_mask, ball, quality)
                else:
                    players, player_mask, ball, quality = [value.to(device, non_blocking=True) for value in batch[:4]]
                    logits = model(players, player_mask, ball, quality)
                probabilities = torch.softmax(logits, dim=-1).float().cpu()
                for batch_index in range(probabilities.shape[0]):
                    item = items[cursor + batch_index]
                    take_values = aggregate[str(item["capture_take_id"])]
                    for offset, row in enumerate(item["label"]["timeline_labels"]):
                        timestamp = round(float(row["canonical_timestamp_ms"]), 3)
                        if timestamp not in take_values:
                            take_values[timestamp] = [0.0, 0.0, 0.0]
                        take_values[timestamp][0] += float(probabilities[batch_index, offset, 0])
                        take_values[timestamp][1] += float(probabilities[batch_index, offset, 1])
                        take_values[timestamp][2] += 1.0
                cursor += probabilities.shape[0]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    fps = float(profile["temporal_input"]["sampling_fps"])
    for take_id, take in take_map.items():
        raw_windows = full_timeline_windows(take, aggregate.get(take_id, {}), fps)
        decoded = decode_state_timeline(raw_windows, **package["thresholds"])
        target = ground_truth(take)
        evaluation = evaluate_timeline(decoded["windows"], decoded["segments"], target)
        artifact = {
            "schema_version": "match_state_candidate_timeline.v1", "capture_take_id": take_id,
            "source_session_id": take["source_session_id"], "duration_ms": take["duration_ms"],
            "model": {"package_id": package["package_id"], "model_name": package["model_name"], "model_version": package["model_version"], "modalities": package["input_contract"]["modalities"]},
            "source_provenance": {
                "model_package": package.get("provenance", {}),
                "dataset_manifest_id": sequence_manifest.get("identity", {}).get("dataset_manifest_id"),
                "dataset_manifest_sha256": sequence_manifest.get("identity", {}).get("dataset_manifest_sha256"),
                "group_split_id": sequence_manifest.get("identity", {}).get("group_split_id"),
                "group_split_sha256": sequence_manifest.get("identity", {}).get("group_split_sha256"),
                "canonical_feature_manifest_id": sequence_manifest.get("identity", {}).get("canonical_feature_manifest_id"),
                "canonical_feature_manifest_sha256": sequence_manifest.get("identity", {}).get("canonical_feature_manifest_sha256"),
                "structured_sequence_manifest_id": sequence_manifest.get("manifest_id"),
                "structured_sequence_manifest_sha256": package.get("provenance", {}).get("structured_sequence_manifest_sha256"),
                "structured_tensor_schema_version": tensor_manifest.get("schema_version"),
                "structured_tensor_manifest_sha256": package.get("provenance", {}).get("structured_tensor_manifest_sha256"),
                "strict_authoritative_only": sequence_manifest.get("identity", {}).get("strict_authoritative_only"),
                "timeline_generator_revision": "match-state-candidate-timeline-v1-20260902",
            },
            "decoder": package["thresholds"], "windows": decoded["windows"], "candidate_segments": decoded["segments"],
            "ground_truth_segments": target, "evaluation": evaluation, "review_status": "unreviewed",
        }
        (args.output_dir / f"{take['source_session_id']}.timeline.json").write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        results.append({"capture_take_id": take_id, "source_session_id": take["source_session_id"], "split": next((x["split"] for x in sequences if x["capture_take_id"] == take_id), None), "unknown_rate": decoded["unknown_rate"], "candidate_count": len(decoded["segments"]), "evaluation": evaluation})
    report = {"schema_version": "match_state_candidate_timeline_report.v1", "generated_at": datetime.now(UTC).isoformat(), "package_id": package["package_id"], "model_version": package["model_version"], "mode": args.mode, "take_count": len(results), "runtime_seconds": round(time.time()-started, 3), "per_take": results}
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
