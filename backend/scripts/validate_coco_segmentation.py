from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.courtvision_calibration_engine.coco_dataset import (
    COCODatasetValidationError,
    validate_coco_segmentation_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a COCO segmentation dataset for court-line training.")
    parser.add_argument("--dataset-root", default="../datasets/court-line-coco", help="COCO dataset root directory.")
    parser.add_argument("--splits", nargs="*", default=None, help="Splits to validate, default: train val test.")
    parser.add_argument("--target-category", default=None, help="Expected COCO category name for category target validation.")
    parser.add_argument(
        "--target-strategy",
        choices=["category", "merge", "unspecified"],
        default=None,
        help="Target validation strategy. Use 'merge' for one-class training from all annotated categories.",
    )
    parser.add_argument(
        "--evidence-output",
        default=None,
        help="Optional ignored local directory where acceptance summary and previews should be written.",
    )
    parser.add_argument(
        "--preview-samples-per-split",
        type=int,
        default=0,
        help="Number of annotation preview images to write per split when --evidence-output is set.",
    )
    args = parser.parse_args()

    try:
        report = validate_coco_segmentation_dataset(
            Path(args.dataset_root),
            splits=args.splits,
            target_category=args.target_category,
            target_strategy=args.target_strategy,
            evidence_output=Path(args.evidence_output) if args.evidence_output else None,
            preview_samples_per_split=max(0, args.preview_samples_per_split),
        )
    except COCODatasetValidationError as exc:
        print(json.dumps(exc.report, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
