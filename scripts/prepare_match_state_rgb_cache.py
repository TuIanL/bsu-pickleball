#!/usr/bin/env python3
"""在远程节点将双摄源视频一次性转换为训练用 RGB 帧缓存。

该脚本必须在远程数据根目录执行。缓存只保存缩放后的 JPEG 帧和索引，不改变源视频，
并通过临时目录与完成标记避免训练读取半成品。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "match_state_rgb_frame_cache.v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def media_items(dataset: dict[str, Any], only_session: str | None, only_camera: str | None) -> Iterable[dict[str, Any]]:
    for take in dataset.get("takes", []):
        if only_session and take.get("source_session_id") != only_session:
            continue
        for media in take.get("media", []):
            if only_camera and media.get("camera_role") != only_camera:
                continue
            yield {
                "capture_take_id": take["capture_take_id"],
                "source_session_id": take["source_session_id"],
                "duration_ms": int(take["duration_ms"]),
                **media,
            }


def write_index(path: Path, entries: dict[str, dict[str, Any]], identity: dict[str, Any]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "cache_id": f"rgbf_{stable_hash(identity)[:20]}",
        "identity": identity,
        "generated_at": datetime.now(UTC).isoformat(),
        "entries": dict(sorted(entries.items())),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_media(
    *,
    dataset_root: Path,
    output_root: Path,
    media: dict[str, Any],
    fps: float,
    size: int,
    jpeg_quality: int,
    ffmpeg_bin: str,
) -> dict[str, Any]:
    logical_uri = str(media["logical_uri"])
    identity = {
        "logical_uri": logical_uri,
        "fps": fps,
        "size": size,
        "jpeg_quality": jpeg_quality,
        "source_relative_path": media["remote_relative_path"],
    }
    cache_key = stable_hash(identity)[:24]
    target = output_root / cache_key
    marker = target / "cache.json"
    if marker.is_file():
        existing = load_json(marker)
        if existing.get("status") == "complete" and existing.get("identity") == identity:
            return existing

    source = dataset_root / str(media["remote_relative_path"])
    if not source.is_file():
        raise ValueError(f"源视频不存在: {source}")
    partial = output_root / f".{cache_key}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True, exist_ok=True)
    pattern = partial / "%06d.jpg"
    vf = (
        f"fps={fps:g},scale={size}:{size}:force_original_aspect_ratio=decrease,"
        f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:black"
    )
    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        vf,
        "-q:v",
        str(jpeg_quality),
        "-start_number",
        "1",
        str(pattern),
    ]
    subprocess.run(command, check=True)
    frame_count = len(list(partial.glob("*.jpg")))
    if frame_count <= 0:
        raise ValueError(f"ffmpeg 没有产生帧: {source}")
    if target.exists():
        shutil.rmtree(target)
    partial.rename(target)
    result = {
        "status": "complete",
        "schema_version": SCHEMA_VERSION,
        "cache_key": cache_key,
        "identity": identity,
        "logical_uri": logical_uri,
        "capture_take_id": media["capture_take_id"],
        "source_session_id": media["source_session_id"],
        "camera_role": media["camera_role"],
        "frame_dir": str(target),
        "frame_count": frame_count,
        "duration_ms": int(media["duration_ms"]),
        "frame_naming": "%06d.jpg, 1-based",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (target / "cache.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="远程生成比赛状态 RGB 帧缓存")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--size", type=int, default=224)
    parser.add_argument("--jpeg-quality", type=int, default=3)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--only-session")
    parser.add_argument("--only-camera")
    parser.add_argument("--max-media", type=int)
    args = parser.parse_args()
    if args.fps <= 0 or args.size <= 0 or not 1 <= args.jpeg_quality <= 31:
        raise SystemExit("fps/size 必须为正数，jpeg-quality 必须在 1..31")
    if shutil.which(args.ffmpeg) is None:
        raise SystemExit(f"找不到 ffmpeg: {args.ffmpeg}")
    dataset = load_json(args.dataset_manifest)
    args.output_root.mkdir(parents=True, exist_ok=True)
    index_path = args.output_root / "cache-manifest.json"
    existing: dict[str, dict[str, Any]] = {}
    if index_path.is_file():
        existing_payload = load_json(index_path)
        existing = dict(existing_payload.get("entries", {}))
    selected = list(media_items(dataset, args.only_session, args.only_camera))
    if args.max_media is not None:
        selected = selected[: args.max_media]
    identity = {
        "dataset_manifest_id": dataset.get("manifest_id"),
        "dataset_manifest_sha256": hashlib.sha256(args.dataset_manifest.read_bytes()).hexdigest(),
        "fps": args.fps,
        "size": args.size,
        "jpeg_quality": args.jpeg_quality,
    }
    prepared = []
    for media in selected:
        entry = prepare_media(
            dataset_root=args.dataset_root,
            output_root=args.output_root,
            media=media,
            fps=args.fps,
            size=args.size,
            jpeg_quality=args.jpeg_quality,
            ffmpeg_bin=args.ffmpeg,
        )
        existing[entry["logical_uri"]] = entry
        prepared.append(entry)
        write_index(index_path, existing, identity)
        print(json.dumps({"logical_uri": entry["logical_uri"], "frame_count": entry["frame_count"], "status": entry["status"]}, ensure_ascii=False))
    print(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "selected_media": len(selected),
                "prepared_media": len(prepared),
                "cache_manifest": str(index_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
