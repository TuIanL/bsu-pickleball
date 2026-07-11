"""ffmpeg_utils —— FFmpeg 可用性检查（从 recorder.py 迁移）"""
from __future__ import annotations

import subprocess


def check_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)
        return True
    except Exception:
        return False
