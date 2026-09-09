#!/usr/bin/env python3
"""结构化比赛状态模型共享的数据编码、模型与指标实现。"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import Dataset

CLASSES = ("rally_active", "non_play")
PLAYER_FEATURES = 6
BALL_FEATURES = 8
QUALITY_FEATURES = 8
CAMERAS = ("cam_1", "cam_2")
FRAME_COUNT = 48
VECTOR_SCHEMA_VERSION = "match_state_structured_tensor.v1"
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


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _pair(value: Any) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) < 2:
        return 0.0, 0.0
    return _finite(value[0]), _finite(value[1])


def _clip(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def vectorize_view(view: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """编码单机位；未检测到球只通过 observed mask 表达，不解释为场上无球。"""

    players = np.zeros((4, PLAYER_FEATURES), dtype=np.float32)
    player_mask = np.zeros(4, dtype=np.float32)
    pose = view.get("features", {}).get("pose", {})
    people = [item for item in pose.get("players", []) if isinstance(item, dict)]
    # 槽位只用于批处理；模型使用共享 player encoder + set pooling，不依赖此排序保持身份。
    people.sort(key=lambda item: (_pair(item.get("position_xy_norm"))[1], _pair(item.get("position_xy_norm"))[0]))
    for index, person in enumerate(people[:4]):
        px, py = _pair(person.get("position_xy_norm"))
        vx, vy = _pair(person.get("velocity_xy_norm_per_s"))
        players[index] = np.asarray(
            [
                _clip(px, 1.5),
                _clip(py, 1.5),
                _clip(vx / 3.0, 1.0),
                _clip(vy / 3.0, 1.0),
                _clip(_finite(person.get("body_activity_intensity")) / 3.0, 1.0),
                _clip(_finite(person.get("visibility_ratio")), 1.0),
            ],
            dtype=np.float32,
        )
        player_mask[index] = 0.0 if person.get("missing", False) else 1.0

    ball_record = view.get("features", {}).get("ball", {})
    bx, by = _pair(ball_record.get("center_xy_norm"))
    bvx, bvy = _pair(ball_record.get("velocity_xy_norm_per_s"))
    direction = ball_record.get("direction_rad")
    direction_value = _finite(direction) if direction is not None else 0.0
    ball = np.asarray(
        [
            _clip(bx, 1.5),
            _clip(by, 1.5),
            _clip(bvx / 3.0, 1.0),
            _clip(bvy / 3.0, 1.0),
            _clip(_finite(ball_record.get("speed_norm_per_s")) / 3.0, 1.0),
            math.sin(direction_value),
            math.cos(direction_value) if direction is not None else 0.0,
            _clip(_finite(ball_record.get("visibility")), 1.0),
        ],
        dtype=np.float32,
    )
    quality_record = view.get("quality", {})
    player_count = _finite(pose.get("formation", {}).get("player_count"))
    sync_quality = 1.0 if quality_record.get("sync_status") == "authoritative" else 0.0
    quality = np.asarray(
        [
            float(bool(quality_record.get("pose_usable"))),
            float(bool(pose.get("four_players_observed"))),
            _clip(_finite(pose.get("pose_visible_ratio")), 1.0),
            _clip(player_count / 4.0, 1.0),
            float(bool(quality_record.get("ball_observed"))),
            float(bool(quality_record.get("court_line_available"))),
            sync_quality,
            float(not bool(quality_record.get("view_missing"))),
        ],
        dtype=np.float32,
    )
    return players, player_mask, ball, quality


def vectorize_record(record: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    player_views = np.zeros((2, 4, PLAYER_FEATURES), dtype=np.float32)
    mask_views = np.zeros((2, 4), dtype=np.float32)
    ball_views = np.zeros((2, BALL_FEATURES), dtype=np.float32)
    quality_views = np.zeros((2, QUALITY_FEATURES), dtype=np.float32)
    views = record.get("views", {})
    for camera_index, camera in enumerate(CAMERAS):
        view = views.get(camera, {}) if isinstance(views, dict) else {}
        player_views[camera_index], mask_views[camera_index], ball_views[camera_index], quality_views[
            camera_index
        ] = vectorize_view(view)
    return player_views, mask_views, ball_views, quality_views


def read_sequences(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_json(manifest_path)
    sequence_path = manifest_path.parent / str(manifest["sequence_file"])
    if sha256_file(sequence_path) != manifest["sequence_file_sha256"]:
        raise ValueError(f"sequence_file SHA-256 不一致: {sequence_path}")
    sequences = []
    with sequence_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                sequences.append(json.loads(line))
    if len(sequences) != int(manifest["sequence_count"]):
        raise ValueError("sequence_count 与实际 JSONL 行数不一致")
    return manifest, sequences


class StructuredSequenceDataset(Dataset[tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]]):
    def __init__(
        self,
        sequences: list[dict[str, Any]],
        split: str,
        tensors: dict[str, dict[str, np.ndarray]],
        split_assignment: dict[str, str] | None = None,
    ) -> None:
        self.items = [
            item
            for item in sequences
            if (
                split_assignment.get(str(item.get("capture_take_id")), item.get("split"))
                if split_assignment is not None
                else item.get("split")
            )
            == split
        ]
        self.tensors = tensors
        if not self.items:
            raise ValueError(f"split={split} 没有结构化序列")

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]:
        item = self.items[index]
        source = item["source"]
        key = str(source["feature_file"])
        arrays = self.tensors[key]
        start = int(source["record_start_index"])
        end = start + int(item["record_count"])
        labels = item["label"]["timeline_labels"]
        targets = np.asarray([CLASSES.index(row["label"]) if row["label"] in CLASSES else 0 for row in labels])
        loss_mask = np.asarray([int(row.get("loss_mask", 0)) for row in labels], dtype=np.float32)
        center_label = str(item["label"]["center_label"])
        center_target = CLASSES.index(center_label) if center_label in CLASSES else -1
        center_mask = float(item["label"].get("center_loss_mask", 0) and center_target >= 0)
        return (
            torch.from_numpy(arrays["players"][start:end]),
            torch.from_numpy(arrays["player_mask"][start:end]),
            torch.from_numpy(arrays["ball"][start:end]),
            torch.from_numpy(arrays["quality"][start:end]),
            torch.from_numpy(targets).long(),
            torch.from_numpy(loss_mask),
            torch.tensor([max(center_target, 0), int(center_mask)], dtype=torch.long),
        )


class ResidualTCNBlock(nn.Module):
    def __init__(self, channels: int, dilation: int, dropout: float) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv1d(channels, channels, 3, padding=dilation, dilation=dilation),
            nn.BatchNorm1d(channels),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Conv1d(channels, channels, 3, padding=dilation, dilation=dilation),
            nn.BatchNorm1d(channels),
            nn.GELU(),
            nn.Dropout(dropout),
        )

    def forward(self, inputs: Tensor) -> Tensor:
        return inputs + self.block(inputs)


class StructuredTemporalModel(nn.Module):
    def __init__(self, hidden_dim: int = 128, temporal_dim: int = 256, layers: int = 4, dropout: float = 0.2) -> None:
        super().__init__()
        player_dim = hidden_dim // 2
        self.player_encoder = nn.Sequential(
            nn.Linear(PLAYER_FEATURES, player_dim), nn.LayerNorm(player_dim), nn.GELU(), nn.Linear(player_dim, player_dim)
        )
        self.view_encoder = nn.Sequential(
            nn.Linear(player_dim * 2 + BALL_FEATURES + QUALITY_FEATURES, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.fusion = nn.Sequential(
            nn.Linear(hidden_dim * 2, temporal_dim), nn.LayerNorm(temporal_dim), nn.GELU()
        )
        self.temporal = nn.Sequential(
            *[ResidualTCNBlock(temporal_dim, 2**index, dropout) for index in range(layers)]
        )
        self.classifier = nn.Conv1d(temporal_dim, len(CLASSES), 1)

    def encode(self, players: Tensor, player_mask: Tensor, ball: Tensor, quality: Tensor) -> Tensor:
        encoded = self.player_encoder(players)
        mask = player_mask.unsqueeze(-1)
        mean = (encoded * mask).sum(dim=-2) / mask.sum(dim=-2).clamp_min(1.0)
        masked = encoded.masked_fill(mask == 0, torch.finfo(encoded.dtype).min)
        maximum = masked.max(dim=-2).values
        maximum = torch.where(mask.sum(dim=-2) > 0, maximum, torch.zeros_like(maximum))
        views = self.view_encoder(torch.cat([mean, maximum, ball, quality], dim=-1))
        # 双摄 late fusion 同时保留平均证据与互补的强响应。
        fused = torch.cat([views.mean(dim=2), views.max(dim=2).values], dim=-1)
        return self.fusion(fused)

    def forward(self, players: Tensor, player_mask: Tensor, ball: Tensor, quality: Tensor) -> Tensor:
        return self.classifier(self.temporal_features(players, player_mask, ball, quality).transpose(1, 2)).transpose(1, 2)

    def temporal_features(self, players: Tensor, player_mask: Tensor, ball: Tensor, quality: Tensor) -> Tensor:
        features = self.encode(players, player_mask, ball, quality)
        return self.temporal(features.transpose(1, 2)).transpose(1, 2)


def classification_metrics(targets: list[int], predictions: list[int]) -> dict[str, Any]:
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
        "accuracy": sum(a == b for a, b in zip(targets, predictions, strict=True)) / max(len(targets), 1),
        "macro_f1": sum(f1s) / len(f1s),
        "rally_active_precision": per_class["rally_active"]["precision"],
        "rally_active_recall": per_class["rally_active"]["recall"],
        "non_play_precision": per_class["non_play"]["precision"],
        "non_play_recall": per_class["non_play"]["recall"],
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def class_weights(
    sequences: list[dict[str, Any]],
    split: str,
    device: torch.device,
    split_assignment: dict[str, str] | None = None,
) -> Tensor:
    counts: Counter[int] = Counter()
    for item in sequences:
        item_split = (
            split_assignment.get(str(item.get("capture_take_id")), item.get("split"))
            if split_assignment is not None
            else item.get("split")
        )
        if item_split != split:
            continue
        for row in item["label"]["timeline_labels"]:
            if row.get("loss_mask") and row.get("label") in CLASSES:
                counts[CLASSES.index(row["label"])] += 1
    total = sum(counts.values())
    values = torch.tensor([math.sqrt(total / max(counts[index], 1)) for index in range(len(CLASSES))], device=device)
    return values / values.mean()
