from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.action_classification_preprocessing import (  # noqa: E402
    ActionPreprocessingConfig,
    ActionPreprocessingError,
    CLAHEConfig,
    DenoiseConfig,
    ROIConfig,
    export_action_classification_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export target-player crops as action-classification training clips."
    )
    parser.add_argument("input", help="Source video file or directory containing video files.")
    parser.add_argument("--output-root", required=True, help="Output dataset directory.")
    parser.add_argument("--label", required=True, help="Action label, e.g. forehand, backhand, serve.")
    parser.add_argument("--target-fps", type=float, default=20.0, help="Sampling FPS for exported clips.")
    parser.add_argument("--roi", default="0.02,0.30,0.98,0.98", help="Court ROI ratios as x1,y1,x2,y2.")
    parser.add_argument("--disable-clahe", action="store_true", help="Disable CLAHE light enhancement.")
    parser.add_argument("--clahe-clip-limit", type=float, default=2.0, help="CLAHE clip limit.")
    parser.add_argument("--clahe-tile-grid-size", type=int, default=8, help="CLAHE tile grid size.")
    parser.add_argument("--detect-on-enhanced", action="store_true", help="Run person detection on enhanced frames.")
    parser.add_argument("--denoise", action="store_true", help="Apply light GaussianBlur before export.")
    parser.add_argument("--denoise-kernel-size", type=int, default=3, help="GaussianBlur kernel size.")
    parser.add_argument("--denoise-sigma", type=float, default=0.0, help="GaussianBlur sigma.")
    parser.add_argument("--detector-model", default="yolo11n.pt", help="Ultralytics YOLO model path.")
    parser.add_argument("--detector-confidence", type=float, default=0.5, help="Person detector confidence.")
    parser.add_argument("--detector-device", default=None, help="Detector device, e.g. cpu or cuda:0.")
    parser.add_argument(
        "--selection-strategy",
        choices=["largest", "near-left", "near-right", "track-iou", "manual-initial-bbox"],
        default="largest",
        help="Target player selection strategy.",
    )
    parser.add_argument("--manual-initial-bbox", default=None, help="Initial target bbox in ROI coords: x1,y1,x2,y2.")
    parser.add_argument("--bbox-expand-scale", type=float, default=1.4, help="Target bbox expansion scale.")
    parser.add_argument("--output-size", type=int, default=224, help="Square crop output size.")
    parser.add_argument("--clip-length", type=int, default=16, help="Frames per output clip.")
    parser.add_argument("--clip-stride", type=int, default=16, help="Sliding window stride in successful frames.")
    parser.add_argument("--start-seconds", type=float, default=0.0, help="Only process frames at or after this time.")
    parser.add_argument("--end-seconds", type=float, default=None, help="Only process frames at or before this time.")
    parser.add_argument("--jpeg-quality", type=int, default=95, help="OpenCV JPEG quality, from 1 to 100.")
    parser.add_argument("--manifest-name", default="manifest.json", help="Manifest filename under output root.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing manifest or clip files.")
    args = parser.parse_args()

    try:
        x1, y1, x2, y2 = _parse_float_list(args.roi, expected=4, label="--roi")
        manual_bbox = (
            _parse_float_list(args.manual_initial_bbox, expected=4, label="--manual-initial-bbox")
            if args.manual_initial_bbox
            else None
        )
        config = ActionPreprocessingConfig(
            input_path=args.input,
            output_root=args.output_root,
            label=args.label,
            target_fps=args.target_fps,
            roi=ROIConfig(x1_ratio=x1, y1_ratio=y1, x2_ratio=x2, y2_ratio=y2),
            clahe=CLAHEConfig(
                enabled=not args.disable_clahe,
                clip_limit=args.clahe_clip_limit,
                tile_grid_size=args.clahe_tile_grid_size,
            ),
            detect_on_enhanced=args.detect_on_enhanced,
            denoise=DenoiseConfig(
                enabled=args.denoise,
                kernel_size=args.denoise_kernel_size,
                sigma=args.denoise_sigma,
            ),
            detector_model_path=args.detector_model,
            detector_confidence=args.detector_confidence,
            detector_device=args.detector_device,
            selection_strategy=args.selection_strategy,
            manual_initial_bbox=manual_bbox,
            bbox_expand_scale=args.bbox_expand_scale,
            output_size=args.output_size,
            clip_length=args.clip_length,
            clip_stride=args.clip_stride,
            start_seconds=args.start_seconds,
            end_seconds=args.end_seconds,
            jpeg_quality=args.jpeg_quality,
            manifest_name=args.manifest_name,
            overwrite=args.overwrite,
        )
        manifest = export_action_classification_dataset(config)
    except (ActionPreprocessingError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    summary = manifest["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["clips_written"] > 0 and summary["error_count"] == 0 else 1


def _parse_float_list(value: str, *, expected: int, label: str) -> list[float]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != expected:
        raise ValueError(f"{label} must contain {expected} comma-separated numbers")
    return [float(part) for part in parts]


if __name__ == "__main__":
    raise SystemExit(main())
