"""浏览器可播播放版相关的单元测试。

覆盖：分片合并源 → faststart 播放版的辅助逻辑（命名解析、remux、可解码性）。
这些是纯函数/轻依赖，不拉起完整 app，便于快速回归。
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from pathlib import Path

from app.camera import ffmpeg_utils


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _make_tiny_mp4(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1",
            "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_resolve_browser_stream_path_prefers_playback(tmp_path: Path) -> None:
    merged = tmp_path / "174_merged.mp4"
    merged.write_bytes(b"merged")
    playback = tmp_path / "174_playback.mp4"
    playback.write_bytes(b"playback")

    assert ffmpeg_utils.resolve_browser_stream_path(merged) == playback

    playback.unlink()
    assert ffmpeg_utils.resolve_browser_stream_path(merged) == merged


def test_resolve_browser_stream_path_ts_to_merged(tmp_path: Path) -> None:
    ts = tmp_path / "abc.ts"
    ts.write_bytes(b"ts")
    merged = tmp_path / "abc_merged.mp4"
    merged.write_bytes(b"merged")

    assert ffmpeg_utils.resolve_browser_stream_path(ts) == merged

    merged.unlink()
    assert ffmpeg_utils.resolve_browser_stream_path(ts) == ts


def test_resolve_browser_stream_path_plain_mp4_untouched(tmp_path: Path) -> None:
    normal = tmp_path / "normal.mp4"
    normal.write_bytes(b"plain")

    assert ffmpeg_utils.resolve_browser_stream_path(normal) == normal


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="需要 ffmpeg")
def test_remux_faststart_yields_decodable_non_fragmented(tmp_path: Path) -> None:
    src = tmp_path / "src.mp4"
    _make_tiny_mp4(src)
    dst = tmp_path / "out.mp4"

    assert ffmpeg_utils.remux_faststart(src, dst)
    assert dst.stat().st_size > 0
    assert ffmpeg_utils.probe_decodable(dst)

    # faststart 输出应为普通 MP4：头部 moov 随后 mdat，无 moof 分片
    with dst.open("rb") as file:
        header = file.read(64)
    assert b"moov" in header
    assert b"moof" not in header


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="需要 ffmpeg")
def test_probe_decodable_rejects_garbage(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a real video file at all")
    assert ffmpeg_utils.probe_decodable(junk) is False