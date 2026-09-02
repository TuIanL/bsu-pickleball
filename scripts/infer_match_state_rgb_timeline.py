#!/usr/bin/env python3
"""用已训练 RGB baseline 生成滑窗状态概率、候选回合和边界评估。"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn import functional as F
from torchvision.io import read_image
from torchvision.transforms import functional as TF

try:
    from .match_state_timeline import decode_state_timeline, evaluate_timeline
    from .train_match_state_rgb import RGBLateFusion
    from .verify_match_state_model_package import validate_package
except ImportError:  # 允许远程节点直接执行该脚本
    from match_state_timeline import decode_state_timeline, evaluate_timeline
    from train_match_state_rgb import RGBLateFusion
    from verify_match_state_model_package import validate_package


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def frame_path(entry: dict[str, Any], timestamp_ms: float, fps: float) -> Path:
    duration_ms = float(entry.get("duration_ms", 0.0))
    clamped = min(max(0.0, timestamp_ms), duration_ms)
    frame_index = max(1, min(int(entry["frame_count"]), int(round(clamped / 1000.0 * fps)) + 1))
    return Path(str(entry["frame_dir"])) / f"{frame_index:06d}.jpg"


def window_coverage(start_ms: float, end_ms: float, duration_ms: float) -> float:
    overlap = max(0.0, min(end_ms, duration_ms) - max(start_ms, 0.0))
    return overlap / max(end_ms - start_ms, 1.0)


def load_rgb_window(
    *,
    views: list[dict[str, Any]],
    center_ms: float,
    duration_ms: float,
    fps: float,
    clip_duration_ms: int,
    frame_count: int,
    model_frame_count: int,
) -> tuple[torch.Tensor | None, float, list[dict[str, Any]]]:
    if len(views) != 2 or any(view.get("status") != "complete" for view in views):
        return None, 0.0, []
    start_ms = center_ms - clip_duration_ms * 0.5
    end_ms = start_ms + clip_duration_ms
    coverage = window_coverage(start_ms, end_ms, duration_ms)
    offsets = np.linspace(0, frame_count - 1, model_frame_count).round().astype(int)
    mean = (0.43216, 0.394666, 0.37645)
    std = (0.22803, 0.22145, 0.216989)
    tensors = []
    view_meta = []
    for view in sorted(views, key=lambda item: str(item["camera_role"])):
        frames = []
        for offset in offsets:
            timestamp_ms = start_ms + offset * 1000.0 / fps
            image = TF.convert_image_dtype(read_image(str(frame_path(view, timestamp_ms, fps))), torch.float32)
            frames.append(TF.normalize(image, mean, std))
        tensors.append(torch.stack(frames, dim=0))
        view_meta.append(
            {"camera_role": view["camera_role"], "logical_media_uri": view["logical_uri"], "coverage": coverage}
        )
    return torch.stack(tensors, dim=0).unsqueeze(0), coverage, view_meta


def ground_truth_for_take(take: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for label in take.get("labels", []):
        start_ms = label.get("start_ms")
        end_ms = label.get("end_ms")
        if start_ms is None or end_ms is None or float(end_ms) <= float(start_ms):
            continue
        result.append({"segment_id": label.get("segment_id"), "start_ms": float(start_ms), "end_ms": float(end_ms)})
    return sorted(result, key=lambda item: item["start_ms"])


def run_take(
    *,
    model: torch.nn.Module,
    take: dict[str, Any],
    cache_entries: dict[str, dict[str, Any]],
    thresholds: dict[str, Any],
    fps: float,
    clip_duration_ms: int,
    frame_count: int,
    model_frame_count: int,
    stride_ms: int,
    device: torch.device,
    max_windows: int | None = None,
) -> dict[str, Any]:
    views = [
        cache_entries[media["logical_uri"]]
        for media in take.get("media", [])
        if media.get("logical_uri") in cache_entries
    ]
    windows: list[dict[str, Any]] = []
    started = time.time()
    with torch.inference_mode():
        for window_index, center_ms in enumerate(range(0, int(take["duration_ms"]) + 1, stride_ms)):
            if max_windows is not None and window_index >= max_windows:
                break
            inputs, coverage, view_meta = load_rgb_window(
                views=views,
                center_ms=float(center_ms),
                duration_ms=float(take["duration_ms"]),
                fps=fps,
                clip_duration_ms=clip_duration_ms,
                frame_count=frame_count,
                model_frame_count=model_frame_count,
            )
            if inputs is None:
                probabilities = {"rally_active": 0.0, "non_play": 0.0}
                insufficient = True
            else:
                logits = model(inputs.to(device))
                values = F.softmax(logits[0], dim=-1).detach().cpu().tolist()
                probabilities = {"rally_active": float(values[0]), "non_play": float(values[1])}
                insufficient = False
            windows.append(
                {
                    "schema_version": "match_state_rgb_timeline_window.v1",
                    "center_ms": center_ms,
                    "requested_start_ms": center_ms - clip_duration_ms * 0.5,
                    "requested_end_ms": center_ms + clip_duration_ms * 0.5,
                    "state_probabilities": probabilities,
                    "coverage": coverage,
                    "view_count": len(view_meta),
                    "view_mask": {item["camera_role"]: True for item in view_meta},
                    "insufficient_evidence": insufficient,
                }
            )
    decoded = decode_state_timeline(
        windows,
        minimum_confidence=float(thresholds.get("minimum_confidence", 0.65)),
        minimum_coverage=float(thresholds.get("minimum_coverage", 0.75)),
        minimum_duration_ms=int(thresholds.get("minimum_duration_ms", 500)),
        hysteresis=float(thresholds.get("hysteresis", 0.1)),
        unknown_on_insufficient_evidence=bool(thresholds.get("unknown_on_insufficient_evidence", True)),
    )
    ground_truth = ground_truth_for_take(take)
    evaluation = evaluate_timeline(decoded["windows"], decoded["segments"], ground_truth)
    return {
        "schema_version": "match_state_rgb_timeline.v1",
        "capture_take_id": take["capture_take_id"],
        "source_session_id": take["source_session_id"],
        "duration_ms": take["duration_ms"],
        "model_input": {
            "modalities": ["rgb"],
            "fps": fps,
            "clip_duration_ms": clip_duration_ms,
            "frame_count": model_frame_count,
            "stride_ms": stride_ms,
        },
        "windows": decoded["windows"],
        "segments": decoded["segments"],
        "ground_truth_segments": ground_truth,
        "evaluation": evaluation,
        "runtime_seconds": round(time.time() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RGB baseline 滑窗时间线推理和边界评估")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-cache-manifest", type=Path, required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument("--stride-ms", type=int, default=500)
    parser.add_argument("--only-session")
    parser.add_argument("--max-windows", type=int, help="仅处理每场前 N 个窗口，用于 CPU/路径 smoke")
    args = parser.parse_args()
    if args.stride_ms <= 0 or (args.max_windows is not None and args.max_windows <= 0):
        raise SystemExit("stride-ms 和 max-windows 必须为正数")
    package_check = validate_package(args.package_dir, strict=True)
    if package_check["status"] != "passed":
        raise SystemExit(json.dumps(package_check, ensure_ascii=False, indent=2))
    package = load_json(args.package_dir / "model_package.json")
    profile = load_json(args.package_dir / str(package["artifacts"]["training_config"]))
    checkpoint_path = args.package_dir / str(package["artifacts"]["weights"])
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        if not args.allow_cpu:
            raise SystemExit("CUDA 不可用；正式全量时间线应在远程 GPU 执行，如确需小规模 CPU 测试请显式传 --allow-cpu")
        device = torch.device("cpu")
    model = RGBLateFusion(pretrained=False).to(device)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    dataset = load_json(args.dataset_manifest)
    rgb_manifest = load_json(args.rgb_cache_manifest)
    entries = rgb_manifest.get("entries", {})
    if not isinstance(entries, dict):
        raise SystemExit("RGB cache manifest entries 必须是对象")
    temporal = profile["temporal_input"]
    results = []
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
            device=device,
            max_windows=args.max_windows,
        )
        output_path = args.output_dir / f"{take['source_session_id']}.timeline.json"
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(result)
        print(
            json.dumps(
                {
                    "source_session_id": take["source_session_id"],
                    "predicted_count": len(result["segments"]),
                    "evaluation": result["evaluation"]["rally"],
                },
                ensure_ascii=False,
            )
        )
    report = {
        "schema_version": "match_state_rgb_timeline_report.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "package_id": package.get("package_id"),
        "model_version": package.get("model_version"),
        "device": str(device),
        "take_count": len(results),
        "per_take": [
            {
                "capture_take_id": item["capture_take_id"],
                "source_session_id": item["source_session_id"],
                "evaluation": item["evaluation"],
            }
            for item in results
        ],
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
