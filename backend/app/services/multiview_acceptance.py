"""Preparation helpers for auditable multi-camera visual acceptance runs."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.dual_camera_sync import (
    summarize_frame_timing_sidecar,
    write_frame_timing_sidecar,
)


PTS_SIDECAR_SUFFIX = ".pts.jsonl"

# Per-media-path locks serializing sidecar materialization across trigger
# sources (materialize API, startup backfill, merge wrap-up).  The lock key is
# the resolved media path, so two callers addressing the same video through
# different relative/absolute spellings still serialize on one lock.
_TIMING_LOCKS: dict[str, threading.Lock] = {}
_TIMING_LOCKS_GUARD = threading.Lock()


def _timing_lock_for(media_path: str | os.PathLike[str]) -> threading.Lock:
    key = str(Path(media_path).expanduser().resolve(strict=False))
    with _TIMING_LOCKS_GUARD:
        lock = _TIMING_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _TIMING_LOCKS[key] = lock
        return lock


@dataclass(frozen=True)
class TimingPreparationResult:
    slot: str
    media_path: str
    sidecar_path: str
    status: str
    timing_authority: str
    reused: bool = False
    summary: dict[str, object] | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "media_path": self.media_path,
            "sidecar_path": self.sidecar_path,
            "status": self.status,
            "timing_authority": self.timing_authority,
            "reused": self.reused,
            "summary": self.summary,
            "reason": self.reason,
        }


def repair_capture_track_video_indices(
    db: Any,
    capture_take_id: str,
    take_dir: str | os.PathLike[str],
    *,
    video_service: Any | None = None,
    materialize_timing: bool = True,
) -> dict[str, object]:
    """Repair only unambiguous CaptureTrack video/timing metadata.

    The session snapshot is the source of the registered-video relationship.
    Slot order is used only to look up an explicit manifest entry; it is never
    used to guess between multiple candidate files.
    """
    from app.services.capture_track_service import get_tracks_for_take
    from app.services.video_service import VideoService

    root = Path(take_dir).expanduser().resolve(strict=False)
    session_payload = _load_json(root / "metadata" / "recording_session.json")
    manifest_payload = _load_json(root / "manifest.json")
    registered_ids = _extract_registered_video_ids(session_payload) or _extract_registered_video_ids(
        manifest_payload
    )
    slots = _extract_camera_slots(session_payload) or _extract_camera_slots(manifest_payload)
    service = video_service or VideoService()
    tracks = get_tracks_for_take(db, capture_take_id)
    issues: list[str] = []
    staged: list[tuple[Any, str, str, dict[str, object]]] = []
    timing_by_slot: dict[str, dict[str, object]] = {}

    if not registered_ids:
        issues.append("registered_video_ids missing from session metadata and manifest")
    if not tracks:
        issues.append(f"no CaptureTrack found for capture_take_id={capture_take_id}")

    for track in tracks:
        slot = getattr(getattr(track, "slot", None), "value", getattr(track, "slot", ""))
        slot = str(slot)
        expected_video_id = registered_ids.get(slot)
        if not expected_video_id:
            issues.append(f"registered video id missing for slot {slot}")
            continue
        if track.video_id and str(track.video_id) != str(expected_video_id):
            issues.append(
                f"CaptureTrack {track.id} video_id conflict: existing={track.video_id}, "
                f"manifest={expected_video_id}"
            )
            continue
        slot_camera_id = slots.get(slot)
        if slot_camera_id and str(getattr(track, "camera_id", "")) != slot_camera_id:
            issues.append(
                f"CaptureTrack {track.id} camera identity conflict: "
                f"track={track.camera_id}, manifest={slot_camera_id}"
            )
            continue
        video = service.get_available_video(str(expected_video_id))
        if video is None:
            issues.append(f"registered video metadata/file unavailable: {expected_video_id}")
            continue
        media = Path(video.path).expanduser().resolve(strict=False)
        try:
            media.relative_to(root)
        except ValueError:
            issues.append(f"registered video is outside take directory for slot {slot}: {media}")
            continue
        timing = (
            materialize_registered_video_timing(media, slot=slot)
            if materialize_timing
            else TimingPreparationResult(
                slot=slot,
                media_path=str(media),
                sidecar_path=str(timing_sidecar_path(media)),
                status="ready" if timing_sidecar_path(media).exists() else "failed",
                timing_authority="source_pts" if timing_sidecar_path(media).exists() else "missing",
                reason=None if timing_sidecar_path(media).exists() else "timing materialization disabled",
            )
        )
        timing_by_slot[slot] = timing.to_dict()
        if timing.status != "ready" or timing.timing_authority != "source_pts":
            issues.append(f"timing sidecar unavailable for slot {slot}: {timing.reason or 'unknown error'}")
            continue
        staged.append((track, str(expected_video_id), slot, timing.summary or {}))

    if not issues:
        for track, video_id, _slot, summary in staged:
            track.video_id = video_id
            track.timing_authority = "source_pts"
            track.timing_sidecar_path = str(summary.get("sidecar_path"))
            track.timing_failure_reason = None
        db.flush()

    return {
        "schema_version": "capture_track_repair.v1",
        "capture_take_id": capture_take_id,
        "take_dir": str(root),
        "ok": not issues,
        "issues": list(dict.fromkeys(issues)),
        "registered_video_ids": registered_ids,
        "timing_by_slot": timing_by_slot,
        "tracks": [
            {
                    "track_id": track.id,
                    "slot": getattr(getattr(track, "slot", None), "value", str(track.slot)),
                    "video_id": getattr(track, "video_id", None),
                    "timing_authority": getattr(track, "timing_authority", "missing"),
            }
            for track in tracks
        ],
    }


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_registered_video_ids(payload: Mapping[str, object]) -> dict[str, str]:
    direct = payload.get("registered_video_ids")
    if isinstance(direct, dict):
        return {str(slot): str(video_id) for slot, video_id in direct.items() if video_id}
    for value in payload.values():
        if isinstance(value, dict):
            found = _extract_registered_video_ids(value)
            if found:
                return found
    return {}


def _extract_camera_slots(payload: Mapping[str, object]) -> dict[str, str]:
    raw = payload.get("camera_slots")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for slot, value in raw.items():
        if isinstance(value, dict) and value.get("camera_id"):
            result[str(slot)] = str(value["camera_id"])
    return result


def timing_sidecar_path(media_path: str | os.PathLike[str]) -> Path:
    """Return the sidecar path bound to the exact registered media path."""
    return Path(f"{Path(media_path)}{PTS_SIDECAR_SUFFIX}")


def materialize_registered_video_timing(
    media_path: str | os.PathLike[str],
    *,
    slot: str = "",
    sidecar_path: str | os.PathLike[str] | None = None,
    ffprobe_bin: str = "ffprobe",
) -> TimingPreparationResult:
    """Materialize or reuse a registered-video PTS sidecar without fallback.

    Concurrent callers addressing the same media are serialized by a
    per-media-path lock so a heavy ffprobe extraction never runs twice; once a
    winner writes the sidecar atomically, everyone else takes the reuse path.
    """
    with _timing_lock_for(media_path):
        return _materialize_registered_video_timing_unlocked(
            media_path,
            slot=slot,
            sidecar_path=sidecar_path,
            ffprobe_bin=ffprobe_bin,
        )


def _materialize_registered_video_timing_unlocked(
    media_path: str | os.PathLike[str],
    *,
    slot: str = "",
    sidecar_path: str | os.PathLike[str] | None = None,
    ffprobe_bin: str = "ffprobe",
) -> TimingPreparationResult:
    """Materialize or reuse a registered-video PTS sidecar without fallback."""
    media = Path(media_path).expanduser().resolve(strict=False)
    sidecar = Path(sidecar_path) if sidecar_path is not None else timing_sidecar_path(media)
    if not media.is_file() or media.stat().st_size <= 0:
        return TimingPreparationResult(
            slot=slot,
            media_path=str(media),
            sidecar_path=str(sidecar),
            status="failed",
            timing_authority="missing",
            reason="registered video is missing or empty",
        )
    if sidecar.exists():
        try:
            summary = summarize_frame_timing_sidecar(
                sidecar,
                media_path=media,
                require_bound_path=True,
            )
            return TimingPreparationResult(
                slot=slot,
                media_path=str(media),
                sidecar_path=str(sidecar),
                status="ready",
                timing_authority="source_pts",
                reused=True,
                summary=summary,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            # An invalid sidecar is never promoted to authority.  Rebuild it
            # from the registered media using the existing atomic writer.
            invalid_reason = str(exc)
    else:
        invalid_reason = None
    try:
        summary = write_frame_timing_sidecar(media, sidecar, ffprobe_bin=ffprobe_bin)
        summary = summarize_frame_timing_sidecar(
            sidecar,
            media_path=media,
            require_bound_path=True,
        )
        if invalid_reason:
            summary["replaced_invalid_sidecar"] = invalid_reason
        return TimingPreparationResult(
            slot=slot,
            media_path=str(media),
            sidecar_path=str(sidecar),
            status="ready",
            timing_authority="source_pts",
            summary=summary,
        )
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return TimingPreparationResult(
            slot=slot,
            media_path=str(media),
            sidecar_path=str(sidecar),
            status="failed",
            timing_authority="missing",
            reason=str(exc),
        )


def prepare_take_timing(
    take_dir: str | os.PathLike[str],
    *,
    video_paths: Mapping[str, str | os.PathLike[str]] | None = None,
    output_path: str | os.PathLike[str] | None = None,
    ffprobe_bin: str = "ffprobe",
) -> dict[str, object]:
    """Prepare all explicitly supplied registered videos for one CaptureTake."""
    root = Path(take_dir).expanduser().resolve(strict=False)
    paths = dict(video_paths or {})
    if not paths:
        discovered = sorted(root.glob("*_merged.mp4"))
        paths = {f"video_{index + 1}": path for index, path in enumerate(discovered)}
    results = [
        materialize_registered_video_timing(path, slot=slot, ffprobe_bin=ffprobe_bin)
        for slot, path in paths.items()
    ]
    payload: dict[str, object] = {
        "schema_version": "multiview_timing_preparation.v1",
        "take_dir": str(root),
        "timing_authority": "source_pts" if results and all(
            item.timing_authority == "source_pts" for item in results
        ) else "missing",
        "status": "ready" if results and all(item.status == "ready" for item in results) else "failed",
        "videos": [item.to_dict() for item in results],
    }
    if output_path is not None:
        _write_json_atomic(Path(output_path), payload)
    return payload


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".part", delete=False
    ) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
