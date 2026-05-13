from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import cv2  # type: ignore
import numpy as np


VIDEO_EXTENSIONS = (".mov", ".mp4", ".avi", ".mkv", ".webm")
DEFAULT_KEYPOINT_CONFIDENCE = 0.25
DEFAULT_MAX_GAP_FRAMES = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Burn an existing pose_overlay.json skeleton overlay into a video file."
    )
    parser.add_argument("--job-id", help="Analysis job id, for example job-de44b626b9.")
    parser.add_argument("--video", type=Path, help="Source video path. Defaults to the job's uploaded video.")
    parser.add_argument(
        "--pose-overlay",
        type=Path,
        help="pose_overlay.json path. Defaults to backend/data/outputs/<job-id>/pose_overlay.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output .mp4 path. Defaults to backend/data/outputs/<job-id>/pose_overlay_video.mp4.",
    )
    parser.add_argument(
        "--keypoint-confidence",
        type=float,
        default=DEFAULT_KEYPOINT_CONFIDENCE,
        help=f"Minimum keypoint confidence to draw. Default: {DEFAULT_KEYPOINT_CONFIDENCE}.",
    )
    parser.add_argument(
        "--max-gap-frames",
        type=int,
        default=DEFAULT_MAX_GAP_FRAMES,
        help="Largest overlay frame gap to interpolate across. Default: 10.",
    )
    parser.add_argument("--no-boxes", action="store_true", help="Do not draw subject bounding boxes.")
    parser.add_argument("--no-labels", action="store_true", help="Do not draw track id labels.")
    parser.add_argument(
        "--max-frames",
        type=int,
        help="Debug option: stop after this many source frames.",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=300,
        help="Print progress after every N frames. Default: 300.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backend_dir = Path(__file__).resolve().parents[1]
    job_id = args.job_id

    pose_path = resolve_pose_overlay_path(backend_dir, job_id, args.pose_overlay)
    pose_overlay = read_json(pose_path)
    job_id = job_id or pose_overlay.get("job_id")
    if not job_id:
        raise SystemExit("Could not infer job id. Pass --job-id or use a pose_overlay.json with job_id.")

    video_path = resolve_video_path(backend_dir, pose_overlay, args.video)
    output_path = args.output or backend_dir / "data" / "outputs" / job_id / "pose_overlay_video.mp4"

    export_pose_overlay_video(
        video_path=video_path,
        pose_overlay=pose_overlay,
        output_path=output_path,
        draw_boxes=not args.no_boxes,
        draw_labels=not args.no_labels,
        keypoint_confidence=args.keypoint_confidence,
        max_gap_frames=args.max_gap_frames,
        max_frames=args.max_frames,
        progress_interval=args.progress_interval,
    )
    return 0


def resolve_pose_overlay_path(backend_dir: Path, job_id: str | None, explicit_path: Path | None) -> Path:
    if explicit_path:
        path = explicit_path
    elif job_id:
        path = backend_dir / "data" / "outputs" / job_id / "pose_overlay.json"
    else:
        raise SystemExit("Pass --job-id or --pose-overlay.")

    path = path.expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"pose overlay not found: {path}")
    return path


