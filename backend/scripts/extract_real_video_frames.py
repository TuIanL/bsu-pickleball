from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.courtvision_calibration_engine.real_video_frame_extraction import (
    FrameExtractionError,
    FrameExtractionSettings,
    extract_real_video_frames,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract real captured court video frames into an annotation-ready local frame pool."
    )
    parser.add_argument("input", help="Source video file or directory containing video files.")
    parser.add_argument(
        "--output-root",
        default="../datasets/real-court-frame-pool",
        help="Output directory for per-video frame folders and manifest.json.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=2.0,
        help="Sampling interval in seconds. Use 1.0 or 2.0 for a first real-court frame pool.",
    )
    parser.add_argument(
        "--max-frames-per-video",
        type=int,
        default=200,
        help="Maximum frames to write per source video.",
    )
    parser.add_argument(
        "--start-seconds",
        type=float,
        default=0.0,
        help="Only sample frames at or after this timestamp.",
    )
    parser.add_argument(
        "--end-seconds",
        type=float,
        default=None,
        help="Only sample frames at or before this timestamp.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="OpenCV JPEG quality, from 1 to 100.",
    )
    parser.add_argument(
        "--manifest-name",
        default="manifest.json",
        help="Manifest filename written under --output-root.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing frame images when names collide.",
    )
    args = parser.parse_args()

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
        manifest = extract_real_video_frames(
            input_path=args.input,
            output_root=args.output_root,
            settings=settings,
        )
    except FrameExtractionError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 1 if manifest["summary"]["frames_written"] == 0 or manifest["summary"]["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
