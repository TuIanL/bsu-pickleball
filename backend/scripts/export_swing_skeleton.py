#!/usr/bin/env python3
"""挥拍视频骨架叠加导出工具。

读取一段挥拍视频，逐帧执行 YOLO 人体检测 → IoU 跟踪 → RTMPose 姿态估计 → 骨架叠加绘制，
同步输出带骨架的叠加视频和逐帧 JPG 照片集。

用法:
    python backend/scripts/export_swing_skeleton.py --video data/demo-videos/forehand-drive.mp4
    python backend/scripts/export_swing_skeleton.py --video swing.mp4 --device cuda --no-labels
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")

COLOR_PALETTE = [
    (72, 220, 136),
    (47, 128, 237),
    (255, 149, 0),
    (255, 77, 79),
    (182, 108, 255),
    (56, 189, 248),
]


def _load_overlay_module():
    """通过 importlib 加载 export_pose_overlay_video.py 中的绘制函数，避免拷贝代码。"""
    overlay_path = BACKEND_DIR / "scripts" / "export_pose_overlay_video.py"
    spec = importlib.util.spec_from_file_location("_pose_overlay_video", overlay_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_OVERLAY = _load_overlay_module()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="挥拍视频骨架叠加导出工具")
    parser.add_argument("--video", type=Path, required=True, help="输入视频路径")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="输出根目录（默认 outputs/）")
    parser.add_argument("--device", type=str, default="cpu", help="推理设备（默认 cpu）")
    parser.add_argument("--conf-threshold", type=float, default=0.25, help="YOLO 检测置信度阈值（默认 0.25）")
    parser.add_argument("--keypoint-confidence", type=float, default=0.25, help="关键点绘制最低置信度（默认 0.25）")
    parser.add_argument("--no-boxes", action="store_true", help="不绘制边界框")
    parser.add_argument("--no-labels", action="store_true", help="不绘制 ID 标签")
    return parser.parse_args()


def check_dependencies() -> None:
    missing = []
    for mod, hint in [
        ("ultralytics", "pip install ultralytics"),
        ("mmpose", "pip install mmpose mmcv mmengine"),
        ("mmcv", "pip install mmcv"),
        ("torch", "pip install torch"),
        ("cv2", "pip install opencv-python"),
        ("numpy", "pip install numpy"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"  {mod} 未安装 → {hint}")
    if missing:
        print("缺少 Python 依赖：")
        for line in missing:
            print(line)
        sys.exit(1)


def compute_iou(box1: list[float], box2: list[float]) -> float:
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0


def match_detections(
    active_tracks: dict[int, list[float]],
    detections: list,
    iou_threshold: float = 0.3,
) -> tuple[dict[int, object], list[int]]:
    """IoU 贪心匹配：将当前检测关联到已有 track_id。

    Returns:
        assignments: {track_id: Detection}  已匹配的
        unmatched: [idx, ...]  未匹配的检测索引
    """
    assignments: dict[int, object] = {}
    unmatched = list(range(len(detections)))

    for track_id, prev_bbox in active_tracks.items():
        best_iou = iou_threshold
        best_idx = -1
        for i in unmatched:
            iou = compute_iou(prev_bbox, detections[i].bbox)
            if iou > best_iou:
                best_iou = iou
                best_idx = i
        if best_idx >= 0:
            assignments[track_id] = detections[best_idx]
            unmatched.remove(best_idx)

    return assignments, unmatched


def color_for_track(track_id: int) -> tuple[int, int, int]:
    return COLOR_PALETTE[(track_id - 1) % len(COLOR_PALETTE)]


def main() -> int:
    args = parse_args()

    # ---- 依赖检查 ----
    check_dependencies()

    # 重载模块后导入项目内模块
    from app.vision.player_tracking_engine.person_detector import PersonDetector
    from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter
    from app.schemas.tracking import FrameDetection
    from app.schemas.pose import DEFAULT_SKELETON_EDGES

    # ---- 输入验证 ----
    video_path = args.video.expanduser().resolve()
    if not video_path.exists():
        print(f"视频文件不存在: {video_path}")
        return 1
    if video_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        print(f"不支持的视频格式: {video_path.suffix}（支持 {', '.join(SUPPORTED_VIDEO_EXTENSIONS)}）")
        return 1

    video_stem = video_path.stem
    output_root = args.output_dir.expanduser().resolve()
    video_output_dir = output_root / video_stem
    frames_dir = video_output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    overlay_video_path = video_output_dir / "overlay.mp4"

    # ---- 打开视频 ----
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"无法打开视频: {video_path}")
        return 1

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    print(f"视频: {video_path.name}")
    print(f"分辨率: {width}x{height}  FPS: {fps:.1f}  总帧数: {total_frames or '未知'}")

    # ---- 加载模型 ----
    print("加载 YOLO 检测模型 ...")
    detector = PersonDetector(device=args.device, conf_threshold=args.conf_threshold)

    print("加载 RTMPose 姿态模型 ...")
    rtmpose_dir = BACKEND_DIR.parent / "models" / "rtmpose"
    config_files = sorted(rtmpose_dir.glob("configs/*.py"))
    checkpoint_files = sorted(rtmpose_dir.glob("*.pth"))

    if not config_files:
        print(f"未找到 RTMPose 配置文件，请确认 {rtmpose_dir / 'configs/'} 目录存在")
        return 1
    if not checkpoint_files:
        print(f"未找到 RTMPose checkpoint，请确认 {rtmpose_dir} 目录下有 .pth 文件")
        return 1

    pose_adapter = RTMPose26Adapter(
        config_path=str(config_files[0]),
        checkpoint_path=str(checkpoint_files[0]),
        device=args.device,
        conf_threshold=args.keypoint_confidence,
    )
    print(f"  config:  {config_files[0].name}")
    print(f"  weights: {checkpoint_files[0].name}")
    print(f"  device:  {args.device}")

    # ---- 骨架边定义 ----
    skeleton_edges = [{"from_keypoint": s, "to_keypoint": e} for s, e in DEFAULT_SKELETON_EDGES]

    # ---- 初始化视频写入器 ----
    writer = _OVERLAY.open_video_writer(overlay_video_path, fps, (width, height))
    if not writer.isOpened():
        print(f"无法创建输出视频: {overlay_video_path}")
        return 1

    # ---- 主循环 ----
    active_tracks: dict[int, list[float]] = {}
    next_track_id = 1
    frame_index = 0
    processed = 0

    print("开始处理 ...\n")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        timestamp = frame_index / fps

        # Step 1: YOLO 人体检测
        detections = detector.detect(frame)

        # Step 2: IoU 跟踪
        assignments, unmatched = match_detections(active_tracks, detections)
        for idx in unmatched:
            assignments[next_track_id] = detections[idx]
            next_track_id += 1
        active_tracks = {tid: det.bbox for tid, det in assignments.items()}

        # Step 3: 构建 FrameDetection 列表
        frame_detections = [
            FrameDetection(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                bbox=det.bbox,
                confidence=det.confidence,
                class_name="person",
                track_id=str(track_id),
                source_width=width,
                source_height=height,
            )
            for track_id, det in assignments.items()
        ]

        # Step 4: RTMPose 姿态估计
        try:
            pose_frame = pose_adapter.estimate_frame(
                frame, frame_detections, frame_index, timestamp
            )
        except Exception:
            pose_frame = None

        # Step 5: 绘制骨架叠加
        if pose_frame is not None and pose_frame.subjects:
            _OVERLAY.draw_pose_frame(
                frame,
                pose_frame.model_dump(),
                skeleton_edges,
                scale_x=1.0,
                scale_y=1.0,
                draw_boxes=not args.no_boxes,
                draw_labels=not args.no_labels,
                keypoint_confidence=args.keypoint_confidence,
            )

        # Step 6: 写入叠加视频帧
        writer.write(frame)

        # Step 7: 写入逐帧照片
        cv2.imwrite(
            str(frames_dir / f"frame_{frame_index + 1:04d}.jpg"),
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 95],
        )

        processed += 1
        frame_index += 1

        if processed % 30 == 0:
            suffix = f"/{total_frames}" if total_frames else ""
            print(f"  已处理 {processed}{suffix} 帧")

    # ---- 清理 ----
    cap.release()
    writer.release()

    print(f"\n完成！共处理 {processed} 帧")
    print(f"叠加视频: {overlay_video_path}")
    print(f"照片集:   {frames_dir} ({processed} 张)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
