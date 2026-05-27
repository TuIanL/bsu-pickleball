"""纯图像处理工具，用于动作分类训练样本导出。"""

from __future__ import annotations

from typing import Any

from app.vision.action_classification_preprocessing.schemas import ROIConfig, ROIRecord


def sample_frame_indices(
    *,
    fps: float,
    frame_count: int,
    target_fps: float,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> list[tuple[int, float]]:
    if fps <= 0:
        raise ValueError("fps must be greater than 0")
    if frame_count <= 0:
        return []
    if target_fps <= 0:
        raise ValueError("target_fps must be greater than 0")
    if start_seconds < 0:
        raise ValueError("start_seconds must be greater than or equal to 0")
    duration = frame_count / fps
    end = duration if end_seconds is None else min(end_seconds, duration)
    if end < start_seconds:
        return []

    samples: list[tuple[int, float]] = []
    seen: set[int] = set()
    timestamp = start_seconds
    step = 1.0 / target_fps
    while timestamp <= end + 1e-9:
        frame_index = int(round(timestamp * fps))
        if frame_index >= frame_count:
            break
        if frame_index not in seen:
            seen.add(frame_index)
            samples.append((frame_index, frame_index / fps))
        timestamp += step
    return samples


def crop_court_roi(frame: Any, roi: ROIConfig) -> tuple[Any, ROIRecord]:
    height, width = frame.shape[:2]
    x1 = max(0, min(width - 1, int(round(width * roi.x1_ratio))))
    y1 = max(0, min(height - 1, int(round(height * roi.y1_ratio))))
    x2 = max(x1 + 1, min(width, int(round(width * roi.x2_ratio))))
    y2 = max(y1 + 1, min(height, int(round(height * roi.y2_ratio))))
    record = ROIRecord(
        ratios={
            "x1_ratio": roi.x1_ratio,
            "y1_ratio": roi.y1_ratio,
            "x2_ratio": roi.x2_ratio,
            "y2_ratio": roi.y2_ratio,
        },
        bbox=[x1, y1, x2, y2],
        source_width=width,
        source_height=height,
    )
    return frame[y1:y2, x1:x2], record


def apply_clahe_bgr(frame: Any, *, clip_limit: float = 2.0, tile_grid_size: int = 8) -> Any:
    import cv2  # type: ignore

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(int(tile_grid_size), int(tile_grid_size)))
    enhanced_l = clahe.apply(l_channel)
    enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def apply_light_denoise(frame: Any, *, kernel_size: int = 3, sigma: float = 0.0) -> Any:
    import cv2  # type: ignore

    return cv2.GaussianBlur(frame, (int(kernel_size), int(kernel_size)), float(sigma))


def expand_box(box: list[float], frame_shape: tuple[int, ...], *, scale: float = 1.4) -> list[int]:
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = [float(value) for value in box[:4]]
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    box_width = max(1.0, (x2 - x1) * scale)
    box_height = max(1.0, (y2 - y1) * scale)
    nx1 = max(0, int(round(cx - box_width / 2.0)))
    ny1 = max(0, int(round(cy - box_height / 2.0)))
    nx2 = min(width, int(round(cx + box_width / 2.0)))
    ny2 = min(height, int(round(cy + box_height / 2.0)))
    if nx2 <= nx1:
        nx2 = min(width, nx1 + 1)
    if ny2 <= ny1:
        ny2 = min(height, ny1 + 1)
    return [nx1, ny1, nx2, ny2]


def offset_box(box: list[float] | list[int], x_offset: float, y_offset: float) -> list[float]:
    x1, y1, x2, y2 = [float(value) for value in box[:4]]
    return [x1 + x_offset, y1 + y_offset, x2 + x_offset, y2 + y_offset]


def crop_player(frame: Any, box: list[float], *, output_size: int = 224, scale: float = 1.4) -> tuple[Any, list[int]]:
    import cv2  # type: ignore

    crop_box = expand_box(box, frame.shape, scale=scale)
    x1, y1, x2, y2 = crop_box
    crop = frame[y1:y2, x1:x2]
    resized = cv2.resize(crop, (int(output_size), int(output_size)))
    return resized, crop_box


def build_clip_windows(frame_count: int, *, clip_length: int, clip_stride: int) -> list[list[int]]:
    if clip_length <= 0:
        raise ValueError("clip_length must be greater than 0")
    if clip_stride <= 0:
        raise ValueError("clip_stride must be greater than 0")
    windows: list[list[int]] = []
    start = 0
    while start + clip_length <= frame_count:
        windows.append(list(range(start, start + clip_length)))
        start += clip_stride
    return windows
