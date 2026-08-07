"""投影调试叠加视频写入 —— 在视频帧上标注 bbox、脚点、投影坐标、方法/状态。"""

from __future__ import annotations

from pathlib import Path

import cv2  # type: ignore
import numpy as np


class ProjectionDebugOverlayWriter:
    """在逐帧 tracking 过程中写出投影调试叠加视频。"""

    def __init__(self, output_path: Path, fps: float, width: int, height: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(output_path), fourcc, fps if fps > 0 else 25.0, (width, height))
        self._width = width
        self._height = height

    @property
    def is_open(self) -> bool:
        return self._writer.isOpened()

    def write_frame(
        self,
        frame: np.ndarray,
        frame_index: int,
        positions: list,
    ) -> None:
        if not self._writer.isOpened():
            return
        annotated = frame.copy()
        overlay = annotated.copy()

        for pos in positions:
            bbox = pos.bbox if hasattr(pos, "bbox") and pos.bbox and len(pos.bbox) >= 4 else None
            footpoint = (
                pos.image_footpoint
                if hasattr(pos, "image_footpoint") and pos.image_footpoint and len(pos.image_footpoint) >= 2
                else None
            )
            method = getattr(pos, "footpoint_method", None) or "unknown"
            status = getattr(pos, "projection_status", None) or "unknown"
            court = (
                pos.court_position
                if hasattr(pos, "court_position") and pos.court_position and len(pos.court_position) >= 2
                else None
            )
            clip_suspected = False
            if hasattr(pos, "footpoint_metadata") and pos.footpoint_metadata:
                clip_suspected = pos.footpoint_metadata.get("bbox_clip_suspected", False)

            box_color = (50, 210, 235) if clip_suspected else (35, 190, 90)  # yellow if clip, green normal
            box_thickness = 2

            if bbox is not None:
                x1, y1, x2, y2 = [int(round(float(v))) for v in bbox[:4]]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, box_thickness)

                label_parts = [f"T{pos.track_id}"]
                if court is not None:
                    label_parts.append(f"court=({court[0]:.1f},{court[1]:.1f})")
                label_parts.append(f"{method}")
                if clip_suspected:
                    label_parts.append("CLIP_SUSPECT")
                label = " | ".join(label_parts)
                cv2.putText(
                    annotated, label, (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, box_color, 2, cv2.LINE_AA
                )

            if footpoint is not None:
                fx, fy = int(round(footpoint[0])), int(round(footpoint[1]))
                cross_color = (50, 130, 255) if clip_suspected else (50, 50, 255)
                cv2.drawMarker(
                    annotated, (fx, fy), cross_color, markerType=cv2.MARKER_CROSS, markerSize=12, thickness=2
                )

            status_color = (50, 210, 235) if clip_suspected else (200, 200, 200)
            status_text = f"status={status}"
            y_offset = annotated.shape[0] - 40 - pos.track_id * 20
            cv2.putText(
                annotated,
                status_text,
                (12, max(20, y_offset)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                status_color,
                1,
                cv2.LINE_AA,
            )

        alpha = 0.55
        blended = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
        self._writer.write(blended)

    def close(self) -> None:
        if self._writer.isOpened():
            self._writer.release()
