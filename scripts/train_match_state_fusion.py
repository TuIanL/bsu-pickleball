#!/usr/bin/env python3
"""训练 canonical RGB + 骨架/球路的双摄晚融合时序模型。"""

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
from torch.utils.data import DataLoader, Dataset
from torchvision.io import read_image
from torchvision.models.video import r3d_18
from torchvision.transforms import functional as TF

from match_state_structured_model import (
    CHECKPOINT_SCHEMA_VERSION,
    CLASSES,
    ResidualTCNBlock,
    StructuredSequenceDataset,
    StructuredTemporalModel,
    class_weights,
    classification_metrics,
    load_json,
    read_sequences,
    set_seed,
    sha256_file,
)
from train_match_state_rgb import frame_path, read_clips, sample_timestamp_ms
from train_match_state_structured import load_tensor_cache

RUN_SCHEMA = "match_state_fusion_run.v1"
MODEL_NAME = "match_state_rgb_structured_late_fusion_tcn"
EXPERIMENT_ID = "rgb_structured_fusion_v1"


class FusionDataset(Dataset):
    def __init__(
        self,
        sequences: list[dict[str, Any]],
        split: str,
        tensors: dict[str, dict[str, np.ndarray]],
        rgb_clips: list[dict[str, Any]],
        rgb_cache: dict[str, dict[str, Any]],
        fps: float,
        frame_count: int,
        encoder_frames: int,
        split_assignment: dict[str, str] | None = None,
    ) -> None:
        self.structured = StructuredSequenceDataset(sequences, split, tensors, split_assignment)
        self.rgb_index = {
            (str(item["capture_take_id"]), round(float(item["center_ms"]), 3)): item for item in rgb_clips
        }
        self.rgb_cache = rgb_cache
        self.fps = fps
        self.frame_count = frame_count
        self.encoder_frames = encoder_frames
        self.mean = (0.43216, 0.394666, 0.37645)
        self.std = (0.22803, 0.22145, 0.216989)
        missing = [
            item["sequence_id"]
            for item in self.structured.items
            if (str(item["capture_take_id"]), round(float(item["center_timestamp_ms"]), 3)) not in self.rgb_index
        ]
        if missing:
            raise ValueError(f"结构化窗口缺少 canonical RGB 配对: {missing[:3]}，共 {len(missing)} 条")

    def __len__(self) -> int:
        return len(self.structured)

    def _rgb(self, item: dict[str, Any]) -> Tensor:
        clip = self.rgb_index[(str(item["capture_take_id"]), round(float(item["center_timestamp_ms"]), 3))]
        offsets = np.linspace(0, self.frame_count - 1, self.encoder_frames).round().astype(int)
        views = []
        for view in sorted(clip["views"], key=lambda value: str(value["camera_role"])):
            entry = self.rgb_cache[str(view["logical_media_uri"])]
            frames = []
            for offset in offsets:
                timestamp = sample_timestamp_ms(clip, view, int(offset), self.fps)
                image = TF.convert_image_dtype(read_image(str(frame_path(entry, timestamp, self.fps))), torch.float32)
                frames.append(TF.normalize(image, self.mean, self.std))
            views.append(torch.stack(frames))
        if len(views) != 2:
            raise ValueError(f"融合输入要求双摄: {item['sequence_id']}")
        return torch.stack(views)

    def __getitem__(self, index: int):
        item = self.structured.items[index]
        return (self._rgb(item), *self.structured[index])


