"""cover_poster —— 为已落盘视频抽取一帧 poster 图（比赛库封面预生成）。

设计要点（见 OpenSpec change `library-cover-poster`）：
- poster 是「已落盘视频」的确定性衍生物，在上传/录制登记/双摄合并完成时同步生成。
- 抽帧 SHALL 非阻断：ffmpeg 不可用 / 解码失败 / 视频不存在时仅 warning 并返回 False，
  绝不抛异常、绝不让调用方（视频登记/合并）失败。
- 时间戳避开第 0 帧（常为黑屏/设备预热帧），跳到开球后片刻。
- 输出宽度 ≤480px、jpeg，单张约 20–60KB，与视频文件同目录存储，随视频清理而清理。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

POSTER_SUFFIX = ".poster.jpg"
POSTER_MAX_WIDTH = 480
# ffmpeg `-q:v` 对 MJPEG：2（最佳）~31（最差），5 约等于 jpeg q70~75
POSTER_JPEG_QUALITY = 5


def poster_path_for(video_path: str | Path) -> Path:
    """返回与视频同目录、同 stem 的 poster 文件路径。"""
    p = Path(video_path)
    return p.parent / f"{p.stem}{POSTER_SUFFIX}"


def _seek_seconds(video_path: Path) -> float:
    """用 ffprobe 读时长，计算避开第 0 帧的抽帧时间戳。

    规则：min(max(duration*0.15, 2.0), duration-0.1)，并保证 ≥ 0。
    ffprobe 不可用时回退到 1.0s。
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(video_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        duration = float(result.stdout.strip())
    except Exception:
        return 1.0
    seek = min(max(duration * 0.15, 2.0), duration - 0.1)
    return max(0.0, seek)


def generate_poster(video_path: str | Path, poster_path: str | Path | None = None) -> bool:
    """从视频抽取一帧生成 poster 图。

    成功返回 True；任何失败（文件缺失 / ffmpeg 缺失 / 解码失败）返回 False。
    失败时不留半成品文件。
    """
    src = Path(video_path)
    if not src.exists() or src.stat().st_size <= 0:
        return False

    dst = Path(poster_path) if poster_path is not None else poster_path_for(src)
    seek = _seek_seconds(src)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", f"{seek:.3f}", "-i", str(src),
                "-frames:v", "1", "-q:v", str(POSTER_JPEG_QUALITY),
                "-vf", f"scale='min({POSTER_MAX_WIDTH},iw)':-2",
                str(dst),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=True,
        )
    except Exception as exc:  # noqa: BLE001 - 抽帧失败非阻断
        logger.warning("poster 抽帧失败，跳过（封面回退视频流）: %s -> %s: %s", src, dst, exc)
        dst.unlink(missing_ok=True)
        return False

    if not dst.exists() or dst.stat().st_size <= 0:
        dst.unlink(missing_ok=True)
        return False
    return True
