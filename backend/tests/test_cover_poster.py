"""cover_poster 抽帧工具单测：成功 / 失败容错两条路径 + 路径契约。"""

from __future__ import annotations

import subprocess

import pytest

from app.services.cover_poster import POSTER_SUFFIX, generate_poster, poster_path_for


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return True
    except Exception:
        return False


def test_poster_path_colocated(tmp_path):
    video = tmp_path / "x.mp4"
    assert poster_path_for(video) == tmp_path / f"x{POSTER_SUFFIX}"


def test_generate_poster_missing_video(tmp_path):
    assert generate_poster(tmp_path / "nope.mp4") is False


def test_generate_poster_bad_file(tmp_path):
    bogus = tmp_path / "bad.mp4"
    bogus.write_bytes(b"not a real video")
    assert generate_poster(bogus) is False
    # 失败不留半成品文件
    assert not poster_path_for(bogus).exists()


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_generate_poster_success(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25",
            "-pix_fmt", "yuv420p", str(src),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
        check=True,
    )
    poster = tmp_path / "poster.jpg"
    assert generate_poster(src, poster) is True
    assert poster.exists()
    assert poster.stat().st_size > 0
