#!/usr/bin/env python3
"""Rebase imported dual-camera CaptureTakes onto the remote recordings root."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rebase(value, old: str, new: str):
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [rebase(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: rebase(item, old, new) for key, item in value.items()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--recordings-root", default="/root/autodl-tmp/pre-pickleball/backend/data/recordings")
    args = parser.parse_args()
    root = Path(args.recordings_root).resolve()
    date_root = root / "captures" / args.date
    db_path = root.parent / "app.sqlite3"
    uploads = root.parent / "uploads"
    takes = sorted(path for path in date_root.glob("take_sync_*") if path.is_dir())
    if len(takes) != 7:
        raise SystemExit(f"expected 7 take directories, got {len(takes)}")

    prepared: list[tuple[Path, dict, dict[str, str]]] = []
    for take_dir in takes:
        session_path = take_dir / "metadata" / "recording_session.json"
        session = load_json(session_path)
        take_id = str(session["capture_take_id"])
        registered = session.get("registered_video_ids") or {}
        ids = {slot: str(registered[slot]) for slot in ("cam_1", "cam_2")}
        for slot, camera in (("cam_1", "174"), ("cam_2", "175")):
            media = take_dir / f"{camera}_merged.mp4"
            timing = Path(f"{media}.pts.jsonl")
            if not media.is_file() or not timing.is_file() or media.stat().st_size == 0 or timing.stat().st_size == 0:
                raise SystemExit(f"missing input for {take_dir.name} {slot}")
            if not (uploads / f"{ids[slot]}.json").is_file():
                raise SystemExit(f"missing registered video metadata for {ids[slot]}")
        if not (take_dir / "timeline" / "sync_calibration.json").is_file():
            raise SystemExit(f"missing sync calibration for {take_dir.name}")
        prepared.append((take_dir, session, ids))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for take_dir, session, ids in prepared:
            take_id = str(session["capture_take_id"])
            old_dir = str(session.get("session_dir") or "")
            new_dir = str(take_dir)
            for path in [take_dir / "manifest.json", *(take_dir / "metadata").glob("*.json"), *(take_dir / "timeline").glob("*.json")]:
                payload = load_json(path)
                if old_dir:
                    payload = rebase(payload, old_dir, new_dir)
                write_json(path, payload)
            for slot, camera in (("cam_1", "174"), ("cam_2", "175")):
                meta_path = uploads / f"{ids[slot]}.json"
                metadata = load_json(meta_path)
                media = take_dir / f"{camera}_merged.mp4"
                metadata["path"] = str(media)
                metadata["size_bytes"] = media.stat().st_size
                write_json(meta_path, metadata)
                conn.execute(
                    "UPDATE capture_tracks SET timing_authority=?, timing_sidecar_path=?, timing_failure_reason=NULL WHERE capture_take_id=? AND video_id=?",
                    ("source_pts", f"{media}.pts.jsonl", take_id, ids[slot]),
                )
            conn.execute(
                "UPDATE capture_takes SET session_dir=?, storage_root=?, storage_status='available' WHERE id=?",
                (new_dir, str(root), take_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Use the service after rebasing so identity/stat metadata reflects remote inputs.
    from app.database import get_session_factory
    from app.services.sync_anchor_service import SyncAnchorAssetService, _fingerprint

    session_factory = get_session_factory()
    db = session_factory()
    try:
        service = SyncAnchorAssetService(db)
        for take_dir, session, _ in prepared:
            provenance = [item.model_dump(mode="json") for item in service.current_provenance(str(session["capture_take_id"]))]
            for name in ("sync_anchors.v1.json", "sync_calibration.json", "sync_anchor_confirmation.json"):
                path = take_dir / "timeline" / name
                if path.is_file():
                    payload = load_json(path)
                    payload["provenance"] = provenance
                    payload["provenance_fingerprint"] = _fingerprint(provenance)
                    write_json(path, payload)
    finally:
        db.close()
    print(json.dumps({"prepared_capture_takes": len(prepared), "recordings_root": str(root)}))


if __name__ == "__main__":
    main()
