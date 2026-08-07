"""
动作分类训练数据集导出器。

这个文件是整个预处理流程的"总指挥"：
拿到一份配置（ActionPreprocessingConfig），把视频逐帧读出来，
增强 → 检测人 → 选中目标球员 → 裁出球员图 → 拼成 clip → 写出图片 + manifest 清单。

对外唯一要调用的就是 `export_action_classification_dataset(config)`，
它内部会：发现视频 → 逐个视频导出 → 汇总成 manifest.json 返回。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

import json  # 把清单写成 JSON 文件
from dataclasses import asdict  # 把 dataclass 转 dict
from datetime import UTC, datetime  # 生成清单的创建时间（带时区）
from pathlib import Path  # 路径对象
from typing import Any, Protocol  # Any：任意类型；Protocol：定义"结构化的接口约定"

# 检测框数据结构（来自 tracking schemas）
from app.schemas.tracking import Detection

# 预处理工具函数（来自同包 preprocessing）
from app.vision.action_classification_preprocessing.preprocessing import (
    apply_clahe_bgr,
    apply_light_denoise,
    build_clip_windows,
    crop_court_roi,
    crop_player,
    offset_box,
    sample_frame_indices,
)

# 配置与产物数据结构（来自同包 schemas）
from app.vision.action_classification_preprocessing.schemas import (
    ActionPreprocessingConfig,
    ActionPreprocessingError,
    ClipRecord,
    FrameSample,
    VideoManifest,
    dataclass_to_dict,
)

# 目标球员选择策略（来自同包 selection）
from app.vision.action_classification_preprocessing.selection import select_target_detection

# 视频扩展名白名单 + 文件名清洗工具（来自其它 vision 子模块）
from app.vision.courtvision_calibration_engine.real_video_frame_extraction import (
    SUPPORTED_VIDEO_EXTENSIONS,
    sanitize_video_stem,
)

# 真正的人体检测器（YOLO）
from app.vision.player_tracking_engine.person_detector import PersonDetector


class DetectorProtocol(Protocol):
    """
    "协议（Protocol）"是 Python 的"结构化类型"：它不要求类真的继承它，
    只要某个对象"长这样"（有 `detect(frame) -> list[Detection]` 方法），就能当作 DetectorProtocol 用。
    这样做的好处：导出函数既能接收真正的 PersonDetector，也能接收测试用的假检测器，
    而不需要它们之间存在继承关系。
    """

    def detect(self, frame: object) -> list[Detection]: ...


def export_action_classification_dataset(
    config: ActionPreprocessingConfig,
    *,
    detector: DetectorProtocol | None = None,
) -> dict[str, Any]:
    """
    导出动作分类所需的球员裁剪样本（一个视频，或一个文件夹里的多个视频）。

    这是本模块的"主入口"。返回一份 manifest 字典（同时也写成了 manifest.json 文件）。

    参数：
    - config：总配置（输入/输出路径、label、采样率、ROI、增强、选择策略等）；
    - detector：可选，传入自定义检测器；不传则按配置新建一个 PersonDetector。
    """
    # 取出配置里的输入/输出路径
    source = config.input_path
    output_root = config.output_root

    # 输入必须存在
    if not source.exists():
        raise ActionPreprocessingError(f"Input path not found: {source}")
    # 不能把输出目录设成和输入视频目录相同，否则会互相污染
    if source.is_dir() and output_root.resolve() == source.resolve():
        raise ActionPreprocessingError("Output root must be different from the input video directory")

    # 如果清单已存在且不允许覆盖，直接报错，避免误覆盖已有数据
    manifest_path = output_root / config.manifest_name
    if manifest_path.exists() and not config.overwrite:
        raise ActionPreprocessingError(f"Output manifest already exists: {manifest_path}")

    # 发现所有要处理的视频文件（单个文件 or 文件夹递归）
    video_paths = discover_video_paths(source)
    if not video_paths:
        raise ActionPreprocessingError(f"No supported video files found under: {source}")

    # 确保输出根目录存在
    output_root.mkdir(parents=True, exist_ok=True)

    # 没有外部传入检测器，就按配置新建一个真正的人检测器
    detector = detector or PersonDetector(
        model_path=config.detector_model_path,
        conf_threshold=config.detector_confidence,
        device=config.detector_device,
    )

    # used_stems 用来给同名视频做去重（如 a.mp4、a_001.mp4 → a、a-2）
    used_stems: dict[str, int] = {}
    # 逐个视频导出，收集每个视频的 VideoManifest
    videos = [
        _export_one_video(
            video_path=video_path,
            output_root=output_root,
            output_stem=_unique_output_stem(video_path, used_stems),
            config=config,
            detector=detector,
        )
        for video_path in video_paths
    ]

    # 把所有视频的统计数字汇总
    clips_written = sum(video.clips_written for video in videos)
    frames_written = sum(video.frames_written for video in videos)
    error_count = sum(len(video.errors) for video in videos)
    skipped_frame_count = sum(video.skipped_frame_count for video in videos)

    # 拼出最终 manifest 字典
    manifest = {
        "manifest_version": 1,
        "created_at": datetime.now(UTC).isoformat(),  # 带时区的创建时间
        "input_path": str(source),
        "output_root": str(output_root),
        "manifest_path": str(manifest_path),
        "settings": config.to_manifest_dict(),  # 把配置原样记下来，便于复现
        "summary": {
            # 状态判断：有 clip 且无错误 → "ok"；有 clip 但有错误 → "partial"；一个 clip 都没 → "no_samples"
            "status": "ok"
            if clips_written > 0 and error_count == 0
            else "partial"
            if clips_written > 0
            else "no_samples",
            "video_count": len(videos),
            "clips_written": clips_written,
            "frames_written": frames_written,
            "skipped_frame_count": skipped_frame_count,
            "error_count": error_count,
        },
        "videos": [dataclass_to_dict(video) for video in videos],
    }
    # 把 manifest 写成 JSON 文件（ensure_ascii=False 让中文标签能正常显示）
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def discover_video_paths(input_path: str | Path) -> list[Path]:
    """
    根据输入路径，找出所有要处理的视频文件。

    - 如果输入是单个文件 → 直接返回 [该文件]；
    - 如果输入是文件夹 → 返回里面所有"扩展名在白名单内"的文件（按名字排序）；
    - 既不是文件也不是文件夹 → 返回空列表。
    """
    path = Path(input_path).expanduser()
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    return sorted(
        child for child in path.iterdir() if child.is_file() and child.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )


def _export_one_video(
    *,
    video_path: Path,
    output_root: Path,
    output_stem: str,
    config: ActionPreprocessingConfig,
    detector: DetectorProtocol,
) -> VideoManifest:
    """
    处理单个视频：逐帧读取 → 增强 → 检测 → 选目标 → 裁球员 → 暂存 → 最后拼 clip 写出。

    返回这个视频的 VideoManifest（含统计与错误）。
    """
    # 延迟导入 OpenCV，只有真正要处理视频时才需要它
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to export action classification crops") from exc

    # 初始化这个视频的清单对象
    entry = VideoManifest(
        source_path=str(video_path),
        source_name=video_path.name,
        output_stem=output_stem,
    )
    # 用 OpenCV 打开视频文件
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        entry.errors.append({"message": f"Could not open video: {video_path}"})
        return entry

    try:
        # 读取视频元信息（帧率、总帧数、宽高）
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration_seconds = frame_count / fps if fps > 0 and frame_count > 0 else None
        entry.fps = fps
        entry.frame_count = frame_count
        entry.duration_seconds = duration_seconds
        entry.width = width
        entry.height = height
        # 元信息缺失则记录错误并返回，无法继续
        if fps <= 0:
            entry.errors.append({"message": f"Video FPS metadata is unavailable: {video_path}"})
            return entry
        if frame_count <= 0:
            entry.errors.append({"message": f"Video frame count metadata is unavailable: {video_path}"})
            return entry

        # frame_samples 暂存 (帧记录, 裁好的图)；后面拼 clip 时再统一写出
        frame_samples: list[tuple[FrameSample, Any]] = []
        previous_bbox: list[float] | None = None  # 上一帧选中的框，供 track 类策略做 IoU 跟踪
        # 先算好要抽哪些帧
        for frame_index, timestamp in sample_frame_indices(
            fps=fps,
            frame_count=frame_count,
            target_fps=config.target_fps,
            start_seconds=config.start_seconds,
            end_seconds=config.end_seconds,
        ):
            entry.processed_frame_count += 1
            # 把视频"定位"到指定帧（虽然逐帧 read 也行，但跳转更稳）
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                # 读不出这一帧：跳过并记录
                entry.skipped_frame_count += 1
                entry.errors.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(timestamp, 3),
                        "message": f"Could not read frame {frame_index}",
                    }
                )
                continue

            # 1) 按 ROI 裁出场地区域
            roi_frame, roi_record = crop_court_roi(frame, config.roi)
            enhanced_frame = roi_frame
            # 2) 可选 CLAHE 增强
            if config.clahe.enabled:
                enhanced_frame = apply_clahe_bgr(
                    enhanced_frame,
                    clip_limit=config.clahe.clip_limit,
                    tile_grid_size=config.clahe.tile_grid_size,
                )
            # 3) 可选去噪
            if config.denoise.enabled:
                enhanced_frame = apply_light_denoise(
                    enhanced_frame,
                    kernel_size=config.denoise.kernel_size,
                    sigma=config.denoise.sigma,
                )
            # 4) 决定在"增强后"还是"原始 ROI"画面上做检测
            detection_frame = enhanced_frame if config.detect_on_enhanced else roi_frame
            detections = _detect(detector, detection_frame, frame_index)
            # 5) 从检测到的人里选目标球员
            target = select_target_detection(
                detections,
                strategy=config.selection_strategy,
                frame_shape=roi_frame.shape,
                previous_bbox=previous_bbox,
                manual_initial_bbox=config.manual_initial_bbox,
            )
            if target is None:
                # 这一帧没合适目标：跳过
                entry.skipped_frame_count += 1
                entry.errors.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(timestamp, 3),
                        "message": "No usable person detection for target player",
                    }
                )
                continue

            # 6) 裁出目标球员图（按 output_size resize）
            crop, crop_bbox_roi = crop_player(
                enhanced_frame,
                target.bbox,
                output_size=config.output_size,
                scale=config.bbox_expand_scale,
            )
            previous_bbox = target.bbox
            entry.selected_frame_count += 1
            # 7) 把"相对 ROI 的框"换算回"相对整张原图的框"（加上 ROI 左上角偏移）
            source_bbox = offset_box(target.bbox, roi_record.bbox[0], roi_record.bbox[1])
            crop_bbox_source = [
                int(value) for value in offset_box(crop_bbox_roi, roi_record.bbox[0], roi_record.bbox[1])
            ]
            # 先给个占位文件名（真正写出时再改成最终路径）
            placeholder_name = _frame_file_name(len(frame_samples))
            frame_record = FrameSample(
                source_path=str(video_path),
                frame_index=frame_index,
                timestamp_seconds=round(timestamp, 3),
                output_path="",
                file_name=placeholder_name,
                roi=dataclass_to_dict(roi_record),
                detection_count=len(detections),
                selection_strategy=config.selection_strategy,
                confidence=target.confidence,
                bbox_roi=[float(value) for value in target.bbox],
                bbox_source=[float(value) for value in source_bbox],
                crop_bbox_roi=crop_bbox_roi,
                crop_bbox_source=crop_bbox_source,
            )
            frame_samples.append((frame_record, crop))

        # 8) 所有帧处理完，把它们按 clip_length/clip_stride 拼成 clip 并写出图片
        _write_clip_outputs(
            entry=entry,
            output_root=output_root,
            output_stem=output_stem,
            config=config,
            frame_samples=frame_samples,
        )
        # 如果一个 clip 都没生成，记一条说明（方便排查是帧数不够还是全被跳过）
        if entry.clips_written == 0:
            entry.errors.append(
                {
                    "message": (
                        f"No complete clips generated: selected {entry.selected_frame_count} frames, "
                        f"clip_length={config.clip_length}"
                    )
                }
            )
    finally:
        # 无论成功还是出错，都确保释放视频文件句柄
        capture.release()
    return entry


def _write_clip_outputs(
    *,
    entry: VideoManifest,
    output_root: Path,
    output_stem: str,
    config: ActionPreprocessingConfig,
    frame_samples: list[tuple[FrameSample, Any]],
) -> None:
    """
    把暂存的帧样本拼成 clip 并写出图片。

    逻辑：
    - 用 build_clip_windows 算出"哪些帧序号组成一个 clip"；
    - 每个 clip 建一个目录：output_root/<label>/<stem>_clipNNNN/；
    - 把每帧的 crop 图写成 frame_XXX.jpg；
    - 若出现重名且不允许覆盖，则该 clip 跳过并记录错误。
    """
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to write action classification crops") from exc

    # 计算 clip 窗口（每个窗口是一组帧序号）
    windows = build_clip_windows(len(frame_samples), clip_length=config.clip_length, clip_stride=config.clip_stride)
    for clip_index, sample_indices in enumerate(windows):
        # 输出目录：output_root/类别标签/视频名_clip0000
        clip_dir = output_root / config.label / f"{output_stem}_clip{clip_index:04d}"
        if clip_dir.exists() and not config.overwrite:
            entry.errors.append({"message": f"Output clip already exists: {clip_dir}"})
            continue
        clip_dir.mkdir(parents=True, exist_ok=True)
        clip_frames: list[FrameSample] = []
        write_failed = False
        for frame_position, sample_index in enumerate(sample_indices):
            sample, crop = frame_samples[sample_index]
            file_name = _frame_file_name(frame_position)
            frame_path = clip_dir / file_name
            if frame_path.exists() and not config.overwrite:
                entry.errors.append({"message": f"Output frame already exists: {frame_path}"})
                write_failed = True
                break
            # 用 OpenCV 把裁剪图写成 JPEG（带质量参数）
            ok = cv2.imwrite(str(frame_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), int(config.jpeg_quality)])
            if not ok:
                entry.errors.append({"message": f"Could not write frame: {frame_path}"})
                write_failed = True
                break
            # 复制一份帧记录，填上最终文件名和输出路径
            clip_sample = FrameSample(**asdict(sample))
            clip_sample.file_name = file_name
            clip_sample.output_path = str(frame_path)
            clip_frames.append(clip_sample)
            entry.frames_written += 1
        if write_failed:
            continue
        entry.clips_written += 1
        entry.clips.append(
            ClipRecord(
                label=config.label,
                video_stem=output_stem,
                clip_index=clip_index,
                output_dir=str(clip_dir),
                frames=clip_frames,
            )
        )


def _detect(detector: DetectorProtocol, frame: object, frame_index: int) -> list[Detection]:
    """
    调用检测器做人体检测，兼容两种接口：
    - 若检测器有 `detect_frame(frame, frame_index)`（带帧序号，便于做跟踪）就用它；
    - 否则退回到 `detect(frame)`。
    """
    if hasattr(detector, "detect_frame"):
        return detector.detect_frame(frame, frame_index)  # type: ignore[attr-defined]
    return detector.detect(frame)


def _unique_output_stem(video_path: Path, used_stems: dict[str, int]) -> str:
    """
    生成不重复的输出名（stem）。

    例如两个视频都叫 match.mp4，第一个得到 "match"，第二个得到 "match-2"，
    保证输出目录不互相覆盖。used_stems 在多次调用间共享计数。
    """
    base = sanitize_video_stem(video_path.stem)
    count = used_stems.get(base, 0) + 1
    used_stems[base] = count
    return base if count == 1 else f"{base}-{count}"


def _frame_file_name(frame_index: int) -> str:
    """
    生成帧图片文件名，如第 0 帧 → "frame_000.jpg"。
    :03d 表示用 3 位零填充的十进制整数。
    """
    return f"frame_{frame_index:03d}.jpg"