def resolve_video_path(backend_dir: Path, pose_overlay: dict[str, Any], explicit_path: Path | None) -> Path:
    if explicit_path:
        path = explicit_path.expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"video not found: {path}")
        return path

    video_id = pose_overlay.get("video_id")
    if not video_id:
        raise SystemExit("Could not infer source video. Pass --video.")

    uploads_dir = backend_dir / "data" / "uploads"
    for extension in VIDEO_EXTENSIONS:
        path = uploads_dir / f"{video_id}{extension}"
        if path.exists():
            return path.resolve()
    raise SystemExit(f"source video for {video_id} not found in {uploads_dir}")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def export_pose_overlay_video(
    *,
    video_path: Path,
    pose_overlay: dict[str, Any],
    output_path: Path,
    draw_boxes: bool = True,
    draw_labels: bool = True,
    keypoint_confidence: float = DEFAULT_KEYPOINT_CONFIDENCE,
    max_gap_frames: int = DEFAULT_MAX_GAP_FRAMES,
    max_frames: int | None = None,
    progress_interval: int = 300,
) -> Path:
    frames = sorted(pose_overlay.get("frames", []), key=lambda frame: frame.get("frame_index", 0))
    if not frames:
        raise ValueError("pose overlay contains no frames")

    skeleton_edges = pose_overlay.get("skeleton_edges", [])
    source = pose_overlay.get("source") or {}

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open source video: {video_path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or source.get("width") or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or source.get("height") or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError("Could not determine source video dimensions")

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp.mp4")
    if temp_path.exists():
        temp_path.unlink()

    writer = open_video_writer(temp_path, fps, (width, height))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Could not create output video: {temp_path}")

    scale_x = width / float(source.get("width") or width)
    scale_y = height / float(source.get("height") or height)
    frame_cursor = 0
    written = 0

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if max_frames is not None and written >= max_frames:
                break

            frame_index = int(capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            overlay_frame, frame_cursor = resolve_pose_frame(
                frames,
                frame_index,
                frame_cursor,
                max_gap_frames=max_gap_frames,
            )
            if overlay_frame:
                draw_pose_frame(
                    frame,
                    overlay_frame,
                    skeleton_edges,
                    scale_x=scale_x,
                    scale_y=scale_y,
                    draw_boxes=draw_boxes,
                    draw_labels=draw_labels,
                    keypoint_confidence=keypoint_confidence,
                )

            writer.write(frame)
            written += 1
            if progress_interval > 0 and written % progress_interval == 0:
                total = min(frame_count, max_frames) if max_frames else frame_count
                suffix = f"/{total}" if total else ""
                print(f"rendered {written}{suffix} frames")
    finally:
        capture.release()
        writer.release()

    if written == 0:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError("No frames were written")

    shutil.move(str(temp_path), str(output_path))
    print(f"wrote {written} frames to {output_path}")
    return output_path


def open_video_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    for fourcc_name in ("mp4v", "avc1", "H264"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc_name), fps, size)
        if writer.isOpened():
            return writer
        writer.release()
    return cv2.VideoWriter()


def resolve_pose_frame(
    frames: list[dict[str, Any]],
    frame_index: int,
    cursor: int,
    *,
    max_gap_frames: int,
) -> tuple[dict[str, Any] | None, int]:
    while cursor + 1 < len(frames) and int(frames[cursor + 1].get("frame_index", 0)) <= frame_index:
        cursor += 1

    current = frames[cursor]
    next_frame = frames[cursor + 1] if cursor + 1 < len(frames) else None
    current_index = int(current.get("frame_index", 0))

    if current_index == frame_index:
        return current, cursor

    if next_frame is None:
        return (current if frame_index - current_index <= max_gap_frames else None), cursor

    next_index = int(next_frame.get("frame_index", 0))
    gap = next_index - current_index
    if gap <= 0 or gap > max_gap_frames:
        nearest = current if abs(frame_index - current_index) <= abs(next_index - frame_index) else next_frame
        nearest_index = int(nearest.get("frame_index", 0))
        return (nearest if abs(frame_index - nearest_index) <= max_gap_frames else None), cursor

    ratio = (frame_index - current_index) / gap
    return interpolate_pose_frame(current, next_frame, ratio, frame_index), cursor


def interpolate_pose_frame(
    current: dict[str, Any],
    next_frame: dict[str, Any],
    ratio: float,
    frame_index: int,
) -> dict[str, Any]:
    next_subjects = {subject.get("track_id"): subject for subject in next_frame.get("subjects", [])}
    subjects = []
    for subject in current.get("subjects", []):
        track_id = subject.get("track_id")
        next_subject = next_subjects.get(track_id)
        subjects.append(interpolate_subject(subject, next_subject, ratio) if next_subject else subject)

    return {
        **current,
        "frame_index": frame_index,
        "timestamp_seconds": lerp(
            float(current.get("timestamp_seconds", 0.0)),
            float(next_frame.get("timestamp_seconds", 0.0)),
            ratio,
        ),
        "subjects": subjects,
    }


def interpolate_subject(current: dict[str, Any], next_subject: dict[str, Any], ratio: float) -> dict[str, Any]:
    next_keypoints = {keypoint.get("name"): keypoint for keypoint in next_subject.get("keypoints", [])}
    return {
        **current,
        "bbox": interpolate_list(current.get("bbox", []), next_subject.get("bbox", []), ratio),
        "confidence": lerp(float(current.get("confidence", 0.0)), float(next_subject.get("confidence", 0.0)), ratio),
        "keypoints": [
            interpolate_keypoint(keypoint, next_keypoints.get(keypoint.get("name")), ratio)
            for keypoint in current.get("keypoints", [])
        ],
    }


def interpolate_keypoint(
    current: dict[str, Any],
    next_keypoint: dict[str, Any] | None,
    ratio: float,
) -> dict[str, Any]:
    if not next_keypoint:
        return current
    return {
        **current,
        "x": lerp(float(current.get("x", 0.0)), float(next_keypoint.get("x", 0.0)), ratio),
        "y": lerp(float(current.get("y", 0.0)), float(next_keypoint.get("y", 0.0)), ratio),
        "confidence": lerp(
            float(current.get("confidence", 0.0)),
            float(next_keypoint.get("confidence", 0.0)),
            ratio,
        ),
        "visible": bool(current.get("visible", True)) and bool(next_keypoint.get("visible", True)),
    }


def interpolate_list(current: list[Any], next_values: list[Any], ratio: float) -> list[float]:
    return [
        lerp(float(value), float(next_values[index] if index < len(next_values) else value), ratio)
        for index, value in enumerate(current)
    ]


def draw_pose_frame(
    frame: np.ndarray,
    overlay_frame: dict[str, Any],
    skeleton_edges: list[dict[str, Any]],
    *,
    scale_x: float,
    scale_y: float,
    draw_boxes: bool,
    draw_labels: bool,
    keypoint_confidence: float,
) -> None:
    for subject in overlay_frame.get("subjects", []):
        track_id = str(subject.get("track_id") or "")
        color = color_for_track(track_id)
        keypoints = {
            keypoint.get("name"): keypoint
            for keypoint in subject.get("keypoints", [])
            if is_keypoint_drawable(keypoint, keypoint_confidence)
        }

        if draw_boxes:
            draw_bbox(frame, subject.get("bbox", []), color, scale_x, scale_y)
        draw_skeleton(frame, keypoints, skeleton_edges, color, scale_x, scale_y)
        draw_keypoints(frame, keypoints.values(), color, scale_x, scale_y)

        if draw_labels:
            label_anchor = label_point(subject, keypoints.values(), scale_x, scale_y)
            if label_anchor:
                draw_label(frame, f"ID {track_id}", label_anchor, color)


def is_keypoint_drawable(keypoint: dict[str, Any], confidence_threshold: float) -> bool:
    return (
        bool(keypoint.get("visible", True))
        and math.isfinite(float(keypoint.get("x", 0.0)))
        and math.isfinite(float(keypoint.get("y", 0.0)))
        and float(keypoint.get("confidence", 0.0)) >= confidence_threshold
    )


def draw_bbox(
    frame: np.ndarray,
    bbox: list[Any],
    color: tuple[int, int, int],
    scale_x: float,
    scale_y: float,
) -> None:
    if len(bbox) != 4:
        return
    x1, y1, x2, y2 = scaled_bbox(bbox, scale_x, scale_y)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, dst=frame)


