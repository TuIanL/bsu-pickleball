#!/usr/bin/env python3
"""Create a versioned Vidat package through the application service."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.environ.setdefault("PICKLEBALL_DATA_DIR", str(PROJECT_ROOT / "backend" / "data"))
os.environ.setdefault("PICKLEBALL_DATABASE_PATH", str(PROJECT_ROOT / "backend" / "data" / "app.sqlite3"))

from app.database import get_session_factory, init_db  # noqa: E402
from app.services.vidat_annotation_service import (  # noqa: E402
    VidatPackageError, create_annotation_package, publish_annotation_package,
)


def export_to_vidat(capture_take_id: str, *, copy_video: bool = False,
                    publish_dir: str | None = None, **_legacy_options: object) -> str:
    init_db()
    with get_session_factory()() as db:
        package = create_annotation_package(db, capture_take_id, copy_video=copy_video)
        db.commit()
        db.refresh(package)
        manifest = json.loads(package.manifest_json)
        result = {
            "package_id": package.id, "version": package.version,
            "annotation": str(Path(package.package_dir) / "annotation.json"),
            "video": str(Path(package.package_dir) / manifest["video"]["file"]),
        }
        if publish_dir:
            result["vidat_query"] = publish_annotation_package(package, Path(publish_dir))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result["annotation"]


def main() -> int:
    parser = argparse.ArgumentParser(description="导出版本化 Vidat 标注包")
    parser.add_argument("capture_take_id")
    parser.add_argument("--copy-video", action="store_true", help="显式复制视频（默认使用软链接）")
    parser.add_argument("--publish-dir", help="可选的 Vidat dist 目录")
    args = parser.parse_args()
    try:
        export_to_vidat(args.capture_take_id, copy_video=args.copy_video, publish_dir=args.publish_dir)
    except VidatPackageError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
