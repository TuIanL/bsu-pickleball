"""ffmpeg_utils —— FFmpeg 可用性检查（从 recorder.py 迁移）"""

from __future__ import annotations

import subprocess
from pathlib import Path


def check_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return True
    except Exception:
        return False


def remux_faststart(src: str | Path, dst: str | Path, timeout: float = 3600) -> bool:
    """在不重编码的前提下，把视频重新封装为 faststart MP4（moov 在文件头）。

    faststart 封装后的 MP4 可被浏览器原生 `<video>` 可靠播放；
    分片封装（moof/mdat）的输出文件则不一定可以。失败时删除 dst 并返回 False。
    """
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(dst)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=True,
        )
        return Path(dst).stat().st_size > 0
    except Exception:
        Path(dst).unlink(missing_ok=True)
        return False


def probe_decodable(path: str | Path) -> bool:
    """用 ffprobe 读取首个视频流，确认文件可被解码（非仅文件头存在）。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=nw=1:nk=1", str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def resolve_browser_stream_path(path: str | Path) -> Path:
    """把磁盘视频路径解析为浏览器可直接播放的路径。

    优先使用同目录的 faststart 播放版（浏览器可播），其次合并 MP4，最后原路径：
    - `*.ts` → 同目录 `{stem}_merged.mp4`（浏览器不支持 TS）
    - `*_merged.mp4`（分片）→ 同目录 `{base}_playback.mp4`（faststart，浏览器可播）
    若对应文件不存在则原样返回。
    """
    candidate = Path(path)

    if candidate.suffix.lower() == ".ts":
        merged = candidate.parent / f"{candidate.stem}_merged.mp4"
        if merged.exists():
            candidate = merged

    if candidate.suffix.lower() == ".mp4" and candidate.stem.endswith("_merged"):
        base = candidate.stem[: -len("_merged")]
        playback = candidate.parent / f"{base}_playback.mp4"
        if playback.exists():
            candidate = playback

    return candidate
