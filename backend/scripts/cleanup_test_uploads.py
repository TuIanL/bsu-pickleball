#!/usr/bin/env python3
"""清理 ``backend/data/uploads`` 下的测试 fixture —— 仅移动、不删除。

背景
----
后端 ``backend/tests/test_api_smoke.py`` 通过真实 ``/api/videos/upload`` 接口上传了
大量合成 fixture 视频（96×96 伪视频或 ``b"not-a-real-video"`` 占位字节）。这些文件
写进了**生产目录** ``backend/data/uploads/`` 而非隔离的临时目录，被前端 Library 当成
"比赛视频"展示。本脚本把"疑似 fixture"与真实用户上传分离：

- **候选（将被移出）**：

  - ``source == "upload"`` 且媒体文件缺失；
  - ``source == "upload"`` 且媒体文件体积 ``< --threshold``（默认 512 KB）；
  - ``uploads`` 目录下无对应 ``.json`` 的孤立媒体文件。

- **保留（绝不移动）**：

  - ``source == "recording"`` / ``source == "sync_recording"`` 的合法登记；
  - ``source == "upload"`` 且媒体存在且体积 ``>= 阈值`` 的真实上传。

安全约束（重要）
----------------
- **默认 dry-run**：只打印将要移出 / 保留的条目与计数，**不写盘**；仅当显式传入
  ``--apply`` 才执行移动。
- 移动用 ``shutil.move``（**非 rm**），失败逐条报告、不中断整体。
- 移出物放入 ``<uploads_dir>/.cleanup-trash/<UTC时间戳>/``，并在该目录写
  ``manifest.json``（含每条 id、original_filename、media_size、处置、移出路径）。
- **可回收**：验证 manifest 后，随时可手动清空 ``.cleanup-trash`` 目录。
- **回滚**：若误移，按 manifest 中 ``removed_path`` 将文件移回 ``<uploads_dir>/``
  （保留原 ``.json`` 与媒体同名即可）。

用法
----
    python backend/scripts/cleanup_test_uploads.py                 # dry-run 预览
    python backend/scripts/cleanup_test_uploads.py --apply         # 执行移动
    python backend/scripts/cleanup_test_uploads.py --threshold 262144  # 自定义阈值(字节)
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

# 512 KB：远高于最大 fixture（~25 KB）且远低于真实比赛视频（MB 级），零误删风险。
DEFAULT_THRESHOLD_BYTES = 512 * 1024
# 合法登记来源：真实录制媒体在别处，绝不移动。
KEEP_SOURCES = {"recording", "sync_recording"}


def resolve_uploads_dir(explicit: str | None) -> Path:
    """解析 uploads 目录：显式参数优先，否则按脚本位置推导 ``<repo>/backend/data/uploads``。"""
    if explicit:
        return Path(explicit).expanduser().resolve()
    here = Path(__file__).resolve().parent  # backend/scripts
    return (here.parent / "data" / "uploads").resolve()


def _file_size(path: Path | None) -> int:
    if path is None:
        return 0
    try:
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    return 0


def classify(json_path: Path, uploads_dir: Path, threshold: int) -> dict:
    """判定单个元数据 JSON 的处置。返回含 disposition / media_path / size / reason 的字典。"""
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 无法解析的 JSON：视为孤儿，移除以免污染 catalog。
        return {
            "disposition": "remove",
            "media_path": None,
            "media_size": 0,
            "reason": "unreadable_json",
        }

    video_id = payload.get("id", json_path.stem)
    source = payload.get("source", "upload")
    raw_path = payload.get("path")
    # 直接用 uploads_dir / 文件名定位媒体，避免受 cwd 与相对路径影响。
    media_name = Path(raw_path).name if raw_path else ""
    media_path = (uploads_dir / media_name) if media_name else None
    size = _file_size(media_path)
    exists = media_path is not None and media_path.exists()

    if source in KEEP_SOURCES:
        return {
            "disposition": "keep",
            "media_path": media_path,
            "media_size": size,
            "reason": f"source={source}",
        }

    # 以下为 source == "upload" 或未知：按媒体缺失 / 体积判定。
    if not exists:
        return {
            "disposition": "remove",
            "media_path": media_path,
            "media_size": 0,
            "reason": "media_missing",
        }
    if size < threshold:
        return {
            "disposition": "remove",
            "media_path": media_path,
            "media_size": size,
            "reason": f"media_too_small({size}B<{threshold}B)",
        }
    return {
        "disposition": "keep",
        "media_path": media_path,
        "media_size": size,
        "reason": f"real_upload({size}B>={threshold}B)",
    }


def collect_items(uploads_dir: Path) -> tuple[list[Path], list[Path]]:
    """返回 (metadata_jsons, orphan_media)。幂等：已移入 .cleanup-trash 的文件不参与。"""
    trash_dir = uploads_dir / ".cleanup-trash"
    json_files: list[Path] = []
    media_files: list[Path] = []
    for entry in sorted(uploads_dir.iterdir()):
        if not entry.is_file():
            continue
        if trash_dir in entry.parents or entry.parent == trash_dir:
            continue  # 跳过回收目录本身
        if entry.suffix == ".json":
            json_files.append(entry)
        elif entry.suffix in {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}:
            media_files.append(entry)
    return json_files, media_files


def build_plan(uploads_dir: Path, threshold: int) -> list[dict]:
    """构建处置计划：遍历元数据 JSON 与孤立媒体，产出统一条目列表。"""
    json_files, media_files = collect_items(uploads_dir)
    plan: list[dict] = []

    known_json_stems = {p.stem for p in json_files}
    for json_path in json_files:
        info = classify(json_path, uploads_dir, threshold)
        plan.append(
            {
                "id": json_path.stem,
                "original_filename": _original_filename(json_path),
                "json_path": json_path,
                "media_path": info["media_path"],
                "media_size": info["media_size"],
                "disposition": info["disposition"],
                "reason": info["reason"],
            }
        )

    # 孤立媒体：uploads 目录下没有同名 .json 的视频文件（测试残渣，catalog 看不见但占空间）。
    for media_path in media_files:
        if media_path.stem in known_json_stems:
            continue
        plan.append(
            {
                "id": media_path.stem,
                "original_filename": media_path.name,
                "json_path": None,
                "media_path": media_path,
                "media_size": _file_size(media_path),
                "disposition": "remove",
                "reason": "orphan_media_no_json",
            }
        )
    return plan


def _original_filename(json_path: Path) -> str:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        return payload.get("original_filename", json_path.name)
    except (json.JSONDecodeError, OSError):
        return json_path.name


def _move_item(src: Path, trash_dir: Path) -> str:
    """移动到回收目录，返回目标相对路径字符串；失败抛异常由调用方捕获。"""
    dest = trash_dir / src.name
    # 同名防护：理论上不会冲突（id 唯一），但保险起见追加后缀。
    if dest.exists():
        dest = trash_dir / f"{src.stem}__{datetime.now(UTC).strftime('%f')}{src.suffix}"
    shutil.move(str(src), str(dest))
    return str(dest.relative_to(trash_dir))


def apply_plan(plan: list[dict], uploads_dir: Path, threshold: int) -> dict:
    """执行移动并记录 manifest。逐条失败不中断。返回统计与 manifest 条目。"""
    trash_dir = uploads_dir / ".cleanup-trash" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    trash_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    removed = 0
    kept = 0
    errors = 0

    for item in plan:
        manifest_entry = {
            "id": item["id"],
            "original_filename": item["original_filename"],
            "media_size": item["media_size"],
            "disposition": item["disposition"],
            "reason": item["reason"],
            "removed_path": None,
            "error": None,
        }
        if item["disposition"] == "keep":
            kept += 1
            manifest.append(manifest_entry)
            continue

        # 移动 JSON（若有）与媒体文件。
        moved_targets: list[str] = []
        try:
            if item["json_path"] is not None:
                moved_targets.append(_move_item(item["json_path"], trash_dir))
            if item["media_path"] is not None and item["media_path"].exists():
                moved_targets.append(_move_item(item["media_path"], trash_dir))
            manifest_entry["removed_path"] = ";".join(moved_targets)
            removed += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            manifest_entry["error"] = f"{type(exc).__name__}: {exc}"
        manifest.append(manifest_entry)

    manifest_path = trash_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "uploads_dir": str(uploads_dir),
                "threshold_bytes": threshold,
                "summary": {"removed": removed, "kept": kept, "errors": errors},
                "entries": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"trash_dir": trash_dir, "removed": removed, "kept": kept, "errors": errors, "manifest_path": manifest_path}


def print_plan(plan: list[dict], uploads_dir: Path, apply: bool) -> None:
    removed = [i for i in plan if i["disposition"] == "remove"]
    kept = [i for i in plan if i["disposition"] == "keep"]
    print(f"uploads 目录: {uploads_dir}")
    print(f"模式: {'APPLY（将移动）' if apply else 'DRY-RUN（仅预览，不写盘）'}")
    print(f"评估条目: {len(plan)} | 将移出: {len(removed)} | 保留: {len(kept)}")
    print("\n--- 将移出（fixture / 孤儿媒体）---")
    for item in removed:
        size = item["media_size"]
        print(f"  [{item['id']}] {item['original_filename']}  {size}B  ({item['reason']})")
    print("\n--- 保留（真实上传 / 合法登记）---")
    for item in kept:
        print(f"  [{item['id']}] {item['original_filename']}  {item['media_size']}B  ({item['reason']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="清理 backend/data/uploads 下的测试 fixture（仅移动不删除）。")
    parser.add_argument("--uploads-dir", default=None, help="显式指定 uploads 目录（默认按脚本位置推导）。")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD_BYTES, help="判定 fixture 的体积阈值（字节），默认 524288 (512 KB)。")
    parser.add_argument("--apply", action="store_true", help="执行移动；缺省为 dry-run 仅预览。")
    args = parser.parse_args()

    uploads_dir = resolve_uploads_dir(args.uploads_dir)
    if not uploads_dir.exists():
        print(f"[错误] uploads 目录不存在: {uploads_dir}")
        raise SystemExit(1)

    plan = build_plan(uploads_dir, args.threshold)
    print_plan(plan, uploads_dir, args.apply)

    if not args.apply:
        print("\n（dry-run 结束，未做任何改动。加 --apply 执行移动。）")
        return

    result = apply_plan(plan, uploads_dir, args.threshold)
    print("\n--- 执行结果 ---")
    print(f"移出: {result['removed']} | 保留: {result['kept']} | 错误: {result['errors']}")
    print(f"回收目录: {result['trash_dir']}")
    print(f"清单: {result['manifest_path']}")


if __name__ == "__main__":
    main()
