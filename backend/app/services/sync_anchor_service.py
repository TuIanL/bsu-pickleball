"""CaptureTake-level sync anchor assets, provenance, and preflight policy."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.capture_take import CaptureTake
from app.schemas.sync_anchor import (
    SyncAnchorConfirmRequest,
    SyncAnchorDraftRequest,
    SyncAnchorProvenance,
    SyncAnchorQualitySummary,
    SyncAnchorStatus,
    SyncAnchorValidationIssue,
)
from app.services.capture_storage_service import write_json_atomic
from app.services.dual_camera_sync import (
    build_dual_camera_sync_calibration,
    summarize_frame_timing_sidecar,
)
from app.services.video_service import VideoService

ANCHOR_DRAFT_FILENAME = "sync_anchor_draft.json"
ANCHORS_FILENAME = "sync_anchors.v1.json"
CALIBRATION_FILENAME = "sync_calibration.json"
CONFIRMATION_FILENAME = "sync_anchor_confirmation.json"
HISTORY_DIRNAME = "sync_anchor_history"


class SyncAnchorConflictError(ValueError):
    def __init__(self, current_revision: int):
        super().__init__(f"sync anchor revision conflict; current_revision={current_revision}")
        self.current_revision = current_revision


class SyncAnchorValidationError(ValueError):
    def __init__(self, issues: list[SyncAnchorValidationIssue]):
        super().__init__("sync anchor confirmation validation failed")
        self.issues = issues


class SyncAnchorNotFoundError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _identity(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False}
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


class SyncAnchorAssetService:
    """Own the CaptureTake timeline asset contract used by API and preflight."""

    def __init__(self, db: Session, *, video_service: VideoService | None = None) -> None:
        self.db = db
        self.video_service = video_service or VideoService()

    def _take(self, capture_take_id: str) -> CaptureTake:
        take = self.db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
        if take is None:
            raise SyncAnchorNotFoundError(f"CaptureTake {capture_take_id} 不存在")
        return take

    def _timeline(self, take: CaptureTake) -> Path:
        if not take.session_dir:
            raise SyncAnchorNotFoundError(f"CaptureTake {take.id} 没有可用 session_dir")
        path = Path(take.session_dir).expanduser().resolve(strict=False) / "timeline"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _paths(self, take: CaptureTake) -> dict[str, Path]:
        timeline = self._timeline(take)
        return {
            "draft": timeline / ANCHOR_DRAFT_FILENAME,
            "anchors": timeline / ANCHORS_FILENAME,
            "calibration": timeline / CALIBRATION_FILENAME,
            "confirmation": timeline / CONFIRMATION_FILENAME,
            "history": timeline / HISTORY_DIRNAME,
        }

    def _session_payload(self, take: CaptureTake) -> dict[str, Any]:
        root = Path(take.session_dir or "")
        return _read_json(root / "metadata" / "recording_session.json") or _read_json(root / "manifest.json") or {}

    def _registered_inputs(self, take: CaptureTake) -> list[dict[str, Any]]:
        session = self._session_payload(take)
        registered = (
            session.get("registered_video_ids")
            if isinstance(session.get("registered_video_ids"), dict)
            else {}
        )
        slots = session.get("camera_slots") if isinstance(session.get("camera_slots"), dict) else {}
        result: list[dict[str, Any]] = []
        for slot in ("cam_1", "cam_2"):
            video_id = registered.get(slot)
            slot_payload = slots.get(slot) if isinstance(slots.get(slot), dict) else {}
            camera_id = slot_payload.get("camera_id") or slot
            if not video_id:
                continue
            video = self.video_service.get_video(str(video_id))
            media_path = Path(video.path).expanduser().resolve(strict=False) if video else None
            sidecar = Path(f"{media_path}.pts.jsonl") if media_path is not None else None
            timing: dict[str, Any] = {}
            if video and sidecar is not None and sidecar.is_file():
                try:
                    timing = summarize_frame_timing_sidecar(sidecar, media_path=media_path, require_bound_path=True)
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    timing = {}
            result.append(
                {
                    "capture_take_id": take.id,
                    "slot": slot,
                    "camera_id": str(camera_id),
                    "registered_video_id": str(video_id),
                    "media_identity": _identity(media_path),
                    "timing_sidecar_identity": _identity(sidecar),
                    "timing_authority": str(timing.get("timing_authority", "missing")),
                    "frame_count": timing.get("frame_count"),
                    "first_pts_seconds": timing.get("first_pts_seconds"),
                    "last_pts_seconds": timing.get("last_pts_seconds"),
                }
            )
        return result

    def current_provenance(self, capture_take_id: str) -> list[SyncAnchorProvenance]:
        take = self._take(capture_take_id)
        return [SyncAnchorProvenance.model_validate(item) for item in self._registered_inputs(take)]

    def _load_draft(self, paths: dict[str, Path]) -> dict[str, Any] | None:
        return _read_json(paths["draft"])

    def _current_revision(self, paths: dict[str, Path]) -> int:
        draft = self._load_draft(paths)
        confirmation = _read_json(paths["confirmation"])
        values = [
            int(draft.get("revision", 0)) if draft else 0,
            int(confirmation.get("revision", 0)) if confirmation else 0,
        ]
        return max(values)

    def _draft_model(self, payload: dict[str, Any], revision: int) -> SyncAnchorDraftRequest:
        raw = payload.get("draft") if isinstance(payload.get("draft"), dict) else payload
        raw = dict(raw)
        raw["expected_revision"] = revision
        return SyncAnchorDraftRequest.model_validate(raw)

    def _provenance_matches(self, confirmation: dict[str, Any], current: list[SyncAnchorProvenance]) -> bool:
        saved = confirmation.get("provenance")
        if not isinstance(saved, list):
            return False
        return _fingerprint(saved) == _fingerprint([item.model_dump(mode="json") for item in current])

    @staticmethod
    def _dedupe_issues(issues: list[SyncAnchorValidationIssue]) -> list[SyncAnchorValidationIssue]:
        seen: set[tuple[object, ...]] = set()
        result: list[SyncAnchorValidationIssue] = []
        for issue in issues:
            key = (
                issue.code,
                issue.message,
                issue.field,
                issue.anchor_index,
                issue.camera_id,
            )
            if key not in seen:
                seen.add(key)
                result.append(issue)
        return result

    def _legacy_anchor_payload(self, paths: dict[str, Path], calibration: dict[str, Any]) -> dict[str, Any] | None:
        """Read old anchor locations without treating their existence as confirmation."""
        candidates = [
            paths["anchors"],
            paths["anchors"].with_name("manual_anchors.json"),
            paths["anchors"].with_name("anchors.json"),
            paths["anchors"].with_name("sync_anchors.json"),
        ]
        for path in candidates:
            payload = _read_json(path)
            if payload is not None and isinstance(payload.get("anchors"), list):
                return payload
        if isinstance(calibration.get("anchors"), list):
            return calibration
        return None

    def _try_lazy_migrate_legacy_confirmation(
        self,
        paths: dict[str, Path],
        calibration: dict[str, Any],
        current: list[SyncAnchorProvenance],
    ) -> dict[str, Any] | None:
        """Create confirmation metadata only when an old result proves provenance."""
        if calibration.get("source") != "manual_anchors" or paths["confirmation"].exists():
            return None
        anchor_payload = self._legacy_anchor_payload(paths, calibration)
        if anchor_payload is None:
            return None
        saved_provenance = calibration.get("provenance") or anchor_payload.get("provenance")
        current_dump = [item.model_dump(mode="json") for item in current]
        if not isinstance(saved_provenance, list) or _fingerprint(saved_provenance) != _fingerprint(current_dump):
            return None
        current_camera_ids = {item.camera_id for item in current}
        calibration_camera_ids = {
            str(camera_id)
            for camera_id in (calibration.get("mappings") or {}).keys()
        }
        payload_camera_ids = {str(camera_id) for camera_id in anchor_payload.get("cameras", [])}
        if calibration_camera_ids != current_camera_ids or payload_camera_ids != current_camera_ids:
            return None
        anchors = anchor_payload.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            return None
        revision = int(calibration.get("revision", 0) or 0)
        quality = self._quality(calibration, anchors, current).model_dump(mode="json")
        confirmation = {
            "schema_version": "sync_anchor_confirmation.v1",
            "capture_take_id": current[0].capture_take_id if current else "",
            "revision": revision,
            "source": "manual_anchors",
            "confirmed_at": calibration.get("confirmed_at") or calibration.get("created_at") or _now().isoformat(),
            "provenance": current_dump,
            "provenance_fingerprint": _fingerprint(current_dump),
            "anchors": anchors,
            "quality_summary": quality,
            "migration": "legacy_manual_anchors",
        }
        write_json_atomic(paths["confirmation"], confirmation)
        history = paths["history"] / f"revision-{revision}"
        write_json_atomic(history / paths["confirmation"].name, confirmation)
        return confirmation

    def _quality(
        self,
        calibration: dict[str, Any],
        anchors: list[dict[str, Any]],
        provenance: list[SyncAnchorProvenance],
    ) -> SyncAnchorQualitySummary:
        mappings = calibration.get("mappings") if isinstance(calibration.get("mappings"), dict) else {}
        reference = str(calibration.get("reference_camera", ""))
        reference_mapping = mappings.get(reference) if isinstance(mappings.get(reference), dict) else {}
        residual = []
        for mapping in mappings.values():
            if isinstance(mapping, dict) and mapping.get("residual_rms_ms") is not None:
                residual.append(float(mapping["residual_rms_ms"]))
        reference_input = next((item for item in provenance if item.camera_id == reference), None)
        first = reference_input.first_pts_seconds if reference_input is not None else None
        last = reference_input.last_pts_seconds if reference_input is not None else None
        ref_times = [
            float(row[reference])
            for row in anchors
            if isinstance(row, dict) and row.get(reference) is not None
        ]
        span = max(ref_times) - min(ref_times) if len(ref_times) > 1 else 0.0
        media_span = max(0.0, float(last or 0.0) - float(first or 0.0))
        return SyncAnchorQualitySummary(
            anchor_count=len(anchors),
            coverage_ratio=min(1.0, span / media_span) if media_span > 0 else 0.0,
            residual_rms_ms=max(residual) if residual else None,
            quality=str(reference_mapping.get("quality", "unknown")),
            valid_start_seconds=reference_mapping.get("valid_start_seconds"),
            valid_end_seconds=reference_mapping.get("valid_end_seconds"),
            reason=reference_mapping.get("reason"),
        )

    def status(self, capture_take_id: str, *, require_manual: bool = False) -> SyncAnchorStatus:
        take = self._take(capture_take_id)
        if _enum_value(take.capture_mode) != "dual":
            return SyncAnchorStatus(
                capture_take_id=take.id,
                state="not_required",
                analysis_allowed=True,
                reason_codes=["single_camera_take"],
            )
        paths = self._paths(take)
        current = self.current_provenance(take.id)
        current_dump = [item.model_dump(mode="json") for item in current]
        current_fingerprint = _fingerprint(current_dump)
        draft_payload = self._load_draft(paths)
        confirmation = _read_json(paths["confirmation"])
        calibration = _read_json(paths["calibration"])
        if confirmation is None and calibration is not None:
            confirmation = self._try_lazy_migrate_legacy_confirmation(paths, calibration, current)
        revision = self._current_revision(paths)
        draft = self._draft_model(draft_payload, int(draft_payload.get("revision", 0))) if draft_payload else None

        if confirmation and calibration and self._provenance_matches(confirmation, current):
            source = str(confirmation.get("source", calibration.get("source", "none")))
            if source == "manual_anchors":
                quality = self._quality(calibration, (confirmation.get("anchors") or []), current)
                if quality.quality != "good" or quality.coverage_ratio < 0.5:
                    return SyncAnchorStatus(
                        capture_take_id=take.id,
                        state="invalidated",
                        analysis_allowed=False,
                        reason_codes=["manual_confirmation_quality_insufficient"],
                        source="manual_anchors",
                        revision=revision,
                        quality=quality,
                        provenance=current,
                        provenance_fingerprint=current_fingerprint,
                        confirmed_at=confirmation.get("confirmed_at"),
                        invalidation_reasons=[
                            "manual calibration quality or coverage is below the confirmation threshold"
                        ],
                        draft=draft,
                    )
                return SyncAnchorStatus(
                    capture_take_id=take.id,
                    state="confirmed",
                    analysis_allowed=True,
                    reason_codes=["manual_confirmation_valid"],
                    source="manual_anchors",
                    revision=revision,
                    quality=quality,
                    provenance=current,
                    provenance_fingerprint=current_fingerprint,
                    confirmed_at=confirmation.get("confirmed_at"),
                    draft=draft,
                )
        if calibration and str(calibration.get("source")) == "auto_degraded_from_recording_timing":
            allowed = not require_manual
            return SyncAnchorStatus(
                capture_take_id=take.id,
                state="auto_degraded",
                analysis_allowed=allowed,
                reason_codes=["manual_confirmation_required" if require_manual else "recording_timing_degraded"],
                source="auto_degraded_from_recording_timing",
                revision=revision,
                quality=self._quality(calibration, [], current),
                provenance=current,
                provenance_fingerprint=current_fingerprint,
                draft=draft,
            )
        if confirmation or calibration:
            return SyncAnchorStatus(
                capture_take_id=take.id,
                state="invalidated",
                analysis_allowed=False,
                reason_codes=["provenance_changed", "manual_confirmation_required"],
                source="manual_anchors" if confirmation else "legacy",
                revision=revision,
                provenance=current,
                provenance_fingerprint=current_fingerprint,
                invalidation_reasons=["registered video, camera identity, or timing sidecar changed"],
                draft=draft,
            )
        if draft:
            return SyncAnchorStatus(
                capture_take_id=take.id,
                state="draft",
                analysis_allowed=False if require_manual else False,
                reason_codes=["draft_not_confirmed"],
                source="none",
                revision=revision,
                provenance=current,
                provenance_fingerprint=current_fingerprint,
                draft=draft,
            )
        return SyncAnchorStatus(
            capture_take_id=take.id,
            state="required",
            analysis_allowed=False if require_manual else True,
            reason_codes=["manual_anchors_required" if require_manual else "recording_timing_policy"],
            source="none",
            revision=revision,
            provenance=current,
            provenance_fingerprint=current_fingerprint,
        )

    def save_draft(self, capture_take_id: str, request: SyncAnchorDraftRequest) -> tuple[int, SyncAnchorStatus]:
        take = self._take(capture_take_id)
        paths = self._paths(take)
        current_revision = self._current_revision(paths)
        if request.expected_revision != current_revision:
            raise SyncAnchorConflictError(current_revision)
        provenance = self.current_provenance(capture_take_id)
        revision = current_revision + 1
        payload = {
            "schema_version": "sync_anchor_draft.v1",
            "capture_take_id": capture_take_id,
            "revision": revision,
            "draft": request.model_copy(update={"expected_revision": revision}).model_dump(mode="json"),
            "provenance": [item.model_dump(mode="json") for item in provenance],
            "provenance_fingerprint": _fingerprint([item.model_dump(mode="json") for item in provenance]),
            "saved_at": _now().isoformat(),
        }
        write_json_atomic(paths["draft"], payload)
        return revision, self.status(capture_take_id)

    def confirm(self, capture_take_id: str, request: SyncAnchorConfirmRequest) -> dict[str, Any]:
        take = self._take(capture_take_id)
        paths = self._paths(take)
        current_revision = self._current_revision(paths)
        if request.expected_revision != current_revision:
            raise SyncAnchorConflictError(current_revision)
        provenance = self.current_provenance(capture_take_id)
        export = {
            "reference_camera": request.reference_camera,
            "cameras": request.cameras,
            "anchors": [anchor.pts_by_camera for anchor in request.anchors],
        }
        issues = (
            [
                SyncAnchorValidationIssue(
                    code="camera_identity_missing",
                    message="当前双摄素材 provenance 不完整",
                    field="provenance",
                )
            ]
            if len(provenance) < 2
            else []
        )
        current_camera_ids = {item.camera_id for item in provenance}
        requested_camera_ids = {str(camera_id).strip() for camera_id in request.cameras if str(camera_id).strip()}
        if current_camera_ids != requested_camera_ids:
            issues.append(
                SyncAnchorValidationIssue(
                    code="camera_identity_mismatch",
                    message=(
                        "请求中的 cameras 必须与当前 registered 双摄 camera identity 完全一致"
                    ),
                    field="cameras",
                    camera_id=", ".join(sorted(current_camera_ids ^ requested_camera_ids)) or None,
                )
            )
        if request.reference_camera not in current_camera_ids:
            issues.append(
                SyncAnchorValidationIssue(
                    code="reference_camera_mismatch",
                    message="reference_camera 不属于当前 registered camera identity",
                    field="reference_camera",
                    camera_id=request.reference_camera,
                )
            )
        payload = export | {"capture_take_id": capture_take_id}
        calibration = build_dual_camera_sync_calibration(payload, max_residual_seconds=1 / 30, minimum_anchor_count=3)
        for message in calibration.get("anchor_validation", {}).get("issues", []):
            issues.append(SyncAnchorValidationIssue(code="anchor_validation", message=str(message), field="anchors"))
        mappings = calibration.get("mappings", {})
        if not all(isinstance(value, dict) and value.get("quality") == "good" for value in mappings.values()):
            issues.append(
                SyncAnchorValidationIssue(
                    code="quality_threshold",
                    message="拟合 residual 或覆盖质量未达到确认阈值",
                    field="quality",
                )
            )
        quality = self._quality(calibration, export["anchors"], provenance)
        if quality.coverage_ratio < 0.5:
            issues.append(
                SyncAnchorValidationIssue(
                    code="coverage_threshold",
                    message="锚点参考时间跨度必须覆盖当前素材至少 50%",
                    field="quality.coverage_ratio",
                )
            )
        if issues:
            raise SyncAnchorValidationError(self._dedupe_issues(issues))
        anchor_rows = export["anchors"]
        quality = quality.model_dump(mode="json")
        revision = current_revision
        provenance_dump = [item.model_dump(mode="json") for item in provenance]
        calibration = calibration | {
            "revision": revision,
            "capture_take_id": capture_take_id,
            "provenance": provenance_dump,
            "provenance_fingerprint": _fingerprint(provenance_dump),
            "quality_summary": quality,
        }
        confirmation = {
            "schema_version": "sync_anchor_confirmation.v1",
            "capture_take_id": capture_take_id,
            "revision": revision,
            "source": "manual_anchors",
            "confirmed_at": _now().isoformat(),
            "provenance": provenance_dump,
            "provenance_fingerprint": _fingerprint(provenance_dump),
            "anchors": anchor_rows,
            "quality_summary": quality,
        }
        anchors_payload = {
            "schema_version": "sync_anchors.v1",
            "capture_take_id": capture_take_id,
            "revision": revision,
            "source": "manual_anchors",
            "reference_camera": request.reference_camera,
            "cameras": request.cameras,
            "anchors": anchor_rows,
            "provenance": provenance_dump,
        }
        self._publish_group(paths, revision, anchors_payload, calibration, confirmation)
        return {
            "status": self.status(capture_take_id),
            "calibration": calibration,
            "anchors": export,
        }

    def _publish_group(
        self,
        paths: dict[str, Path],
        revision: int,
        anchors: dict[str, Any],
        calibration: dict[str, Any],
        confirmation: dict[str, Any],
    ) -> None:
        timeline = paths["draft"].parent
        temp_dir = Path(tempfile.mkdtemp(prefix=f".sync-anchor-{revision}-", dir=timeline))
        try:
            files = {
                "anchors": anchors,
                "calibration": calibration,
                "confirmation": confirmation,
            }
            for key, payload in files.items():
                (temp_dir / paths[key].name).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
                )
            history = paths["history"] / f"revision-{revision}"
            history.mkdir(parents=True, exist_ok=True)
            for key, payload in files.items():
                write_json_atomic(history / paths[key].name, payload)
            for key in files:
                os.replace(temp_dir / paths[key].name, paths[key])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def export(self, capture_take_id: str) -> dict[str, Any]:
        take = self._take(capture_take_id)
        paths = self._paths(take)
        anchors = _read_json(paths["anchors"])
        if anchors and isinstance(anchors.get("anchors"), list):
            return {
                "reference_camera": str(anchors.get("reference_camera", "")),
                "cameras": [str(value) for value in anchors.get("cameras", [])],
                "anchors": anchors["anchors"],
            }
        calibration = _read_json(paths["calibration"])
        if calibration and calibration.get("source") == "manual_anchors":
            return {
                "reference_camera": str(calibration.get("reference_camera", "")),
                "cameras": list((calibration.get("mappings") or {}).keys()),
                "anchors": [],
            }
        raise SyncAnchorNotFoundError("当前 CaptureTake 没有可导出的同步锚点")
