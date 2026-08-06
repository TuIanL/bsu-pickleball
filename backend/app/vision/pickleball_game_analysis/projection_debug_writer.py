"""投影全链路诊断 —— 生成 projection_debug.jsonl 逐帧记录。"""

from __future__ import annotations

import json
from pathlib import Path


class ProjectionDebugWriter:
    """逐帧将投影诊断信息写入 line-buffered JSONL 文件。"""

    def __init__(
        self,
        output_path: Path | str,
        flush_interval_frames: int = 30,
    ) -> None:
        self._output_path = Path(output_path)
        self._flush_interval = max(1, flush_interval_frames)
        self._file = None
        self._frame_counter = 0
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

    def open(self) -> None:
        self._file = open(self._output_path, "w", encoding="utf-8", buffering=1)

    def close(self) -> None:
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None

    def write_frame(
        self,
        *,
        frame_index: int,
        track_id: int,
        bbox: list[float],
        image_footpoint: list[float],
        footpoint_method: str,
        footpoint_confidence: float | None,
        court_position_raw: list[float],
        court_position_smoothed: list[float],
        projection_status: str,
        minimap_pixel: tuple[int, int] | None,
        homography: list[list[float]] | None = None,
        calibration_quality: str | None = None,
        near_frame_bottom: bool = False,
        bbox_clip_suspected: bool = False,
        pose_unavailable: bool | None = None,
        filter_reason: str | None = None,
    ) -> None:
        if self._file is None:
            return
        record: dict = {
            "frame_index": frame_index,
            "track_id": track_id,
            "bbox": bbox,
            "image_footpoint": image_footpoint,
            "footpoint_method": footpoint_method,
            "footpoint_confidence": footpoint_confidence,
            "court_position_raw": court_position_raw,
            "court_position_smoothed": court_position_smoothed,
            "projection_status": projection_status,
            "minimap_pixel": list(minimap_pixel) if minimap_pixel else None,
        }
        if calibration_quality:
            record["calibration_quality"] = calibration_quality
        if near_frame_bottom or bbox_clip_suspected:
            record["near_frame_bottom"] = near_frame_bottom
            record["bbox_clip_suspected"] = bbox_clip_suspected
        if pose_unavailable is not None:
            record["pose_unavailable"] = pose_unavailable
        if filter_reason:
            record["filter_reason"] = filter_reason
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._frame_counter += 1
        if self._frame_counter % self._flush_interval == 0:
            self._file.flush()

    @property
    def is_open(self) -> bool:
        return self._file is not None and not self._file.closed