class FusionTemporalModel(nn.Module):
    def __init__(self, structured: StructuredTemporalModel, rgb_checkpoint: Path | None, dropout: float = 0.2) -> None:
        super().__init__()
        self.rgb_encoder = r3d_18(weights=None)
        rgb_dim = int(self.rgb_encoder.fc.in_features)
        self.rgb_encoder.fc = nn.Identity()
        if rgb_checkpoint is not None:
            checkpoint = torch.load(rgb_checkpoint, map_location="cpu", weights_only=False)
            encoder_state = {
                key.removeprefix("encoder."): value
                for key, value in checkpoint["model_state_dict"].items()
                if key.startswith("encoder.")
            }
            self.rgb_encoder.load_state_dict(encoder_state, strict=True)
        self.structured = structured
        self.rgb_projection = nn.Sequential(nn.Linear(rgb_dim * 2, 256), nn.LayerNorm(256), nn.GELU(), nn.Dropout(dropout))
        self.fusion = nn.Sequential(nn.Linear(512, 256), nn.LayerNorm(256), nn.GELU())
        self.temporal = nn.Sequential(ResidualTCNBlock(256, 1, dropout), ResidualTCNBlock(256, 2, dropout))
        self.classifier = nn.Conv1d(256, len(CLASSES), 1)
        self.set_rgb_stage(False)

    def set_rgb_stage(self, train_layer4: bool) -> None:
        self.rgb_encoder.requires_grad_(False)
        self.rgb_encoder.layer4.requires_grad_(train_layer4)

    def forward(self, rgb: Tensor, players: Tensor, player_mask: Tensor, ball: Tensor, quality: Tensor) -> Tensor:
        rgb_views = []
        for camera in range(rgb.shape[1]):
            rgb_views.append(self.rgb_encoder(rgb[:, camera].permute(0, 2, 1, 3, 4)))
        view_features = torch.stack(rgb_views, dim=1)
        rgb_feature = self.rgb_projection(torch.cat([view_features.mean(dim=1), view_features.max(dim=1).values], dim=-1))
        structured_feature = self.structured.temporal_features(players, player_mask, ball, quality)
        expanded_rgb = rgb_feature.unsqueeze(1).expand(-1, structured_feature.shape[1], -1)
        fused = self.fusion(torch.cat([structured_feature, expanded_rgb], dim=-1))
        return self.classifier(self.temporal(fused.transpose(1, 2))).transpose(1, 2)


