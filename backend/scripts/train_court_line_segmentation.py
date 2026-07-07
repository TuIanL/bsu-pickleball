from __future__ import annotations

# 球场线分割模型「准备 + 训练」脚本。
# 作用：把 COCO 格式的球场线标注数据集，转换成 YOLO 分割格式，并（可选地）用 Ultralytics 训练分割模型。

import argparse
import json
from pathlib import Path
import sys


# 把项目根目录（backend/）加入模块搜索路径，使 `from app...` 可用。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 复用 courtvision_calibration_engine 里的 COCO 数据集转换与异常类型。
from app.vision.courtvision_calibration_engine.coco_dataset import (
    COCODatasetConversionError,
    COCODatasetValidationError,
    prepare_yolo_segmentation_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and train a court-line segmentation model.")
    # COCO 数据集根目录（默认项目外的 datasets/court-line-coco）。
    parser.add_argument("--dataset-root", default="../datasets/court-line-coco", help="Source COCO dataset root.")
    # YOLO 数据集输出路径（默认项目外的 datasets/court-line-yolo）。
    parser.add_argument("--converted-output", default="../datasets/court-line-yolo", help="YOLO dataset output path.")
    # 单一分割类别名称（球场线）。
    parser.add_argument("--class-name", default="court_line", help="Single segmentation class name.")
    # 分割模型或 checkpoint 路径（Ultralytics）。
    parser.add_argument("--model", default="yolo11n-seg.pt", help="Ultralytics segmentation model or checkpoint.")
    # 训练图片尺寸（细线用小尺寸 960/1280 更稳）。
    parser.add_argument("--imgsz", type=int, default=1280, help="Training image size. Use 960 or 1280 for thin lines.")
    # 训练轮数。
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs.")
    # batch 设置：-1 表示自动，或写 4/8 等数字。
    parser.add_argument(
        "--batch",
        default="-1",
        help="Ultralytics batch setting. Use -1 for automatic batch sizing, or a number such as 4/8.",
    )
    # 训练设备，如 cpu / mps / cuda:0。
    parser.add_argument("--device", default=None, help="Ultralytics device, e.g. cpu, mps, cuda:0.")
    # 训练运行输出目录（默认项目外的 runs/court-line）。
    parser.add_argument("--project", default="../runs/court-line", help="Training run output directory.")
    # 训练运行名称。
    parser.add_argument("--name", default="court-line-seg", help="Training run name.")
    # 只做数据集校验与转换，不训练。
    parser.add_argument("--prepare-only", action="store_true", help="Only validate and convert the dataset.")
    args = parser.parse_args()

    try:
        # 把 COCO 数据集转换为 YOLO 格式，返回包含 dataset.yaml 等信息的字典。
        prepared = prepare_yolo_segmentation_dataset(
            dataset_root=Path(args.dataset_root),
            output_root=Path(args.converted_output),
            class_name=args.class_name,
        )
    except (COCODatasetValidationError, COCODatasetConversionError) as exc:
        # 转换/校验失败：打印报告（异常里可能带 report 字段）并以非零状态退出。
        payload = getattr(exc, "report", {"error": str(exc)})
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(prepared, ensure_ascii=False, indent=2))
    # 仅准备模式：打印结果后直接退出。
    if args.prepare_only:
        return 0

    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("ultralytics is not installed; install backend vision extras before training")
        return 1

    # 加载模型并开始训练。
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
    # 把 batch 参数解析成整数或浮点数（Ultralytics 接受 -1 自动或具体数值）。
    try:
        integer_value = int(value)
    except ValueError:
        return float(value)
    return integer_value


if __name__ == "__main__":
    raise SystemExit(main())
