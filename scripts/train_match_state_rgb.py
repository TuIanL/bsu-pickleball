#!/usr/bin/env python3
"""RGB-only 比赛状态 baseline：双摄共享 R3D-18 编码器的晚融合训练器。

训练和评估必须在远程 CUDA 节点执行。训练样本只使用 RGB 帧、时间清单和质量标签，
不把现有语义预测、比分或人工边界作为模型输入。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.match_state_rgb_sampling import experiment_id_for_manifest, sample_timestamp_ms
except ModuleNotFoundError:  # direct python scripts/train_match_state_rgb.py entry
    from match_state_rgb_sampling import experiment_id_for_manifest, sample_timestamp_ms

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, Dataset
from torchvision.io import read_image
from torchvision.models.video import R3D_18_Weights, r3d_18
from torchvision.transforms import functional as TF

CLASSES = ("rally_active", "non_play")
SCHEMA_VERSION = "match_state_rgb_only_run.v1"
CHECKPOINT_SCHEMA_VERSION = "match_state_model_checkpoint.v1"


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


def set_seed(seed: int, deterministic: bool) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True, warn_only=True)


def read_clips(rgb_manifest_path: Path) -> list[dict[str, Any]]:
    manifest = load_json(rgb_manifest_path)
    clip_path = rgb_manifest_path.parent / str(manifest["clips_file"])
    clips: list[dict[str, Any]] = []
    with clip_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                clips.append(json.loads(line))
    return clips




def frame_path(entry: dict[str, Any], timestamp_ms: float, fps: float) -> Path:
    duration_ms = float(entry.get("duration_ms", 0))
    timestamp_ms = max(0.0, min(duration_ms, timestamp_ms))
    frame_index = max(1, min(int(entry["frame_count"]), round(timestamp_ms / 1000.0 * fps) + 1))
    return Path(entry["frame_dir"]) / f"{frame_index:06d}.jpg"




class RGBClipDataset(Dataset[tuple[Tensor, Tensor]]):
    def __init__(
        self,
        clips: list[dict[str, Any]],
        assignment: dict[str, str],
        split: str,
        cache_entries: dict[str, dict[str, Any]],
        fps: float,
        model_frame_count: int,
        frame_count: int,
    ) -> None:
        self.items = [
            clip
            for clip in clips
            if assignment.get(str(clip.get("capture_take_id"))) == split
            and clip.get("center_quality") == "high_confidence"
            and clip.get("center_label") in CLASSES
        ]
        self.cache_entries = cache_entries
        self.fps = fps
        self.model_frame_count = model_frame_count
        self.frame_count = frame_count
        self.mean = (0.43216, 0.394666, 0.37645)
        self.std = (0.22803, 0.22145, 0.216989)
        if not self.items:
            raise ValueError(f"split={split} 没有 high_confidence RGB 样本")

    def __len__(self) -> int:
        return len(self.items)

    def _load_view(self, clip: dict[str, Any], view: dict[str, Any]) -> Tensor:
        entry = self.cache_entries.get(str(view["logical_media_uri"]))
        if entry is None or entry.get("status") != "complete":
            raise ValueError(f"缺少 RGB cache: {view.get('logical_media_uri')}")
        offsets = np.linspace(0, self.frame_count - 1, self.model_frame_count).round().astype(int)
        frames = []
        for offset in offsets:
            timestamp_ms = sample_timestamp_ms(clip, view, int(offset), self.fps)
            image = read_image(str(frame_path(entry, timestamp_ms, self.fps)))
            image = TF.convert_image_dtype(image, torch.float32)
            image = TF.normalize(image, self.mean, self.std)
            frames.append(image)
        return torch.stack(frames, dim=0)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        clip = self.items[index]
        views = sorted(clip["views"], key=lambda view: str(view["camera_role"]))
        if len(views) != 2:
            raise ValueError(f"RGB-only baseline 要求双摄，clip={clip.get('clip_id')}")
        tensor = torch.stack([self._load_view(clip, view) for view in views], dim=0)
        label = torch.tensor(CLASSES.index(str(clip["center_label"])), dtype=torch.long)
        return tensor, label


class RGBLateFusion(nn.Module):
    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        weights = R3D_18_Weights.DEFAULT if pretrained else None
        self.encoder = r3d_18(weights=weights)
        feature_dim = int(self.encoder.fc.in_features)
        self.encoder.fc = nn.Identity()
        self.head = nn.Linear(feature_dim, len(CLASSES))

    def set_encoder_trainable(self, trainable: bool) -> None:
        """在小数据集上先冻结预训练视觉骨干，避免首轮迅速过拟合。"""
        self.encoder.requires_grad_(trainable)
        if not trainable:
            self.encoder.eval()

    def forward(self, inputs: Tensor) -> Tensor:
        # inputs: [batch, camera=2, time, channels, height, width]
        logits = []
        for camera_index in range(inputs.shape[1]):
            view = inputs[:, camera_index].permute(0, 2, 1, 3, 4)
            logits.append(self.head(self.encoder(view)))
        return torch.stack(logits, dim=1).mean(dim=1)


def metrics(targets: list[int], predictions: list[int]) -> dict[str, Any]:
    matrix = [[0 for _ in CLASSES] for _ in CLASSES]
    for target, prediction in zip(targets, predictions, strict=True):
        matrix[target][prediction] += 1
    per_class: dict[str, dict[str, float]] = {}
    f1s = []
    for index, label in enumerate(CLASSES):
        tp = float(matrix[index][index])
        fp = float(sum(matrix[row][index] for row in range(len(CLASSES))) - matrix[index][index])
        fn = float(sum(matrix[index]) - matrix[index][index])
        precision = tp / max(tp + fp, 1.0)
        recall = tp / max(tp + fn, 1.0)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}
        f1s.append(f1)
    return {
        "sample_count": len(targets),
        "accuracy": sum(target == prediction for target, prediction in zip(targets, predictions, strict=True))
        / max(len(targets), 1),
        "macro_f1": sum(f1s) / len(f1s),
        "rally_active_precision": per_class["rally_active"]["precision"],
        "rally_active_recall": per_class["rally_active"]["recall"],
        "non_play_precision": per_class["non_play"]["precision"],
        "non_play_recall": per_class["non_play"]["recall"],
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def run_epoch(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor]],
    device: torch.device,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer | None,
    scaler: torch.amp.GradScaler | None,
    amp_enabled: bool,
    max_batches: int | None = None,
) -> tuple[float, dict[str, Any]]:
    training = optimizer is not None
    model.train(training)
    if isinstance(model, RGBLateFusion) and not any(
        parameter.requires_grad for parameter in model.encoder.parameters()
    ):
        model.encoder.eval()
    total_loss = 0.0
    total_count = 0
    targets: list[int] = []
    predictions: list[int] = []
    for batch_index, (inputs, labels) in enumerate(loader):
        if max_batches is not None and batch_index >= max_batches:
            break
        inputs = inputs.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        if training:
            optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=amp_enabled):
            output = model(inputs)
            loss = criterion(output, labels)
        if training:
            if scaler is not None and amp_enabled:
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
        total_loss += float(loss.detach()) * len(labels)
        total_count += len(labels)
        targets.extend(labels.detach().cpu().tolist())
        predictions.extend(output.detach().argmax(dim=1).cpu().tolist())
    return total_loss / max(total_count, 1), metrics(targets, predictions)


def evaluate(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor]],
    device: torch.device,
    criterion: nn.Module,
    amp_enabled: bool,
) -> tuple[float, dict[str, Any]]:
    with torch.no_grad():
        return run_epoch(model, loader, device, criterion, None, None, amp_enabled)


def load_history(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    history: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "epoch" in value and "validation" in value:
            history.append(value)
    return history


def build_loaders(args: argparse.Namespace, profile: dict[str, Any]) -> tuple[dict[str, DataLoader], dict[str, int]]:
    split = load_json(args.group_split)
    clips = read_clips(args.rgb_manifest)
    cache_manifest = load_json(args.rgb_cache_manifest)
    entries = cache_manifest.get("entries", {})
    temporal = profile["temporal_input"]
    loaders: dict[str, DataLoader] = {}
    counts: dict[str, int] = {}
    for split_name in ("train", "validation", "test"):
        dataset = RGBClipDataset(
            clips,
            split["assignment"],
            split_name,
            entries,
            float(temporal["sampling_fps"]),
            int(temporal["encoder_frame_count"]),
            int(temporal["frame_count"]),
        )
        counts[split_name] = len(dataset)
        loaders[split_name] = DataLoader(
            dataset,
            batch_size=int(profile["training"]["batch_size"]),
            shuffle=split_name == "train",
            num_workers=int(profile["training"]["num_workers"]),
            pin_memory=True,
            persistent_workers=int(profile["training"]["num_workers"]) > 0,
        )
    return loaders, counts


def create_package(
    args: argparse.Namespace, profile: dict[str, Any], history: list[dict[str, Any]], test_metrics: dict[str, Any]
) -> None:
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.training_profile, output / "training_profile.json")
    rgb_manifest = load_json(args.rgb_manifest)
    experiment_id = experiment_id_for_manifest(rgb_manifest)
    evaluation = {
        "schema_version": "match_state_evaluation_report.v1",
        "experiment_id": experiment_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "test": test_metrics,
        "history": history,
    }
    (output / "evaluation_report.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dataset_manifest = load_json(args.dataset_manifest)
    structured_profile = load_json(args.structured_profile)
    config_sha = sha256_file(args.training_profile)
    provenance = {
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "rgb_clip_manifest_sha256": sha256_file(args.rgb_manifest),
        "group_split_sha256": sha256_file(args.group_split),
        "structured_feature_profile_sha256": sha256_file(args.structured_profile),
        "code_revision": args.code_revision,
        "config_sha256": config_sha,
    }
    package_id = f"msp_rgb_only_{hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()[:16]}"
    artifact_checksums = {
        "model.pt": {"sha256": sha256_file(output / "model.pt"), "size_bytes": (output / "model.pt").stat().st_size},
        "training_profile.json": {
            "sha256": sha256_file(output / "training_profile.json"),
            "size_bytes": (output / "training_profile.json").stat().st_size,
        },
        "evaluation_report.json": {
            "sha256": sha256_file(output / "evaluation_report.json"),
            "size_bytes": (output / "evaluation_report.json").stat().st_size,
        },
    }
    package = {
        "schema_version": "match_state_model_package.v1",
        "package_id": package_id,
        "model_name": "match_state_rgb_only_r3d18_late_fusion",
        "model_version": experiment_id,
        "task": "match_state_temporal_segmentation",
        "classes": ["rally_active", "non_play", "unknown"],
        "input_contract": {
            "modalities": ["rgb"],
            "sampling_fps": profile["temporal_input"]["sampling_fps"],
            "clip_duration_ms": profile["temporal_input"]["clip_duration_ms"],
            "feature_schema": "match_state_rgb_frame_cache.v1",
        },
        "thresholds": profile["inference"],
        "provenance": provenance,
        "artifacts": {
            "weights": "model.pt",
            "training_config": "training_profile.json",
            "evaluation_report": "evaluation_report.json",
            "checksums": artifact_checksums,
        },
        "runtime": {"status": "ready", "device": args.device, "fallback": "preserve_existing_analysis"},
        "source_dataset_manifest_id": dataset_manifest.get("manifest_id"),
        "source_rgb_manifest_id": rgb_manifest.get("manifest_id"),
        "structured_feature_profile_schema": structured_profile.get("schema_version"),
    }
    (output / "model_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="远程训练 RGB-only 比赛状态 baseline")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-manifest", type=Path, required=True)
    parser.add_argument("--group-split", type=Path, required=True)
    parser.add_argument("--rgb-cache-manifest", type=Path, required=True)
    parser.add_argument("--structured-profile", type=Path, required=True)
    parser.add_argument("--training-profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--random-init", action="store_true", help="仅用于无网络 smoke；正式实验默认使用预训练权重")
    parser.add_argument("--code-revision", default="uncommitted-remote-upload")
    parser.add_argument("--evaluate-checkpoint", type=Path, help="仅加载已有 checkpoint，补做测试评估和模型打包")
    parser.add_argument("--history-jsonl", type=Path, help="收尾评估时复用已有的 epoch JSON 日志")
    args = parser.parse_args()
    profile = load_json(args.training_profile)
    experiment_id = experiment_id_for_manifest(load_json(args.rgb_manifest))
    if not args.smoke and args.random_init:
        raise SystemExit("正式 RGB-only 实验不能使用 random-init；请使用默认预训练权重")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA 不可用，拒绝在 CPU 上静默运行正式实验")
    set_seed(int(profile["training"]["seed"]), bool(profile["training"]["deterministic"]))
    loaders, counts = build_loaders(args, profile)
    model = RGBLateFusion(pretrained=not args.random_init).to(device)
    class_counts = Counter()
    for _, labels in loaders["train"]:
        class_counts.update(labels.tolist())
        if sum(class_counts.values()) > 2048:
            break
    total = sum(class_counts.values())
    weights = torch.tensor(
        [np.sqrt(total / max(class_counts[index], 1)) for index in range(len(CLASSES))],
        dtype=torch.float32,
        device=device,
    )
    weights = weights / weights.mean()
    criterion = nn.CrossEntropyLoss(weight=weights)
    amp_enabled = device.type == "cuda" and torch.cuda.is_bf16_supported()
    if args.smoke:
        loss, result = evaluate(model, loaders["validation"], device, criterion, amp_enabled)
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "smoke_passed",
                    "device": str(device),
                    "dataset_counts": counts,
                    "loss": loss,
                    "metrics": result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.evaluate_checkpoint:
        checkpoint = torch.load(args.evaluate_checkpoint, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        output = args.output_dir
        output.mkdir(parents=True, exist_ok=True)
        test_loss, test_metrics = evaluate(model, loaders["test"], device, criterion, amp_enabled)
        history = load_history(args.history_jsonl)
        best_epoch = int(checkpoint.get("best_epoch", 0))
        best_validation = checkpoint.get("validation_metrics", {})
        best_f1 = float(best_validation.get("macro_f1", -1.0))
        (output / "run.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "complete",
                    "experiment_id": experiment_id,
                    "completion_mode": "evaluate_existing_checkpoint",
                    "device": str(device),
                    "gpu_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
                    "dataset_counts": counts,
                    "best_epoch": best_epoch,
                    "best_validation_macro_f1": best_f1,
                    "test_loss": test_loss,
                    "test_metrics": test_metrics,
                    "checkpoint": str(args.evaluate_checkpoint),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        create_package(args, profile, history, test_metrics)
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "complete",
                    "completion_mode": "evaluate_existing_checkpoint",
                    "best_epoch": best_epoch,
                    "validation_macro_f1": best_f1,
                    "test": test_metrics,
                    "output": str(output),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    epochs = int(profile["training"]["epochs"])
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(profile["training"]["learning_rate"]),
        weight_decay=float(profile["training"]["weight_decay"]),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=False)
    history: list[dict[str, Any]] = []
    best_f1 = -1.0
    best_epoch = 0
    stale = 0
    started = time.time()
    freeze_epochs = int(profile["model"]["rgb_encoder"].get("freeze_backbone_initial_epochs", 0))
    for epoch in range(1, epochs + 1):
        model.set_encoder_trainable(epoch > freeze_epochs)
        train_loss, train_metrics = run_epoch(
            model, loaders["train"], device, criterion, optimizer, scaler, amp_enabled
        )
        val_loss, val_metrics = evaluate(model, loaders["validation"], device, criterion, amp_enabled)
        scheduler.step()
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": val_loss,
            "train": train_metrics,
            "validation": val_metrics,
            "learning_rate": optimizer.param_groups[0]["lr"],
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if val_metrics["macro_f1"] > best_f1:
            best_f1 = val_metrics["macro_f1"]
            best_epoch = epoch
            stale = 0
            torch.save(
                {
                    "schema_version": CHECKPOINT_SCHEMA_VERSION,
                    "model_name": "match_state_rgb_only_r3d18_late_fusion",
                    "classes": CLASSES,
                    "model_state_dict": model.state_dict(),
                    "best_epoch": best_epoch,
                    "validation_metrics": val_metrics,
                },
                output / "model.pt",
            )
        else:
            stale += 1
            if stale >= int(profile["training"]["early_stopping"]["patience"]):
                break
    checkpoint = torch.load(output / "model.pt", map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    test_loss, test_metrics = evaluate(model, loaders["test"], device, criterion, amp_enabled)
    (output / "run.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "experiment_id": experiment_id,
                "device": str(device),
                "gpu_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
                "dataset_counts": counts,
                "best_epoch": best_epoch,
                "best_validation_macro_f1": best_f1,
                "test_loss": test_loss,
                "test_metrics": test_metrics,
                "elapsed_seconds": round(time.time() - started, 3),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    create_package(args, profile, history, test_metrics)
    print(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "best_epoch": best_epoch,
                "validation_macro_f1": best_f1,
                "test": test_metrics,
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
