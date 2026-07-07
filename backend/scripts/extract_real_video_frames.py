from __future__ import annotations

# 真实比赛视频抽帧脚本。
# 作用：把真实采集到的球场视频，按固定时间间隔抽成单帧图片，存到本地「帧池」，
# 供后续场地线标注 / 标定模型训练使用。输出带 manifest.json 清单。

import argparse
import json
from pathlib import Path
import sys


# 把项目根目录（backend/）加入模块搜索路径，使 `from app...` 可用。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 复用 courtvision_calibration_engine 里的抽帧逻辑与配置/异常类型。
from app.vision.courtvision_calibration_engine.real_video_frame_extraction import (
    FrameExtractionError,
    FrameExtractionSettings,
    extract_real_video_frames,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract real captured court video frames into an annotation-ready local frame pool."
    )
    # 位置参数：输入视频文件，或包含多个视频文件的目录。
    parser.add_argument("input", help="Source video file or directory containing video files.")
    # 输出根目录（默认是项目外的 datasets/real-court-frame-pool）。
    parser.add_argument(
        "--output-root",
        default="../datasets/real-court-frame-pool",
        help="Output directory for per-video frame folders and manifest.json.",
    )
    # 抽帧间隔（秒）。首次建真实球场帧池常用 1.0 或 2.0。
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=2.0,
        help="Sampling interval in seconds. Use 1.0 or 2.0 for a first real-court frame pool.",
    )
    # 每个源视频最多写多少帧。
    parser.add_argument(
        "--max-frames-per-video",
        type=int,
        default=200,
        help="Maximum frames to write per source video.",
    )
    # 只抽该时间点之后的帧。
    parser.add_argument(
        "--start-seconds",
        type=float,
        default=0.0,
        help="Only sample frames at or after this timestamp.",
    )
    # 只抽该时间点之前的帧（None 表示到结尾）。
    parser.add_argument(
        "--end-seconds",
        type=float,
        default=None,
        help="Only sample frames at or before this timestamp.",
    )
    # 输出 JPEG 质量（1~100）。
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="OpenCV JPEG quality, from 1 to 100.",
    )
    # manifest 文件名。
    parser.add_argument(
        "--manifest-name",
        default="manifest.json",
        help="Manifest filename written under --output-root.",
    )
    # 文件名冲突时是否覆盖已存在的帧图片。
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing frame images when names collide.",
    )
    args = parser.parse_args()

    # 把所有参数组装成抽帧配置对象。
    settings = FrameExtractionSettings(
        interval_seconds=args.interval_seconds,
        max_frames_per_video=args.max_frames_per_video,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        jpeg_quality=args.jpeg_quality,
        overwrite=args.overwrite,
        manifest_name=args.manifest_name,
    )

    try:
        # 调用真正的抽帧函数，得到 manifest 清单。
        manifest = extract_real_video_frames(
            input_path=args.input,
            output_root=args.output_root,
            settings=settings,
        )
    except FrameExtractionError as exc:
        # 抽帧错误：打印错误信息并以非零状态退出。
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    # 成功条件：至少写出 1 帧且没有错误；否则返回 1。
    return 1 if manifest["summary"]["frames_written"] == 0 or manifest["summary"]["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
