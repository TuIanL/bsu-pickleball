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
    VidatPackageError, compare_annotation_packages, create_annotation_package,
    derive_annotation_package, logical_delete_annotation_package, package_display_name,
    publish_annotation_package, purge_annotation_package, resolve_primary_video,
    update_annotation_package,
)
from app.services.vidat_server import VidatServiceError, get_vidat_service_status, stop_vidat_service  # noqa: E402

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


def package_summary(package: VidatAnnotationPackage) -> dict:
    return {
        "package_id": package.id,
        "capture_take_id": package.capture_take_id,
        "version": package.version,
        "name": package_display_name(package),
        "owner": package.owner,
        "note": package.note,
        "provenance": package.provenance or "generated",
        "source_package_id": package.source_package_id,
        "created_at": package.created_at.isoformat() if package.created_at else None,
        "imported_at": package.imported_at.isoformat() if package.imported_at else None,
        "deleted_at": package.deleted_at.isoformat() if package.deleted_at else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="匹克球 Vidat 标注工作台")
    parser.add_argument("--list", action="store_true", help="列出 CaptureTake 及视频就绪状态")
    parser.add_argument("--capture-take")
    parser.add_argument("--package", help="打开已有标注包")
    parser.add_argument("--derive-from", metavar="PACKAGE_ID", help="从指定版本派生新包")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="比较两个版本")
    parser.add_argument("--delete", action="store_true", help="逻辑删除 --package")
    parser.add_argument("--purge", action="store_true", help="永久清理 --package（受后端保护）")
    parser.add_argument("--status", action="store_true", help="查询 Vidat 服务状态")
    parser.add_argument("--stop", action="store_true", help="停止受控 Vidat 服务")
    parser.add_argument("--name", help="新版本名称")
    parser.add_argument("--owner", help="负责人或分工人")
    parser.add_argument("--note", help="版本备注")
    parser.add_argument("--no-launch", action="store_true", help="仅导出/发布，不打开浏览器")
    parser.add_argument("--copy-video", action="store_true")
    args = parser.parse_args()
    if args.status or args.stop:
        try:
            output = stop_vidat_service() if args.stop else get_vidat_service_status()
        except VidatServiceError as exc:
            parser.error(str(exc))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    init_db()
    with get_session_factory()() as db:
        if args.list:
            print(json.dumps(list_captures(db), ensure_ascii=False, indent=2))
            return 0
        if args.compare:
            first = db.get(VidatAnnotationPackage, args.compare[0])
            second = db.get(VidatAnnotationPackage, args.compare[1])
            if first is None or second is None:
                parser.error("比较的标注包不存在")
            try:
                output = compare_annotation_packages(db, first, second)
            except VidatPackageError as exc:
                parser.error(str(exc))
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        if not args.capture_take and not args.package:
            if not args.derive_from:
                parser.error("请提供 --capture-take、--package 或 --derive-from")
        package = db.get(VidatAnnotationPackage, args.package) if args.package else None
        if package is None and args.package:
            parser.error("标注包不存在")
        if args.derive_from:
            source = db.get(VidatAnnotationPackage, args.derive_from)
            if source is None:
                parser.error("派生来源标注包不存在")
            try:
                package = derive_annotation_package(
                    db, source, name=args.name, owner=args.owner, note=args.note
                )
                db.commit()
                db.refresh(package)
            except VidatPackageError as exc:
                db.rollback()
                parser.error(str(exc))

        if package is not None and (args.delete or args.purge):
            try:
                if args.purge:
                    purge_annotation_package(db, package)
                    db.commit()
                    output = {"package_id": package.id, "purged": True}
                else:
                    logical_delete_annotation_package(db, package)
                    db.commit()
                    db.refresh(package)
                    output = package_summary(package)
            except VidatPackageError as exc:
                db.rollback()
                parser.error(str(exc))
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

        if package is None:
            package = create_annotation_package(
                db,
                args.capture_take,
                copy_video=args.copy_video,
                name=args.name,
                owner=args.owner,
                note=args.note,
            )
            db.commit(); db.refresh(package)
        dist = Path(os.getenv("PICKLEBALL_VIDAT_DIST", str(VIDAT_DIR / "dist")))
        try:
            query = publish_annotation_package(package, dist)
        except VidatPackageError as exc:
            parser.error(str(exc))
        output = {
            **package_summary(package),
            "package_dir": package.package_dir,
            "url": f"{VIDAT_URL}/{query}",
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        if not args.no_launch:
            webbrowser.open(output["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
