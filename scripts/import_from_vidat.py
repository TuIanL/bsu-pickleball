#!/usr/bin/env python3
"""Preview or confirm a Vidat import through the shared application service."""
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
from app.models.live_coding_state import LiveCodingState  # noqa: E402
from app.models.vidat_annotation import VidatAnnotationPackage  # noqa: E402
from app.services.vidat_annotation_service import (  # noqa: E402
    VidatPackageError, confirm_import_preview, create_import_preview,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="预览或确认 Vidat 标注导入")
    parser.add_argument("--package", required=True, help="标注包 ID")
    parser.add_argument("--file", type=Path, help="Vidat annotation JSON")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation-token", help="--apply 必需的预览确认令牌")
    args = parser.parse_args()
    if args.apply and not args.confirmation_token:
        parser.error("--apply 必须提供 --confirmation-token")
    if args.preview and not args.file:
        parser.error("--preview 必须提供 --file")
    annotation = json.loads(args.file.read_text(encoding="utf-8")) if args.file else None
    init_db()
    with get_session_factory()() as db:
        package = db.get(VidatAnnotationPackage, args.package)
        if package is None:
            parser.error("标注包不存在")
        try:
            if args.preview:
                preview = create_import_preview(db, package, annotation)
                db.commit()
                output = {"preview_id": preview.id, "confirmation_token": preview.token,
                          "expires_at": preview.expires_at.isoformat(), **json.loads(preview.preview_json)}
            else:
                audit = confirm_import_preview(db, package, args.confirmation_token, annotation)
                db.commit()
                active = db.get(LiveCodingState, package.capture_take_id)
                output = {
                    "audit_id": audit.id,
                    "source_package_id": audit.package_id,
                    "result_package_id": audit.result_package_id,
                    "active_vidat_package_id": active.active_vidat_package_id if active else None,
                    "operations": json.loads(audit.operations_json),
                }
        except VidatPackageError as exc:
            db.rollback()
            parser.error(str(exc))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
