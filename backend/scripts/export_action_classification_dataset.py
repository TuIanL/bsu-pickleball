from __future__ import annotations

# 动作分类数据集导出脚本。
# 作用：把「目标球员」的视频裁剪片段，处理成可供动作分类模型训练的 clip（短视频片段）数据集。
# 支持的预处理包括：ROI 裁剪、CLAHE 光照增强、降噪、人体检测、目标球员选择、正方形裁剪、滑窗切片等。

import argparse
import json
from pathlib import Path
import sys


# 把项目根目录（backend/）加入模块搜索路径，使得后续 `from app...` 能正常导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 复用 action_classification_preprocessing 模块里真正的处理逻辑与配置/异常类型。
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
    # 位置参数：输入视频文件，或包含多个视频文件的目录。
    parser.add_argument("input", help="Source video file or directory containing video files.")
    # 必填：数据集输出根目录。
    parser.add_argument("--output-root", required=True, help="Output dataset directory.")
    # 必填：动作标签，例如 forehand(正手)/backhand(反手)/serve(发球)。
    parser.add_argument("--label", required=True, help="Action label, e.g. forehand, backhand, serve.")
    # 导出 clip 的采样帧率，默认 20 FPS。
    parser.add_argument("--target-fps", type=float, default=20.0, help="Sampling FPS for exported clips.")
    # 球场 ROI 比例（x1,y1,x2,y2，取值 0~1），只在这个区域内做处理。
    parser.add_argument("--roi", default="0.02,0.30,0.98,0.98", help="Court ROI ratios as x1,y1,x2,y2.")
    # 是否禁用 CLAHE 光照增强（默认开启）。
    parser.add_argument("--disable-clahe", action="store_true", help="Disable CLAHE light enhancement.")
    # CLAHE 裁剪阈值（限制对比度放大上限）。
    parser.add_argument("--clahe-clip-limit", type=float, default=2.0, help="CLAHE clip limit.")
    # CLAHE 分块网格边长。
    parser.add_argument("--clahe-tile-grid-size", type=int, default=8, help="CLAHE tile grid size.")
    # 是否在「增强后的帧」上做人检测（默认在原始帧上检测）。
    parser.add_argument("--detect-on-enhanced", action="store_true", help="Run person detection on enhanced frames.")
    # 是否做轻微高斯模糊降噪。
    parser.add_argument("--denoise", action="store_true", help="Apply light GaussianBlur before export.")
    # 高斯模糊核大小（需为奇数）。
    parser.add_argument("--denoise-kernel-size", type=int, default=3, help="GaussianBlur kernel size.")
    # 高斯模糊 sigma（标准差）。
    parser.add_argument("--denoise-sigma", type=float, default=0.0, help="GaussianBlur sigma.")
    # YOLO 人体检测模型路径。
    parser.add_argument("--detector-model", default="yolo11n.pt", help="Ultralytics YOLO model path.")
    # 人体检测置信度阈值。
    parser.add_argument("--detector-confidence", type=float, default=0.5, help="Person detector confidence.")
    # 检测设备，如 cpu / cuda:0。
    parser.add_argument("--detector-device", default=None, help="Detector device, e.g. cpu or cuda:0.")
    # 目标球员选择策略。
    parser.add_argument(
        "--selection-strategy",
        choices=["largest", "near-left", "near-right", "track-iou", "manual-initial-bbox"],
        default="largest",
        help="Target player selection strategy.",
    )
    # 手动指定初始目标框（ROI 坐标系下的 x1,y1,x2,y2）。
    parser.add_argument("--manual-initial-bbox", default=None, help="Initial target bbox in ROI coords: x1,y1,x2,y2.")
    # 目标框外扩倍数（让裁剪略微宽松）。
    parser.add_argument("--bbox-expand-scale", type=float, default=1.4, help="Target bbox expansion scale.")
    # 正方形裁剪输出边长（像素）。
    parser.add_argument("--output-size", type=int, default=224, help="Square crop output size.")
    # 每个输出 clip 的帧数。
    parser.add_argument("--clip-length", type=int, default=16, help="Frames per output clip.")
    # 滑窗步长（在「成功检测到的帧」之间滑动）。
    parser.add_argument("--clip-stride", type=int, default=16, help="Sliding window stride in successful frames.")
    # 只处理该时间点之后的帧。
    parser.add_argument("--start-seconds", type=float, default=0.0, help="Only process frames at or after this time.")
    # 只处理该时间点之前的帧（None 表示处理到结尾）。
    parser.add_argument("--end-seconds", type=float, default=None, help="Only process frames at or before this time.")
    # 输出 JPEG 质量（1~100）。
    parser.add_argument("--jpeg-quality", type=int, default=95, help="OpenCV JPEG quality, from 1 to 100.")
    # manifest 文件名（记录导出结果的清单）。
    parser.add_argument("--manifest-name", default="manifest.json", help="Manifest filename under output root.")
    # 是否覆盖已存在的 manifest 或 clip 文件。
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing manifest or clip files.")
    args = parser.parse_args()

    try:
        # 把 "--roi" 字符串解析成 4 个浮点数。
        x1, y1, x2, y2 = _parse_float_list(args.roi, expected=4, label="--roi")
        # 若提供了手动初始框，同样解析成 4 个浮点数；否则为 None。
        manual_bbox = (
            _parse_float_list(args.manual_initial_bbox, expected=4, label="--manual-initial-bbox")
            if args.manual_initial_bbox
            else None
        )
        # 把所有命令行参数组装成配置对象。
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
        # 调用真正的导出函数，得到 manifest（导出清单）。
        manifest = export_action_classification_dataset(config)
    except (ActionPreprocessingError, ValueError) as exc:
        # 预处理或参数错误：打印错误信息并以非零状态退出。
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    summary = manifest["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # 成功条件：至少写出 1 个 clip，且没有错误。
    return 0 if summary["clips_written"] > 0 and summary["error_count"] == 0 else 1


def _parse_float_list(value: str, *, expected: int, label: str) -> list[float]:
    # 把 "a,b,c,..." 形式的字符串按逗号拆成浮点数列表，并校验数量。
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != expected:
        raise ValueError(f"{label} must contain {expected} comma-separated numbers")
    return [float(part) for part in parts]


if __name__ == "__main__":
    raise SystemExit(main())
