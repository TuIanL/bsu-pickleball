#!/usr/bin/env python3
"""训练 authoritative-only 骨架/球路比赛状态时序 baseline。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from match_state_structured_model import (
    CHECKPOINT_SCHEMA_VERSION,
    CLASSES,
    StructuredSequenceDataset,
    StructuredTemporalModel,
    class_weights,
    classification_metrics,
    load_json,
    read_sequences,
    set_seed,
    sha256_file,
)

RUN_SCHEMA = "match_state_structured_run.v1"
MODEL_NAME = "match_state_structured_deepset_tcn"
EXPERIMENT_ID = "structured_pose_ball_v1"


def load_tensor_cache(path: Path, sequence_manifest: dict[str, Any]) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, Any]]:
    manifest = load_json(path)
    if manifest.get("sequence_manifest_id") != sequence_manifest.get("manifest_id"):
        raise ValueError("tensor cache 与 sequence manifest ID 不一致")
    tensors = {}
    for source_name, entry in manifest.get("entries", {}).items():
        tensor_path = path.parent / str(entry["tensor_file"])
        expected = manifest.get("artifact_checksums", {}).get(tensor_path.name, {})
        if tensor_path.stat().st_size != expected.get("size_bytes") or sha256_file(tensor_path) != expected.get("sha256"):
            raise ValueError(f"tensor cache 哈希或大小不一致: {tensor_path}")
        with np.load(tensor_path) as values:
            tensors[source_name] = {key: values[key].copy() for key in values.files}
    return tensors, manifest


def build_loaders(
    sequences: list[dict[str, Any]],
    tensors: dict[str, dict[str, np.ndarray]],
    profile: dict[str, Any],
    split_assignment: dict[str, str] | None = None,
) -> tuple[dict[str, DataLoader], dict[str, int]]:
    loaders = {}
    counts = {}
    for split in ("train", "validation", "test"):
        dataset = StructuredSequenceDataset(sequences, split, tensors, split_assignment)
        counts[split] = len(dataset)
        loaders[split] = DataLoader(
            dataset,
            batch_size=int(profile["training"]["batch_size"]),
            shuffle=split == "train",
            num_workers=min(4, int(profile["training"]["num_workers"])),
            pin_memory=True,
            persistent_workers=int(profile["training"]["num_workers"]) > 0,
        )
    return loaders, counts


def _drop_one_view(players: Tensor, player_mask: Tensor, ball: Tensor, quality: Tensor, probability: float) -> None:
    if probability <= 0:
        return
    selected = torch.rand(players.shape[0], device=players.device) < probability
    camera = torch.randint(0, 2, (players.shape[0],), device=players.device)
    for batch_index in torch.nonzero(selected, as_tuple=False).flatten().tolist():
        camera_index = int(camera[batch_index])
        players[batch_index, :, camera_index] = 0
        player_mask[batch_index, :, camera_index] = 0
        ball[batch_index, :, camera_index] = 0
        quality[batch_index, :, camera_index] = 0


def run_epoch(
    model: StructuredTemporalModel,
    loader: DataLoader,
    device: torch.device,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer | None,
    amp_enabled: bool,
    accumulation_steps: int,
    view_dropout: float,
    max_batches: int | None = None,
) -> tuple[float, dict[str, Any]]:
    training = optimizer is not None
    model.train(training)
    if training:
        optimizer.zero_grad(set_to_none=True)
    total_loss = 0.0
    total_weight = 0
    timeline_targets: list[int] = []
    timeline_predictions: list[int] = []
    center_targets: list[int] = []
    center_predictions: list[int] = []
    processed_batches = 0
    for batch_index, batch in enumerate(loader):
        if max_batches is not None and batch_index >= max_batches:
            break
        players, player_mask, ball, quality, labels, loss_mask, center = [value.to(device, non_blocking=True) for value in batch]
        if training:
            _drop_one_view(players, player_mask, ball, quality, view_dropout)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=amp_enabled):
            logits = model(players, player_mask, ball, quality)
            raw_loss = criterion(logits.reshape(-1, len(CLASSES)), labels.reshape(-1)).reshape_as(loss_mask)
            weight = loss_mask.sum().clamp_min(1.0)
            loss = (raw_loss * loss_mask).sum() / weight
            scaled_loss = loss / accumulation_steps
        if training:
            scaled_loss.backward()
            if (batch_index + 1) % accumulation_steps == 0:
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
        prediction = logits.detach().argmax(dim=-1)
        valid = loss_mask.bool()
        timeline_targets.extend(labels[valid].detach().cpu().tolist())
        timeline_predictions.extend(prediction[valid].detach().cpu().tolist())
        center_valid = center[:, 1].bool()
        center_targets.extend(center[center_valid, 0].detach().cpu().tolist())
        center_predictions.extend(prediction[center_valid, logits.shape[1] // 2].detach().cpu().tolist())
        count = int(valid.sum())
        total_loss += float(loss.detach()) * count
        total_weight += count
        processed_batches += 1
    if training and processed_batches % accumulation_steps:
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
    return total_loss / max(total_weight, 1), {
        "center": classification_metrics(center_targets, center_predictions),
        "timeline": classification_metrics(timeline_targets, timeline_predictions),
    }


def evaluate(model: StructuredTemporalModel, loader: DataLoader, device: torch.device, criterion: nn.Module, amp: bool) -> tuple[float, dict[str, Any]]:
    with torch.inference_mode():
        return run_epoch(model, loader, device, criterion, None, amp, 1, 0.0)


def artifact_checksums(output: Path) -> dict[str, dict[str, Any]]:
    return {
        name: {"sha256": sha256_file(output / name), "size_bytes": (output / name).stat().st_size}
        for name in ("model.pt", "training_profile.json", "evaluation_report.json")
    }


def write_package(
    args: argparse.Namespace,
    profile: dict[str, Any],
    sequence_manifest: dict[str, Any],
    tensor_manifest: dict[str, Any],
    history: list[dict[str, Any]],
    test_loss: float,
    test_metrics: dict[str, Any],
) -> None:
    output = args.output_dir
    shutil.copy2(args.training_profile, output / "training_profile.json")
    evaluation = {
        "schema_version": "match_state_evaluation_report.v1",
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "test_loss": test_loss,
        "test": test_metrics,
        "history": history,
    }
    (output / "evaluation_report.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rgb_manifest = load_json(args.rgb_manifest)
    structured_profile = load_json(args.structured_profile)
    provenance = {
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "rgb_clip_manifest_sha256": sha256_file(args.rgb_manifest),
        "group_split_sha256": sha256_file(args.group_split),
        "structured_feature_profile_sha256": sha256_file(args.structured_profile),
        "structured_sequence_manifest_sha256": sha256_file(args.sequence_manifest),
        "structured_tensor_manifest_sha256": sha256_file(args.tensor_manifest),
        "code_revision": args.code_revision,
        "config_sha256": sha256_file(args.training_profile),
    }
    package_id = f"msp_structured_{hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()[:16]}"
    package = {
        "schema_version": "match_state_model_package.v1",
        "package_id": package_id,
        "model_name": MODEL_NAME,
        "model_version": EXPERIMENT_ID,
        "task": "match_state_temporal_segmentation",
        "classes": ["rally_active", "non_play", "unknown"],
        "input_contract": {
            "modalities": ["pose", "ball", "quality"],
            "sampling_fps": profile["temporal_input"]["sampling_fps"],
            "clip_duration_ms": profile["temporal_input"]["clip_duration_ms"],
            "feature_schema": sequence_manifest["input_contract"]["source_record_schema"],
        },
        "thresholds": profile["inference"],
        "provenance": provenance,
        "artifacts": {
            "weights": "model.pt",
            "training_config": "training_profile.json",
            "evaluation_report": "evaluation_report.json",
            "checksums": artifact_checksums(output),
        },
        "runtime": {"status": "ready", "device": args.device, "fallback": "preserve_existing_analysis"},
        "source_dataset_manifest_id": load_json(args.dataset_manifest).get("manifest_id"),
        "source_rgb_manifest_id": rgb_manifest.get("manifest_id"),
        "structured_feature_profile_schema": structured_profile.get("schema_version"),
    }
    (output / "model_package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="远程训练骨架/球路比赛状态 baseline")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-manifest", type=Path, required=True, help="共享实验切分与 provenance 使用的 RGB manifest 索引")
    parser.add_argument("--group-split", type=Path, required=True)
    parser.add_argument("--structured-profile", type=Path, required=True)
    parser.add_argument("--training-profile", type=Path, required=True)
    parser.add_argument("--sequence-manifest", type=Path, required=True)
    parser.add_argument("--tensor-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--code-revision", default="uncommitted-remote-upload")
    args = parser.parse_args()
    profile = load_json(args.training_profile)
    sequence_manifest, sequences = read_sequences(args.sequence_manifest)
    tensors, tensor_manifest = load_tensor_cache(args.tensor_manifest, sequence_manifest)
    split_assignment = load_json(args.group_split).get("assignment")
    if not isinstance(split_assignment, dict):
        raise ValueError("group split 缺少 assignment")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA 不可用，拒绝在 CPU 上静默运行正式实验")
    set_seed(int(profile["training"]["seed"]), bool(profile["training"]["deterministic"]))
    loaders, counts = build_loaders(sequences, tensors, profile, split_assignment)
    structured = profile["model"]["structured_encoder"]
    temporal = profile["model"]["temporal_head"]
    model = StructuredTemporalModel(
        hidden_dim=int(structured["hidden_dim"]),
        temporal_dim=int(temporal["hidden_dim"]),
        layers=int(temporal["layers"]),
        dropout=float(temporal["dropout"]),
    ).to(device)
    criterion = nn.CrossEntropyLoss(
        weight=class_weights(sequences, "train", device, split_assignment), reduction="none"
    )
    amp_enabled = device.type == "cuda" and torch.cuda.is_bf16_supported()
    if args.smoke:
        smoke_optimizer = torch.optim.AdamW(model.parameters(), lr=float(profile["training"]["learning_rate"]))
        train_loss, train_metrics = run_epoch(
            model, loaders["train"], device, criterion, smoke_optimizer, amp_enabled, 1, 0.15, max_batches=2
        )
        validation_loss, validation_metrics = run_epoch(
            model, loaders["validation"], device, criterion, None, amp_enabled, 1, 0.0, max_batches=2
        )
        print(
            json.dumps(
                {
                    "schema_version": RUN_SCHEMA,
                    "status": "smoke_passed",
                    "dataset_counts": counts,
                    "train_loss": train_loss,
                    "train_metrics": train_metrics,
                    "validation_loss": validation_loss,
                    "validation_metrics": validation_metrics,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(profile["training"]["learning_rate"]), weight_decay=float(profile["training"]["weight_decay"]))
    epochs = int(profile["training"]["epochs"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    accumulation = int(profile["training"]["gradient_accumulation_steps"])
    history = []
    best_f1 = -1.0
    best_epoch = 0
    stale = 0
    started = time.time()
    for epoch in range(1, epochs + 1):
        train_loss, train_metrics = run_epoch(model, loaders["train"], device, criterion, optimizer, amp_enabled, accumulation, 0.15)
        validation_loss, validation_metrics = evaluate(model, loaders["validation"], device, criterion, amp_enabled)
        scheduler.step()
        row = {"epoch": epoch, "train_loss": train_loss, "validation_loss": validation_loss, "train": train_metrics, "validation": validation_metrics, "learning_rate": optimizer.param_groups[0]["lr"]}
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        score = float(validation_metrics["center"]["macro_f1"])
        if score > best_f1:
            best_f1, best_epoch, stale = score, epoch, 0
            torch.save({"schema_version": CHECKPOINT_SCHEMA_VERSION, "model_name": MODEL_NAME, "classes": CLASSES, "model_state_dict": model.state_dict(), "best_epoch": best_epoch, "validation_metrics": validation_metrics, "feature_contract": {"players": [2, 4, 6], "ball": [2, 8], "quality": [2, 8]}}, args.output_dir / "model.pt")
        else:
            stale += 1
            if stale >= int(profile["training"]["early_stopping"]["patience"]):
                break
    checkpoint = torch.load(args.output_dir / "model.pt", map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    test_loss, test_metrics = evaluate(model, loaders["test"], device, criterion, amp_enabled)
    elapsed = round(time.time() - started, 3)
    run = {"schema_version": RUN_SCHEMA, "status": "complete", "experiment_id": EXPERIMENT_ID, "device": str(device), "gpu_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None, "dataset_counts": counts, "best_epoch": best_epoch, "best_validation_macro_f1": best_f1, "test_loss": test_loss, "test_metrics": test_metrics, "elapsed_seconds": elapsed}
    (args.output_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_package(args, profile, sequence_manifest, tensor_manifest, history, test_loss, test_metrics)
    print(json.dumps({"status": "complete", "best_epoch": best_epoch, "validation_macro_f1": best_f1, "test": test_metrics, "output": str(args.output_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
