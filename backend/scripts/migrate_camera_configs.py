"""Migrate legacy camera JSON files without deleting or renaming sources.

The command is dry-run by default.  ``--apply`` copies only safe IDs into the
configured destination and writes a machine-readable manifest; conflicting or
unsafe records are left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.camera.identifiers import validate_camera_id
from app.core.config import get_settings


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def migrate(source: Path, target: Path, *, apply: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "camera-config-migration.v1",
        "mode": "apply" if apply else "dry-run",
        "source": str(source.resolve()),
        "target": str(target.resolve()),
        "entries": [],
        "summary": {"copied": 0, "already_present": 0, "conflict": 0, "invalid": 0},
    }
    if not source.is_dir():
        return result
    if apply:
        target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("*.json")):
        entry: dict[str, Any] = {"source": str(path), "status": "invalid"}
        try:
            if path.is_symlink():
                raise ValueError("symlink_source")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("config root must be an object")
            camera_id = str(value.get("camera_id") or path.stem)
            validate_camera_id(camera_id)
            if path.stem != camera_id:
                raise ValueError("filename_camera_id_mismatch")
            target_path = target / f"{camera_id}.json"
            if target_path.is_symlink():
                raise ValueError("symlink_target")
            candidate = _canonical(value)
            if target_path.exists():
                existing = json.loads(target_path.read_text(encoding="utf-8"))
                if _canonical(existing) == candidate:
                    entry.update(status="already_present", target=str(target_path))
                    result["summary"]["already_present"] += 1
                else:
                    entry.update(status="conflict", target=str(target_path), reason="different_content")
                    result["summary"]["conflict"] += 1
                result["entries"].append(entry)
                continue
            entry.update(status="copied" if apply else "would_copy", target=str(target_path))
            result["summary"]["copied"] += 1
            if apply:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target, prefix=".camera-migrate-", delete=False) as handle:
                        temporary = Path(handle.name)
                        handle.write(candidate)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.link(temporary, target_path)  # Atomic publish without replacing a concurrent registration.
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            entry["reason"] = str(exc)
            result["summary"]["invalid"] += 1
        result["entries"].append(entry)
    return result


def main() -> int:
    args = _args()
    settings = get_settings()
    source = args.source
    target = args.target or settings.resolved_cameras_dir
    result = migrate(source, target, apply=args.apply)
    manifest = args.manifest
    if manifest is not None or args.apply:
        manifest = manifest or target / "camera-config-migration.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