def run_epoch(model, loader, device, criterion, optimizer, amp_enabled, accumulation, max_batches=None):
    training = optimizer is not None
    model.train(training)
    if not any(parameter.requires_grad for parameter in model.rgb_encoder.parameters()):
        model.rgb_encoder.eval()
    elif not any(parameter.requires_grad for parameter in model.rgb_encoder.stem.parameters()):
        model.rgb_encoder.eval()
        model.rgb_encoder.layer4.train(training)
    if training:
        optimizer.zero_grad(set_to_none=True)
    total_loss = 0.0
    total_count = 0
    timeline_y, timeline_p, center_y, center_p = [], [], [], []
    batches = 0
    for batch_index, batch in enumerate(loader):
        if max_batches is not None and batch_index >= max_batches:
            break
        rgb, players, player_mask, ball, quality, labels, loss_mask, center = [x.to(device, non_blocking=True) for x in batch]
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=amp_enabled):
            logits = model(rgb, players, player_mask, ball, quality)
            raw = criterion(logits.reshape(-1, len(CLASSES)), labels.reshape(-1)).reshape_as(loss_mask)
            valid_count = loss_mask.sum().clamp_min(1.0)
            loss = (raw * loss_mask).sum() / valid_count
        if training:
            (loss / accumulation).backward()
            if (batch_index + 1) % accumulation == 0:
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
        prediction = logits.detach().argmax(-1)
        valid = loss_mask.bool()
        timeline_y.extend(labels[valid].detach().cpu().tolist())
        timeline_p.extend(prediction[valid].detach().cpu().tolist())
        center_valid = center[:, 1].bool()
        center_y.extend(center[center_valid, 0].detach().cpu().tolist())
        center_p.extend(prediction[center_valid, logits.shape[1] // 2].detach().cpu().tolist())
        count = int(valid.sum())
        total_loss += float(loss.detach()) * count
        total_count += count
        batches += 1
    if training and batches % accumulation:
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
    return total_loss / max(total_count, 1), {"center": classification_metrics(center_y, center_p), "timeline": classification_metrics(timeline_y, timeline_p)}


def package(args, profile, sequence_manifest, tensor_manifest, history, test_loss, test_metrics):
    output = args.output_dir
    shutil.copy2(args.training_profile, output / "training_profile.json")
    report = {"schema_version": "match_state_evaluation_report.v1", "experiment_id": EXPERIMENT_ID, "generated_at": datetime.now(UTC).isoformat(), "test_loss": test_loss, "test": test_metrics, "history": history}
    (output / "evaluation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "rgb_clip_manifest_sha256": sha256_file(args.rgb_manifest),
        "group_split_sha256": sha256_file(args.group_split),
        "structured_feature_profile_sha256": sha256_file(args.structured_profile),
        "structured_sequence_manifest_sha256": sha256_file(args.sequence_manifest),
        "structured_tensor_manifest_sha256": sha256_file(args.tensor_manifest),
        "rgb_checkpoint_sha256": sha256_file(args.rgb_checkpoint),
        "structured_checkpoint_sha256": sha256_file(args.structured_checkpoint),
        "code_revision": args.code_revision,
        "config_sha256": sha256_file(args.training_profile),
    }
    checksums = {name: {"sha256": sha256_file(output / name), "size_bytes": (output / name).stat().st_size} for name in ("model.pt", "training_profile.json", "evaluation_report.json")}
    rgb_manifest = load_json(args.rgb_manifest)
    result = {
        "schema_version": "match_state_model_package.v1",
        "package_id": f"msp_fusion_{hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()[:16]}",
        "model_name": MODEL_NAME,
        "model_version": EXPERIMENT_ID,
        "task": "match_state_temporal_segmentation",
        "classes": ["rally_active", "non_play", "unknown"],
        "input_contract": {"modalities": ["rgb", "pose", "ball", "quality"], "sampling_fps": profile["temporal_input"]["sampling_fps"], "clip_duration_ms": profile["temporal_input"]["clip_duration_ms"], "feature_schema": sequence_manifest["input_contract"]["source_record_schema"]},
        "thresholds": profile["inference"], "provenance": provenance,
        "artifacts": {"weights": "model.pt", "training_config": "training_profile.json", "evaluation_report": "evaluation_report.json", "checksums": checksums},
        "runtime": {"status": "ready", "device": args.device, "fallback": "preserve_existing_analysis"},
        "source_dataset_manifest_id": load_json(args.dataset_manifest)["manifest_id"], "source_rgb_manifest_id": rgb_manifest["manifest_id"],
        "structured_feature_profile_schema": load_json(args.structured_profile)["schema_version"],
    }
    (output / "model_package.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="训练 RGB + 结构化视觉融合模型")
    for name in ("dataset-manifest", "rgb-manifest", "rgb-cache-manifest", "group-split", "structured-profile", "training-profile", "sequence-manifest", "tensor-manifest", "rgb-checkpoint", "structured-checkpoint", "output-dir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--code-revision", default="uncommitted-remote-upload")
    args = parser.parse_args()
    profile = load_json(args.training_profile)
    seq_manifest, sequences = read_sequences(args.sequence_manifest)
    tensors, tensor_manifest = load_tensor_cache(args.tensor_manifest, seq_manifest)
    rgb_clips = read_clips(args.rgb_manifest)
    rgb_cache = load_json(args.rgb_cache_manifest)["entries"]
    split_assignment = load_json(args.group_split).get("assignment")
    if not isinstance(split_assignment, dict):
        raise ValueError("group split 缺少 assignment")
    temporal = profile["temporal_input"]
    loaders, counts = {}, {}
    for split in ("train", "validation", "test"):
        dataset = FusionDataset(
            sequences,
            split,
            tensors,
            rgb_clips,
            rgb_cache,
            float(temporal["sampling_fps"]),
            int(temporal["frame_count"]),
            int(temporal["encoder_frame_count"]),
            split_assignment,
        )
        counts[split] = len(dataset)
        loaders[split] = DataLoader(dataset, batch_size=int(profile["training"]["batch_size"]), shuffle=split == "train", num_workers=int(profile["training"]["num_workers"]), pin_memory=True, persistent_workers=True)
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA 不可用，拒绝静默使用 CPU")
    set_seed(int(profile["training"]["seed"]), bool(profile["training"]["deterministic"]))
    structured_config = profile["model"]["structured_encoder"]
    temporal_config = profile["model"]["temporal_head"]
    structured = StructuredTemporalModel(int(structured_config["hidden_dim"]), int(temporal_config["hidden_dim"]), int(temporal_config["layers"]), float(temporal_config["dropout"]))
    structured_state = torch.load(args.structured_checkpoint, map_location="cpu", weights_only=False)
    structured.load_state_dict(structured_state["model_state_dict"])
    model = FusionTemporalModel(structured, args.rgb_checkpoint, float(temporal_config["dropout"])).to(device)
    criterion = nn.CrossEntropyLoss(
        weight=class_weights(sequences, "train", device, split_assignment), reduction="none"
    )
    amp = device.type == "cuda" and torch.cuda.is_bf16_supported()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=float(profile["training"]["learning_rate"]), weight_decay=float(profile["training"]["weight_decay"]))
    if args.smoke:
        train_loss, train_metrics = run_epoch(model, loaders["train"], device, criterion, optimizer, amp, 1, 1)
        validation_loss, validation_metrics = run_epoch(model, loaders["validation"], device, criterion, None, amp, 1, 1)
        print(json.dumps({"status": "smoke_passed", "counts": counts, "train_loss": train_loss, "train": train_metrics, "validation_loss": validation_loss, "validation": validation_metrics}, ensure_ascii=False, indent=2))
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    epochs = int(profile["training"]["epochs"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    accumulation = int(profile["training"]["gradient_accumulation_steps"])
    best_f1, best_epoch, stale, history = -1.0, 0, 0, []
    started = time.time()
    for epoch in range(1, epochs + 1):
        if epoch == 4:
            model.set_rgb_stage(True)
            optimizer.add_param_group({"params": list(model.rgb_encoder.layer4.parameters()), "lr": float(profile["training"]["learning_rate"]) * 0.1})
        train_loss, train_metrics = run_epoch(model, loaders["train"], device, criterion, optimizer, amp, accumulation)
        val_loss, val_metrics = run_epoch(model, loaders["validation"], device, criterion, None, amp, 1)
        scheduler.step()
        row = {"epoch": epoch, "train_loss": train_loss, "validation_loss": val_loss, "train": train_metrics, "validation": val_metrics, "learning_rates": [group["lr"] for group in optimizer.param_groups]}
        history.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
        score = float(val_metrics["center"]["macro_f1"])
        if score > best_f1:
            best_f1, best_epoch, stale = score, epoch, 0
            torch.save({"schema_version": CHECKPOINT_SCHEMA_VERSION, "model_name": MODEL_NAME, "classes": CLASSES, "model_state_dict": model.state_dict(), "best_epoch": best_epoch, "validation_metrics": val_metrics}, args.output_dir / "model.pt")
        else:
            stale += 1
            if stale >= int(profile["training"]["early_stopping"]["patience"]): break
    checkpoint = torch.load(args.output_dir / "model.pt", map_location=device, weights_only=False); model.load_state_dict(checkpoint["model_state_dict"])
    test_loss, test_metrics = run_epoch(model, loaders["test"], device, criterion, None, amp, 1)
    run = {"schema_version": RUN_SCHEMA, "status": "complete", "experiment_id": EXPERIMENT_ID, "device": str(device), "gpu_name": torch.cuda.get_device_name(device), "dataset_counts": counts, "best_epoch": best_epoch, "best_validation_macro_f1": best_f1, "test_loss": test_loss, "test_metrics": test_metrics, "elapsed_seconds": round(time.time()-started, 3)}
    (args.output_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    package(args, profile, seq_manifest, tensor_manifest, history, test_loss, test_metrics)
    print(json.dumps({"status": "complete", "best_epoch": best_epoch, "validation_macro_f1": best_f1, "test": test_metrics, "output": str(args.output_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
