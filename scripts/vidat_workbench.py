#!/usr/bin/env python3
"""Versioned Vidat package CLI and local workbench launcher."""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.environ.setdefault("PICKLEBALL_DATA_DIR", str(PROJECT_ROOT / "backend" / "data"))
os.environ.setdefault("PICKLEBALL_DATABASE_PATH", str(PROJECT_ROOT / "backend" / "data" / "app.sqlite3"))

from app.database import get_session_factory, init_db  # noqa: E402
from app.models.capture_take import CaptureTake  # noqa: E402
from app.models.vidat_annotation import VidatAnnotationPackage  # noqa: E402
from app.services.vidat_annotation_service import (  # noqa: E402
    VidatPackageError, create_annotation_package, publish_annotation_package, resolve_primary_video,
)

VIDAT_DIR = Path(os.getenv("PICKLEBALL_VIDAT_DIR", str(Path.home() / "Documents/大学/竞赛/大创/匹克球/摄像头录制/tennistest")))
VIDAT_URL = os.getenv("PICKLEBALL_VIDAT_URL", "http://localhost:8888").rstrip("/")


def list_captures(db) -> list[dict]:
    rows = []
    for take in db.query(CaptureTake).order_by(CaptureTake.started_at.desc()).limit(100):
        try:
            video = str(resolve_primary_video(db, take))
            ready, reason = True, None
        except VidatPackageError as exc:
            video, ready, reason = None, False, str(exc)
        rows.append({"capture_take_id": take.id, "status": take.status.value, "video_ready": ready,
                     "video": video, "disabled_reason": reason})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="匹克球 Vidat 标注工作台")
    parser.add_argument("--list", action="store_true", help="列出 CaptureTake 及视频就绪状态")
    parser.add_argument("--capture-take")
    parser.add_argument("--package", help="打开已有标注包")
    parser.add_argument("--no-launch", action="store_true", help="仅导出/发布，不打开浏览器")
    parser.add_argument("--copy-video", action="store_true")
    args = parser.parse_args()
    init_db()
    with get_session_factory()() as db:
        if args.list:
            print(json.dumps(list_captures(db), ensure_ascii=False, indent=2))
            return 0
        if not args.capture_take and not args.package:
            parser.error("请提供 --capture-take 或 --package")
        package = db.get(VidatAnnotationPackage, args.package) if args.package else None
        if package is None and args.package:
            parser.error("标注包不存在")
        if package is None:
            package = create_annotation_package(db, args.capture_take, copy_video=args.copy_video)
            db.commit(); db.refresh(package)
        dist = Path(os.getenv("PICKLEBALL_VIDAT_DIST", str(VIDAT_DIR / "dist")))
        try:
            query = publish_annotation_package(package, dist)
        except VidatPackageError as exc:
            parser.error(str(exc))
        output = {"package_id": package.id, "version": package.version, "package_dir": package.package_dir,
                  "url": f"{VIDAT_URL}/{query}"}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        if not args.no_launch:
            webbrowser.open(output["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
