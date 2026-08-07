from __future__ import annotations

# COCO 分割数据集「校验」脚本（用于球场线训练前检查数据是否合格）。
import argparse
import json
import sys
from pathlib import Path

# 把项目根目录（backend/）加入模块搜索路径，使 `from app...` 可用。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 复用 courtvision_calibration_engine 里的 COCO 校验函数与异常类型。
from app.vision.courtvision_calibration_engine.coco_dataset import (
    COCODatasetValidationError,
    validate_coco_segmentation_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a COCO segmentation dataset for court-line training.")
    # COCO 数据集根目录。
    parser.add_argument("--dataset-root", default="../datasets/court-line-coco", help="COCO dataset root directory.")
    # 需要校验的 split（可多个），默认 train/val/test。
    parser.add_argument("--splits", nargs="*", default=None, help="Splits to validate, default: train val test.")
    # 期望的 COCO 类别名称（用于类别目标校验）。
    parser.add_argument(
        "--target-category", default=None, help="Expected COCO category name for category target validation."
    )
    # 目标校验策略：category / merge / unspecified。
    parser.add_argument(
        "--target-strategy",
        choices=["category", "merge", "unspecified"],
        default=None,
        help="Target validation strategy. Use 'merge' for one-class training from all annotated categories.",
    )
    # 可选的「证据输出」目录（当前脚本里该参数实际被忽略，但保留接口）。
    parser.add_argument(
        "--evidence-output",
        default=None,
        help="Optional ignored local directory where acceptance summary and previews should be written.",
    )
    # 每个 split 写多少张标注预览图（仅在设置了 --evidence-output 时生效）。
    parser.add_argument(
        "--preview-samples-per-split",
        type=int,
        default=0,
        help="Number of annotation preview images to write per split when --evidence-output is set.",
    )
    args = parser.parse_args()

    try:
        # 调用真正的校验函数，得到报告字典。
        report = validate_coco_segmentation_dataset(
            Path(args.dataset_root),
            splits=args.splits,
            target_category=args.target_category,
            target_strategy=args.target_strategy,
            evidence_output=Path(args.evidence_output) if args.evidence_output else None,
            preview_samples_per_split=max(0, args.preview_samples_per_split),
        )
    except COCODatasetValidationError as exc:
        # 校验失败：打印异常自带的 report 并以非零状态退出。
        print(json.dumps(exc.report, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
