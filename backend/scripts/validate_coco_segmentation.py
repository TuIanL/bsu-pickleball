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
    args = parser.parse_args()

    try:
        report = validate_coco_segmentation_dataset(Path(args.dataset_root), splits=args.splits)
    except COCODatasetValidationError as exc:
        print(json.dumps(exc.report, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
