#!/usr/bin/env python3
"""Materialize PTS sidecars for registered videos in a historical CaptureTake.

Example:
  python scripts/prepare_multiview_acceptance.py --take-dir /path/to/take \
    --video cam_1=/path/to/175_merged.mp4 \
    --video cam_2=/path/to/174_merged.mp4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.multiview_acceptance import prepare_take_timing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--take-dir", type=Path, required=True)
    parser.add_argument("--video", action="append", default=[], metavar="SLOT=PATH")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    video_paths: dict[str, Path] = {}
    for item in args.video:
        slot, separator, path = item.partition("=")
        if not separator or not slot or not path:
            parser.error(f"--video must use SLOT=PATH, got {item!r}")
        video_paths[slot] = Path(path)
    payload = prepare_take_timing(
        args.take_dir,
        video_paths=video_paths or None,
        output_path=args.output,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
