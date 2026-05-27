"""真实视频帧提取 —— 按时间间隔从视频中抽取标注候选帧，用于标定数据集构建。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


SUPPORTED_VIDEO_EXTENSIONS = {
    ".avi",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mts",
    ".webm",
}


class FrameExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class FrameExtractionSettings:
    interval_seconds: float = 2.0
    max_frames_per_video: int | None = 200
    start_seconds: float = 0.0
    end_seconds: float | None = None
    jpeg_quality: int = 95
    overwrite: bool = False
    manifest_name: str = "manifest.json"


def extract_real_video_frames(
    input_path: str | Path,
    output_root: str | Path,
    settings: FrameExtractionSettings | None = None,
) -> dict[str, Any]:
    """Extract annotation candidate frames from one video or a directory of videos."""

    settings = settings or FrameExtractionSettings()
    _validate_settings(settings)

    source = Path(input_path).expanduser()
    output = Path(output_root).expanduser()
    if not source.exists():
        raise FrameExtractionError(f"Input path not found: {source}")
    if source.is_dir() and output.resolve() == source.resolve():
        raise FrameExtractionError("Output root must be different from the input video directory")

    video_paths = discover_video_paths(source)
    if not video_paths:
        raise FrameExtractionError(f"No supported video files found under: {source}")

    output.mkdir(parents=True, exist_ok=True)
    used_stems: dict[str, int] = {}
    videos = [
        _extract_one_video(
            video_path=video_path,
            output_root=output,
            output_stem=_unique_output_stem(video_path, used_stems),
            settings=settings,
        )
        for video_path in video_paths
    ]

    frames_written = sum(int(video["frames_written"]) for video in videos)
    error_count = sum(len(video["errors"]) for video in videos)
    manifest_path = output / settings.manifest_name
    manifest = {
        "manifest_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(source),
        "output_root": str(output),
        "manifest_path": str(manifest_path),
        "settings": asdict(settings),
        "summary": {
            "video_count": len(videos),
            "frames_written": frames_written,
            "error_count": error_count,
        },
        "videos": videos,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def discover_video_paths(input_path: str | Path) -> list[Path]:
    path = Path(input_path).expanduser()
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    return sorted(
        child
        for child in path.iterdir()
        if child.is_file() and child.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )


def sanitize_video_stem(stem: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", stem.strip())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-._")
    return normalized or "video"


def _extract_one_video(
    video_path: Path,
    output_root: Path,
    output_stem: str,
    settings: FrameExtractionSettings,
) -> dict[str, Any]:
    video_output = output_root / output_stem
    entry: dict[str, Any] = {
        "source_path": str(video_path),
        "source_name": video_path.name,
        "output_stem": output_stem,
        "output_dir": str(video_output),
        "fps": None,
        "frame_count": None,
        "duration_seconds": None,
        "width": None,
        "height": None,
        "frames_written": 0,
        "frames": [],
        "errors": [],
    }

    try:
        import cv2  # type: ignore
    except ImportError as exc:
        entry["errors"].append({"message": "OpenCV is required to extract video frames"})
        return entry

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        entry["errors"].append({"message": f"Could not open video: {video_path}"})
        return entry

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration_seconds = frame_count / fps if fps > 0 and frame_count > 0 else None
        entry.update(
            {
                "fps": fps,
                "frame_count": frame_count,
                "duration_seconds": duration_seconds,
                "width": width,
                "height": height,
            }
        )

        if fps <= 0:
            entry["errors"].append({"message": f"Video FPS metadata is unavailable: {video_path}"})
            return entry
        if frame_count <= 0:
            entry["errors"].append({"message": f"Video frame count metadata is unavailable: {video_path}"})
            return entry

        video_output.mkdir(parents=True, exist_ok=True)
        target_time = settings.start_seconds
        while True:
            if settings.end_seconds is not None and target_time > settings.end_seconds + 1e-9:
                break
            if settings.max_frames_per_video is not None and entry["frames_written"] >= settings.max_frames_per_video:
                break

            frame_index = int(round(target_time * fps))
            if frame_index >= frame_count:
                break

            frame_name = _frame_file_name(output_stem, frame_index, target_time)
            frame_path = video_output / frame_name
            if frame_path.exists() and not settings.overwrite:
                entry["errors"].append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(target_time, 3),
                        "message": f"Output frame already exists: {frame_path}",
                    }
                )
                break

            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                entry["errors"].append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(target_time, 3),
                        "message": f"Could not read frame {frame_index} from {video_path}",
                    }
                )
                break

            written = cv2.imwrite(
                str(frame_path),
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), int(settings.jpeg_quality)],
            )
            if not written:
                entry["errors"].append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(target_time, 3),
                        "message": f"Could not write frame: {frame_path}",
                    }
                )
                break

            frame_record = {
                "source_path": str(video_path),
                "output_path": str(frame_path),
                "file_name": frame_name,
                "frame_index": frame_index,
                "timestamp_seconds": round(target_time, 3),
                "fps": fps,
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
            }
            entry["frames"].append(frame_record)
            entry["frames_written"] = int(entry["frames_written"]) + 1
            target_time += settings.interval_seconds
    finally:
        capture.release()

    return entry


def _validate_settings(settings: FrameExtractionSettings) -> None:
    if settings.interval_seconds <= 0:
        raise FrameExtractionError("interval_seconds must be greater than 0")
    if settings.max_frames_per_video is not None and settings.max_frames_per_video <= 0:
        raise FrameExtractionError("max_frames_per_video must be greater than 0 when provided")
    if settings.start_seconds < 0:
        raise FrameExtractionError("start_seconds must be greater than or equal to 0")
    if settings.end_seconds is not None and settings.end_seconds < settings.start_seconds:
        raise FrameExtractionError("end_seconds must be greater than or equal to start_seconds")
    if not 1 <= settings.jpeg_quality <= 100:
        raise FrameExtractionError("jpeg_quality must be between 1 and 100")
    if not settings.manifest_name.endswith(".json"):
        raise FrameExtractionError("manifest_name must end with .json")


def _unique_output_stem(video_path: Path, used_stems: dict[str, int]) -> str:
    base = sanitize_video_stem(video_path.stem)
    count = used_stems.get(base, 0) + 1
    used_stems[base] = count
    return base if count == 1 else f"{base}-{count}"


def _frame_file_name(stem: str, frame_index: int, timestamp_seconds: float) -> str:
    return f"{stem}_f{frame_index:06d}_t{timestamp_seconds:08.2f}s.jpg"
