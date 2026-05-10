#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Optional


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REQUIRED_IMPORTS = ("torch", "mmpose", "mmcv", "mmengine", "numpy", "cv2")
DEFAULT_BBOX = "40,24,152,232"


def dependency_report() -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_IMPORTS:
        spec = importlib.util.find_spec(name)
        entry: dict[str, Any] = {"installed": spec is not None}
        if spec is not None:
            try:
                module = importlib.import_module(name)
                version = getattr(module, "__version__", None)
                if version:
                    entry["version"] = version
            except Exception as exc:
                entry["installed"] = False
                entry["error"] = f"{type(exc).__name__}: {exc}"
        report[name] = entry
    return report


def parse_bbox(value: str) -> list[float]:
    try:
        bbox = [float(part.strip()) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"bbox must contain numeric xyxy values: {value}") from exc
    if len(bbox) != 4:
        raise argparse.ArgumentTypeError(f"bbox must contain exactly four xyxy values: {value}")
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        raise argparse.ArgumentTypeError(f"bbox must satisfy x2>x1 and y2>y1: {value}")
    return bbox


def resolve_path(value: Optional[str], env_name: str, alias_name: str) -> Optional[Path]:
    raw = value or os.getenv(env_name) or os.getenv(alias_name)
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def load_frame(image_path: Optional[Path]) -> Any:
    import numpy as np  # type: ignore

    if image_path is None:
        frame = np.zeros((256, 192, 3), dtype=np.uint8)
        frame[24:232, 40:152] = (245, 245, 245)
        return frame

    import cv2  # type: ignore

    frame = cv2.imread(str(image_path))
    if frame is None:
        raise RuntimeError(f"Could not read image frame: {image_path}")
    return frame


def validate_dependencies(report: dict[str, dict[str, Any]]) -> list[str]:
    missing = []
    for name, entry in report.items():
        if not entry.get("installed"):
            detail = entry.get("error")
            missing.append(f"{name} ({detail})" if detail else name)
    return missing


def run_validation(args: argparse.Namespace) -> dict[str, Any]:
    dependencies = dependency_report()
    result: dict[str, Any] = {
        "python": {
            "version": sys.version.split()[0],
            "requires": ">=3.10",
            "ok": sys.version_info >= (3, 10),
        },
        "dependencies": dependencies,
    }

    config_path = resolve_path(args.config, "PICKLEBALL_RTMPOSE_CONFIG_PATH", "RTMPOSE_CONFIG_PATH")
    checkpoint_path = resolve_path(
        args.checkpoint,
        "PICKLEBALL_RTMPOSE_CHECKPOINT_PATH",
        "RTMPOSE_CHECKPOINT_PATH",
    )
    device = args.device or os.getenv("PICKLEBALL_RTMPOSE_DEVICE") or os.getenv("RTMPOSE_DEVICE") or "cpu"
    image_path = Path(args.image).expanduser().resolve() if args.image else None

    result["assets"] = {
        "config_path": str(config_path) if config_path else None,
        "config_exists": bool(config_path and config_path.exists()),
        "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
        "checkpoint_exists": bool(checkpoint_path and checkpoint_path.exists()),
        "image_path": str(image_path) if image_path else None,
        "image_exists": bool(image_path and image_path.exists()) if image_path else None,
        "device": device,
    }

    if args.check_only:
        return result

    failures: list[str] = []
    if not result["python"]["ok"]:
        failures.append(f"Python {result['python']['version']} is below 3.10")
    failures.extend(validate_dependencies(dependencies))
    if config_path is None:
        failures.append("RTMPose config path is not configured")
    elif not config_path.exists():
        failures.append(f"RTMPose config not found: {config_path}")
    if checkpoint_path is None:
        failures.append("RTMPose checkpoint path is not configured")
    elif not checkpoint_path.exists():
        failures.append(f"RTMPose checkpoint not found: {checkpoint_path}")
    if image_path is not None and not image_path.exists():
        failures.append(f"Image frame not found: {image_path}")
    if failures:
        result["ok"] = False
        result["errors"] = failures
        return result

    from app.schemas.tracking import FrameDetection
    from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter

    frame = load_frame(image_path)
    height, width = int(frame.shape[0]), int(frame.shape[1])
    subjects = [
        FrameDetection(
            frame_index=0,
            timestamp_seconds=0.0,
            bbox=bbox,
            confidence=1.0,
            track_id=str(index + 1),
            source_width=width,
            source_height=height,
        )
        for index, bbox in enumerate(args.bbox)
    ]

    adapter = RTMPose26Adapter(
        config_path=str(config_path),
        checkpoint_path=str(checkpoint_path),
        device=device,
        conf_threshold=args.confidence,
    )
    pose_frame = adapter.estimate_frame(
        frame=frame,
        subjects=subjects,
        frame_index=0,
        timestamp_seconds=0.0,
    )
    dumped = pose_frame.model_dump(mode="json")
    result["ok"] = bool(dumped["subjects"])
    result["pose_frame"] = dumped
    if not dumped["subjects"]:
        result["errors"] = ["RTMPose inference returned no subjects with usable keypoints"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local RTMPose runtime and single-frame adapter output.")
    parser.add_argument("--config", help="Path to the RTMPose config .py file.")
    parser.add_argument("--checkpoint", help="Path to the RTMPose checkpoint .pth file.")
    parser.add_argument("--device", help="MMPose device such as cpu or cuda:0.")
    parser.add_argument("--image", help="Optional image/frame path. If omitted, a synthetic frame is used.")
    parser.add_argument(
        "--bbox",
        action="append",
        type=parse_bbox,
        default=[],
        help=f"Person bbox as x1,y1,x2,y2. Can be repeated. Default: {DEFAULT_BBOX}",
    )
    parser.add_argument("--confidence", type=float, default=0.3, help="Keypoint visibility confidence threshold.")
    parser.add_argument("--check-only", action="store_true", help="Only report Python, dependencies, and asset status.")
    parser.add_argument("--output", help="Optional path to write JSON validation output.")
    args = parser.parse_args()
    if not args.bbox:
        args.bbox = [parse_bbox(DEFAULT_BBOX)]

    try:
        result = run_validation(args)
    except Exception as exc:
        result = {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result.get("ok") or args.check_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
