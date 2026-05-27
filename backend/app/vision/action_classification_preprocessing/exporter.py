"""动作分类训练数据集导出器。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol

from app.schemas.tracking import Detection
from app.vision.action_classification_preprocessing.preprocessing import (
    apply_clahe_bgr,
    apply_light_denoise,
    build_clip_windows,
    crop_court_roi,
    crop_player,
    offset_box,
    sample_frame_indices,
)
from app.vision.action_classification_preprocessing.schemas import (
    ActionPreprocessingConfig,
    ActionPreprocessingError,
    ClipRecord,
    FrameSample,
    VideoManifest,
    dataclass_to_dict,
)
from app.vision.action_classification_preprocessing.selection import select_target_detection
from app.vision.courtvision_calibration_engine.real_video_frame_extraction import (
    SUPPORTED_VIDEO_EXTENSIONS,
    sanitize_video_stem,
)
from app.vision.player_tracking_engine.person_detector import PersonDetector


class DetectorProtocol(Protocol):
    def detect(self, frame: object) -> list[Detection]:
        ...


def export_action_classification_dataset(
    config: ActionPreprocessingConfig,
    *,
    detector: DetectorProtocol | None = None,
) -> dict[str, Any]:
    """Export action-classification player crops for one video or a directory of videos."""

    source = config.input_path
    output_root = config.output_root
    if not source.exists():
        raise ActionPreprocessingError(f"Input path not found: {source}")
    if source.is_dir() and output_root.resolve() == source.resolve():
        raise ActionPreprocessingError("Output root must be different from the input video directory")

    manifest_path = output_root / config.manifest_name
    if manifest_path.exists() and not config.overwrite:
        raise ActionPreprocessingError(f"Output manifest already exists: {manifest_path}")

    video_paths = discover_video_paths(source)
    if not video_paths:
        raise ActionPreprocessingError(f"No supported video files found under: {source}")

    output_root.mkdir(parents=True, exist_ok=True)
    detector = detector or PersonDetector(
        model_path=config.detector_model_path,
        conf_threshold=config.detector_confidence,
        device=config.detector_device,
    )
    used_stems: dict[str, int] = {}
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
    clips_written = sum(video.clips_written for video in videos)
    frames_written = sum(video.frames_written for video in videos)
    error_count = sum(len(video.errors) for video in videos)
    skipped_frame_count = sum(video.skipped_frame_count for video in videos)
    manifest = {
        "manifest_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(source),
        "output_root": str(output_root),
        "manifest_path": str(manifest_path),
        "settings": config.to_manifest_dict(),
        "summary": {
            "status": "ok" if clips_written > 0 and error_count == 0 else "partial" if clips_written > 0 else "no_samples",
            "video_count": len(videos),
            "clips_written": clips_written,
            "frames_written": frames_written,
            "skipped_frame_count": skipped_frame_count,
            "error_count": error_count,
        },
        "videos": [dataclass_to_dict(video) for video in videos],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def discover_video_paths(input_path: str | Path) -> list[Path]:
    path = Path(input_path).expanduser()
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    return sorted(child for child in path.iterdir() if child.is_file() and child.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS)


def _export_one_video(
    *,
    video_path: Path,
    output_root: Path,
    output_stem: str,
    config: ActionPreprocessingConfig,
    detector: DetectorProtocol,
) -> VideoManifest:
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to export action classification crops") from exc

    entry = VideoManifest(
        source_path=str(video_path),
        source_name=video_path.name,
        output_stem=output_stem,
    )
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        entry.errors.append({"message": f"Could not open video: {video_path}"})
        return entry

    try:
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
        if fps <= 0:
            entry.errors.append({"message": f"Video FPS metadata is unavailable: {video_path}"})
            return entry
        if frame_count <= 0:
            entry.errors.append({"message": f"Video frame count metadata is unavailable: {video_path}"})
            return entry

        frame_samples: list[tuple[FrameSample, Any]] = []
        previous_bbox: list[float] | None = None
        for frame_index, timestamp in sample_frame_indices(
            fps=fps,
            frame_count=frame_count,
            target_fps=config.target_fps,
            start_seconds=config.start_seconds,
            end_seconds=config.end_seconds,
        ):
            entry.processed_frame_count += 1
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                entry.skipped_frame_count += 1
                entry.errors.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(timestamp, 3),
                        "message": f"Could not read frame {frame_index}",
                    }
                )
                continue

            roi_frame, roi_record = crop_court_roi(frame, config.roi)
            enhanced_frame = roi_frame
            if config.clahe.enabled:
                enhanced_frame = apply_clahe_bgr(
                    enhanced_frame,
                    clip_limit=config.clahe.clip_limit,
                    tile_grid_size=config.clahe.tile_grid_size,
                )
            if config.denoise.enabled:
                enhanced_frame = apply_light_denoise(
                    enhanced_frame,
                    kernel_size=config.denoise.kernel_size,
                    sigma=config.denoise.sigma,
                )
            detection_frame = enhanced_frame if config.detect_on_enhanced else roi_frame
            detections = _detect(detector, detection_frame, frame_index)
            target = select_target_detection(
                detections,
                strategy=config.selection_strategy,
                frame_shape=roi_frame.shape,
                previous_bbox=previous_bbox,
                manual_initial_bbox=config.manual_initial_bbox,
            )
            if target is None:
                entry.skipped_frame_count += 1
                entry.errors.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(timestamp, 3),
                        "message": "No usable person detection for target player",
                    }
                )
                continue

            crop, crop_bbox_roi = crop_player(
                enhanced_frame,
                target.bbox,
                output_size=config.output_size,
                scale=config.bbox_expand_scale,
            )
            previous_bbox = target.bbox
            entry.selected_frame_count += 1
            source_bbox = offset_box(target.bbox, roi_record.bbox[0], roi_record.bbox[1])
            crop_bbox_source = [int(value) for value in offset_box(crop_bbox_roi, roi_record.bbox[0], roi_record.bbox[1])]
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

        _write_clip_outputs(
            entry=entry,
            output_root=output_root,
            output_stem=output_stem,
            config=config,
            frame_samples=frame_samples,
        )
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
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to write action classification crops") from exc

    windows = build_clip_windows(len(frame_samples), clip_length=config.clip_length, clip_stride=config.clip_stride)
    for clip_index, sample_indices in enumerate(windows):
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
            ok = cv2.imwrite(str(frame_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), int(config.jpeg_quality)])
            if not ok:
                entry.errors.append({"message": f"Could not write frame: {frame_path}"})
                write_failed = True
                break
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
    if hasattr(detector, "detect_frame"):
        return detector.detect_frame(frame, frame_index)  # type: ignore[attr-defined]
    return detector.detect(frame)


def _unique_output_stem(video_path: Path, used_stems: dict[str, int]) -> str:
    base = sanitize_video_stem(video_path.stem)
    count = used_stems.get(base, 0) + 1
    used_stems[base] = count
    return base if count == 1 else f"{base}-{count}"


def _frame_file_name(frame_index: int) -> str:
    return f"frame_{frame_index:03d}.jpg"
