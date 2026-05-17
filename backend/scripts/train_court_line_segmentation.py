from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.courtvision_calibration_engine.coco_dataset import (
    COCODatasetConversionError,
    COCODatasetValidationError,
    prepare_yolo_segmentation_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and train a court-line segmentation model.")
    parser.add_argument("--dataset-root", default="../datasets/court-line-coco", help="Source COCO dataset root.")
    parser.add_argument("--converted-output", default="../datasets/court-line-yolo", help="YOLO dataset output path.")
    parser.add_argument("--class-name", default="court_line", help="Single segmentation class name.")
    parser.add_argument("--model", default="yolo11n-seg.pt", help="Ultralytics segmentation model or checkpoint.")
    parser.add_argument("--imgsz", type=int, default=1280, help="Training image size. Use 960 or 1280 for thin lines.")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs.")
    parser.add_argument(
        "--batch",
        default="-1",
        help="Ultralytics batch setting. Use -1 for automatic batch sizing, or a number such as 4/8.",
    )
    parser.add_argument("--device", default=None, help="Ultralytics device, e.g. cpu, mps, cuda:0.")
    parser.add_argument("--project", default="../runs/court-line", help="Training run output directory.")
    parser.add_argument("--name", default="court-line-seg", help="Training run name.")
    parser.add_argument("--prepare-only", action="store_true", help="Only validate and convert the dataset.")
    args = parser.parse_args()

    try:
        prepared = prepare_yolo_segmentation_dataset(
            dataset_root=Path(args.dataset_root),
            output_root=Path(args.converted_output),
            class_name=args.class_name,
        )
    except (COCODatasetValidationError, COCODatasetConversionError) as exc:
        payload = getattr(exc, "report", {"error": str(exc)})
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(prepared, ensure_ascii=False, indent=2))
    if args.prepare_only:
        return 0

    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("ultralytics is not installed; install backend vision extras before training")
        return 1

    model = YOLO(args.model)
    model.train(
        data=prepared["dataset_yaml"],
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=_parse_batch(args.batch),
        device=args.device,
        project=args.project,
        name=args.name,
    )
    return 0


def _parse_batch(value: str) -> int | float:
    try:
        integer_value = int(value)
    except ValueError:
        return float(value)
    return integer_value


if __name__ == "__main__":
    raise SystemExit(main())
