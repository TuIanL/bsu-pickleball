#!/usr/bin/env python3
"""backfill_playback_mp4 —— 为历史分片合并源补生成浏览器可播的 faststart 播放版

背景：双摄同步录制的合并视频以分片封装（moof/mdat）写入，浏览器原生 `<video>`
无法可靠播放。本脚本对 `*_merged.mp4` 执行 `-c copy +faststart` 生成
`{camera}_playback.mp4`（不重编码、不改动源），让历史素材在浏览器可播。

用法：
    python -m scripts.backfill_playback_mp4 \
        --path "/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_122645_317228"
    或指定单个文件：
    python -m scripts.backfill_playback_mp4 --path "..../174_merged.mp4"
    全量（递归 glob 所有 *_merged.mp4）：
    python -m scripts.backfill_playback_mp4 --all

说明：失败的条目保留源、打印警告、不影响其余；已存在播放版的跳过。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.camera.ffmpeg_utils import probe_decodable, remux_faststart  # noqa: E402


def playback_path_for(merged: Path) -> Path:
    base = merged.stem[: -len("_merged")] if merged.stem.endswith("_merged") else merged.stem
    return merged.parent / f"{base}_playback.mp4"


def ensure_playback(merged: Path, dry_run: bool = False) -> tuple[Path, str]:
    playback = playback_path_for(merged)
    if playback.is_file() and playback.stat().st_size > 0:
        return playback, "skipped(exists)"
    if dry_run:
        return playback, "queued(dry-run)"
    if remux_faststart(merged, playback) and probe_decodable(playback):
        return playback, "ok"
    playback.unlink(missing_ok=True)
    return playback, "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description="为分片合并源补生成浏览器可播的 faststart 播放版")
    parser.add_argument("--path", help="单个合并 MP4 文件，或包含 *_merged.mp4 的目录")
    parser.add_argument("--all", action="store_true", help="递归扫描全部 *_merged.mp4")
    parser.add_argument("--dry-run", action="store_true", help="只列出待处理项，不实际生成")
    args = parser.parse_args()

    targets: list[Path] = []
    if args.path:
        p = Path(args.path)
        if p.is_file():
            targets = [p]
        elif p.is_dir():
            targets = [q for q in p.rglob("*_merged.mp4")]
    elif args.all:
        # 默认扫描后端 data 目录与常见外接录制目录
        roots = list(Path("data").rglob("") if Path("data").exists() else [])
        targets = []
        for root in roots:
            targets.extend(root.glob("*_merged.mp4"))
    else:
        parser.print_help()
        return 2

    if not targets:
        print("未找到待处理的分片合并源（*_merged.mp4）")
        return 0

    summary = {"ok": 0, "skipped(exists)": 0, "failed": 0, "queued(dry-run)": 0}
    for merged in sorted(targets):
        # 跳过 macOS AppleDouble（._*）等隐藏/元数据文件
        if merged.name.startswith(".") or merged.suffix.lower() != ".mp4":
            continue
        playback, status = ensure_playback(merged, dry_run=args.dry_run)
        summary[status] = summary.get(status, 0) + 1
        arrow = "->" if status == "ok" else "  "
        print(f"[{status}] {merged} {arrow} {playback}")

    print("\n完成：", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())