def draw_skeleton(
    frame: np.ndarray,
    keypoints: dict[str, dict[str, Any]],
    skeleton_edges: list[dict[str, Any]],
    color: tuple[int, int, int],
    scale_x: float,
    scale_y: float,
) -> None:
    for edge in skeleton_edges:
        start = keypoints.get(edge.get("from_keypoint"))
        end = keypoints.get(edge.get("to_keypoint"))
        if not start or not end:
            continue
        cv2.line(
            frame,
            scaled_point(start, scale_x, scale_y),
            scaled_point(end, scale_x, scale_y),
            color,
            3,
            cv2.LINE_AA,
        )


def draw_keypoints(
    frame: np.ndarray,
    keypoints: Any,
    color: tuple[int, int, int],
    scale_x: float,
    scale_y: float,
) -> None:
    for keypoint in keypoints:
        center = scaled_point(keypoint, scale_x, scale_y)
        cv2.circle(frame, center, 5, (8, 12, 18), -1, cv2.LINE_AA)
        cv2.circle(frame, center, 3, color, -1, cv2.LINE_AA)


def draw_label(
    frame: np.ndarray,
    text: str,
    anchor: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    x, y = anchor
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 2
    (text_width, text_height), baseline = cv2.getTextSize(text, font, scale, thickness)
    x = max(0, min(frame.shape[1] - text_width - 10, x))
    y = max(text_height + 10, min(frame.shape[0] - baseline - 4, y))
    cv2.rectangle(frame, (x, y - text_height - 8), (x + text_width + 10, y + baseline + 4), (8, 12, 18), -1)
    cv2.rectangle(frame, (x, y - text_height - 8), (x + text_width + 10, y + baseline + 4), color, 1)
    cv2.putText(frame, text, (x + 5, y), font, scale, color, thickness, cv2.LINE_AA)


def label_point(
    subject: dict[str, Any],
    keypoints: Any,
    scale_x: float,
    scale_y: float,
) -> tuple[int, int] | None:
    keypoints = list(keypoints)
    head = next((keypoint for keypoint in keypoints if keypoint.get("name") in {"head", "nose"}), None)
    if head:
        x, y = scaled_point(head, scale_x, scale_y)
        return x + 8, y - 12

    bbox = subject.get("bbox", [])
    if len(bbox) == 4:
        x1, y1, _, _ = scaled_bbox(bbox, scale_x, scale_y)
        return x1, y1 - 8
    return None


def scaled_point(keypoint: dict[str, Any], scale_x: float, scale_y: float) -> tuple[int, int]:
    return (round(float(keypoint.get("x", 0.0)) * scale_x), round(float(keypoint.get("y", 0.0)) * scale_y))


def scaled_bbox(bbox: list[Any], scale_x: float, scale_y: float) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
    return (round(x1 * scale_x), round(y1 * scale_y), round(x2 * scale_x), round(y2 * scale_y))


def color_for_track(track_id: str) -> tuple[int, int, int]:
    palette = [
        (72, 220, 136),
        (47, 128, 237),
        (255, 149, 0),
        (255, 77, 79),
        (182, 108, 255),
        (56, 189, 248),
    ]
    try:
        index = int(track_id) - 1
    except ValueError:
        index = sum(ord(char) for char in track_id)
    return palette[index % len(palette)]


def lerp(start: float, end: float, ratio: float) -> float:
    clamped_ratio = min(1.0, max(0.0, ratio))
    return start + (end - start) * clamped_ratio


if __name__ == "__main__":
    raise SystemExit(main())
