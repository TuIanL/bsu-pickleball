"""Product observability projection for multiview analysis jobs.

This module is deliberately read-only with respect to analysis semantics. It
composes published artifacts and preserves their decisions; it never reads the
raw joint trace or re-runs an authority/safety threshold.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from app.schemas.analysis import AnalysisJobSummary
from app.services.mock_analysis import get_mock_job, get_pipeline_result
from app.services.storage_service import StorageService

AVAILABILITIES = {"available", "partial", "unavailable", "not_applicable"}
EPISODE_OUTCOMES = {
    "guided_recovery_success",
    "base_recovered",
    "guidance_failed",
    "pre_gate_rejected",
    "lock_rejected",
    "global_mismatch",
}


def build_recovery_episode_projection(trace: dict[str, Any]) -> dict[str, Any]:
    """Reduce in-memory joint debug evidence to one row per recovery episode.

    This function is called by the executor while the run already owns its
    evidence. The request-time projector only reads the resulting small JSON.
    """
    episodes: dict[str, dict[str, Any]] = {}
    ticks = trace.get("ticks") if isinstance(trace.get("ticks"), list) else []
    for tick in ticks:
        if not isinstance(tick, dict):
            continue
        timestamp = float(tick.get("canonical_timestamp_ms", 0.0) or 0.0)
        tick_recovery = tick.get("recovery") if isinstance(tick.get("recovery"), dict) else {}
        guidance_rows: list[dict[str, Any]] = []
        views = tick.get("views") if isinstance(tick.get("views"), dict) else {}
        for view_id, view in views.items():
            if not isinstance(view, dict):
                continue
            guidance = view.get("guidance") if isinstance(view.get("guidance"), list) else []
            for item in guidance:
                if isinstance(item, dict) and item.get("recovery_episode_id"):
                    guidance_rows.append({**item, "target_view": item.get("target_view") or view_id})
        observations = tick.get("canonical_observations") if isinstance(tick.get("canonical_observations"), list) else []
        for guidance in guidance_rows:
            episode_id = str(guidance["recovery_episode_id"])
            item = episodes.setdefault(
                episode_id,
                {
                    "recovery_episode_id": episode_id,
                    "start_ms": timestamp,
                    "end_ms": timestamp,
                    "global_player_id": guidance.get("global_player_id"),
                    "donor_view": guidance.get("donor_view"),
                    "target_view": guidance.get("target_view"),
                    "guidance_attempts": 0,
                    "pre_gate_rejections": 0,
                    "lock_rejections": 0,
                    "outcome": "guidance_failed",
                    "debug_video_seek_ms": timestamp,
                    "closed": False,
                },
            )
            if item.get("closed"):
                continue
            item["start_ms"] = min(float(item["start_ms"]), timestamp)
            item["end_ms"] = max(float(item["end_ms"]), timestamp)
            item["guidance_attempts"] += 1
            item["pre_gate_rejections"] += int(tick_recovery.get("guided_pre_gate_rejected_count", 0) or 0)
            item["lock_rejections"] += int(tick_recovery.get("guided_lock_rejected_count", 0) or 0)
            target = item.get("target_view")
            gid = item.get("global_player_id")
            matching = [
                row for row in observations
                if isinstance(row, dict)
                and row.get("global_player_id") == gid
                and row.get("view_id") == target
            ]
            mismatch = [
                row for row in observations
                if isinstance(row, dict)
                and row.get("view_id") == target
                and row.get("detection_origin") == "guided_roi"
                and row.get("expected_global_player_id") == gid
                and row.get("global_player_id") != gid
            ]
            if any(row.get("detection_origin") == "base" for row in matching):
                item["outcome"] = "base_recovered"
                item["closed"] = True
            elif any(
                row.get("detection_origin") == "guided_roi"
                and row.get("expected_global_player_id") == gid
                for row in matching
            ):
                    item["outcome"] = "guided_recovery_success"
                    item["closed"] = True
            elif mismatch:
                item["outcome"] = "global_mismatch"
                item["closed"] = True

        # A formal base/guided assignment may close an existing episode on a
        # tick that emits no new guidance row. Preserve that terminal evidence.
        for item in episodes.values():
            if item.get("closed") or item.get("global_player_id") is None or item.get("target_view") is None:
                continue
            matching = [
                row for row in observations
                if isinstance(row, dict)
                and row.get("global_player_id") == item.get("global_player_id")
                and row.get("view_id") == item.get("target_view")
            ]
            if any(row.get("detection_origin") == "base" for row in matching):
                item["outcome"] = "base_recovered"
                item["end_ms"] = max(float(item["end_ms"]), timestamp)
                item["closed"] = True
            elif any(
                row.get("detection_origin") == "guided_roi"
                and row.get("expected_global_player_id") == item.get("global_player_id")
                for row in matching
            ):
                item["outcome"] = "guided_recovery_success"
                item["end_ms"] = max(float(item["end_ms"]), timestamp)
                item["closed"] = True
            else:
                mismatch = any(
                    row.get("detection_origin") == "guided_roi"
                    and row.get("expected_global_player_id") == item.get("global_player_id")
                    and row.get("global_player_id") != item.get("global_player_id")
                    and row.get("view_id") == item.get("target_view")
                    for row in observations
                )
                if mismatch:
                    item["outcome"] = "global_mismatch"
                    item["end_ms"] = max(float(item["end_ms"]), timestamp)
                    item["closed"] = True

    # Preserve explicit failure evidence when an episode emitted a guidance
    # rejection but did not produce a formal target observation.
    for item in episodes.values():
        if item["outcome"] == "guidance_failed":
            if item["lock_rejections"]:
                item["outcome"] = "lock_rejected"
            elif item["pre_gate_rejections"]:
                item["outcome"] = "pre_gate_rejected"
            elif not item["guidance_attempts"]:
                item["outcome"] = "global_mismatch"
        item.pop("closed", None)
    return {
        "schema_version": "recovery_episodes.v1",
        "run_id": trace.get("run_id"),
        "capture_take_id": trace.get("capture_take_id"),
        "episodes": sorted(episodes.values(), key=lambda item: (item["start_ms"], item["recovery_episode_id"])),
    }


class MultiviewNotApplicableError(Exception):
    """Raised when a resource is requested for a non-multiview job."""


def structured_error(code: str, message: str, *, job_id: str | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **({"job_id": job_id} if job_id else {})}}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _first(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _section(availability: str, status: str, payload: dict[str, Any] | None = None, *, reason_code: str | None = None) -> dict[str, Any]:
    if availability not in AVAILABILITIES:
        raise ValueError(f"unknown observability availability: {availability}")
    result: dict[str, Any] = {"availability": availability, "status": status}
    if reason_code:
        result["reason_code"] = reason_code
    if payload:
        result["data"] = payload
    return result


def _public_timing_provenance(value: Any) -> dict[str, dict[str, Any]] | None:
    """Expose timing facts without leaking local media or sidecar paths."""
    if not isinstance(value, dict):
        return None
    allowed = {
        "schema_version",
        "authority",
        "reason",
        "frame_count",
        "fps",
        "first_pts_seconds",
        "last_pts_seconds",
        "duration_seconds",
    }
    return {
        str(view_id): {key: item[key] for key in allowed if key in item}
        for view_id, item in value.items()
        if isinstance(item, dict)
    }


def _run_id(
    job: AnalysisJobSummary,
    manifest: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> str | None:
    return _first(
        getattr(job, "jointRunId", None),
        getattr(job, "fusionRunId", None),
        (manifest or {}).get("run_id"),
        (manifest or {}).get("fusion_run_id"),
        (diagnostics or {}).get("run_id"),
    )


def _mode(
    job: AnalysisJobSummary,
    manifest: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> str:
    return str(_first(
        (result or {}).get("execution_mode"),
        (manifest or {}).get("execution_mode"),
        (diagnostics or {}).get("execution_mode"),
        getattr(job, "executionMode", None),
        "late_fusion_v1",
    ))


def _effective_mode(manifest: dict[str, Any] | None, result: dict[str, Any] | None, diagnostics: dict[str, Any] | None) -> str | None:
    return _first(
        (result or {}).get("effective_multiview_mode"),
        (manifest or {}).get("effective_mode"),
        (diagnostics or {}).get("effective_mode"),
        (manifest or {}).get("analysis_source", {}).get("mode") if isinstance((manifest or {}).get("analysis_source"), dict) else None,
    )


class RecoveryEpisodeProjector:
    """Read and filter the small, backend-owned recovery episode artifact."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    @staticmethod
    def _cursor_payload(cursor: str | None) -> dict[str, Any]:
        if not cursor:
            return {"offset": 0}
        try:
            decoded = base64.urlsafe_b64decode(cursor.encode("ascii") + b"===")
            payload = json.loads(decoded.decode("utf-8"))
            return payload if isinstance(payload, dict) else {"offset": 0}
        except (ValueError, UnicodeError, json.JSONDecodeError):
            raise ValueError("invalid recovery episode cursor") from None

    @staticmethod
    def _encode_cursor(offset: int, fingerprint: str) -> str:
        raw = json.dumps({"offset": offset, "fingerprint": fingerprint}, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _fingerprint(filters: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(filters, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]

    def list_episodes(
        self,
        *,
        job: AnalysisJobSummary,
        run_id: str | None,
        cursor: str | None = None,
        limit: int = 25,
        outcome: str | None = None,
        global_player_id: str | None = None,
        donor_view: str | None = None,
        target_view: str | None = None,
        from_ms: float | None = None,
        to_ms: float | None = None,
    ) -> dict[str, Any]:
        filters = {
            "outcome": outcome,
            "global_player_id": global_player_id,
            "donor_view": donor_view,
            "target_view": target_view,
            "from_ms": from_ms,
            "to_ms": to_ms,
        }
        fingerprint = self._fingerprint(filters)
        if outcome and outcome not in EPISODE_OUTCOMES:
            return {"items": [], "next_cursor": None, "total_estimate": 0, "availability": "partial", "reason": {"code": "unknown_outcome", "message": "Unknown recovery episode outcome."}}
        if not run_id:
            return {"items": [], "next_cursor": None, "total_estimate": 0, "availability": "unavailable", "reason": {"code": "run_identity_missing", "message": "No published multiview run identity is available."}}
        path = self.storage.recovery_episodes_json_path(job.id, run_id)
        payload = _read_json(path)
        if payload is None:
            return {"items": [], "next_cursor": None, "total_estimate": 0, "availability": "partial", "reason": {"code": "episode_evidence_unavailable", "message": "This task has funnel diagnostics but no published recovery episode evidence."}}
        raw_items = payload.get("episodes")
        if not isinstance(raw_items, list):
            return {"items": [], "next_cursor": None, "total_estimate": 0, "availability": "partial", "reason": {"code": "episode_artifact_invalid", "message": "Recovery episode evidence is incomplete."}}
        items = [item for item in raw_items if isinstance(item, dict)]
        items.sort(key=lambda item: (float(item.get("start_ms", 0.0) or 0.0), str(item.get("recovery_episode_id", ""))))

        def matches(item: dict[str, Any]) -> bool:
            if outcome and item.get("outcome") != outcome:
                return False
            if global_player_id and str(item.get("global_player_id")) != global_player_id:
                return False
            if donor_view and item.get("donor_view") != donor_view:
                return False
            if target_view and item.get("target_view") != target_view:
                return False
            start = float(item.get("start_ms", 0.0) or 0.0)
            end = float(item.get("end_ms", start) or start)
            if from_ms is not None and end < from_ms:
                return False
            if to_ms is not None and start > to_ms:
                return False
            return True

        filtered = [item for item in items if matches(item)]
        try:
            cursor_payload = self._cursor_payload(cursor)
        except ValueError:
            return {"items": [], "next_cursor": None, "total_estimate": len(filtered), "availability": "partial", "reason": {"code": "invalid_cursor", "message": "The recovery episode cursor is invalid or expired."}}
        if cursor_payload.get("fingerprint") not in (None, fingerprint):
            return {"items": [], "next_cursor": None, "total_estimate": len(filtered), "availability": "partial", "reason": {"code": "cursor_filter_mismatch", "message": "The cursor does not match the requested filters."}}
        raw_offset = cursor_payload.get("offset", 0)
        if isinstance(raw_offset, bool) or not isinstance(raw_offset, (int, float, str)):
            return {"items": [], "next_cursor": None, "total_estimate": len(filtered), "availability": "partial", "reason": {"code": "invalid_cursor", "message": "The recovery episode cursor is invalid or expired."}}
        try:
            offset = max(0, int(raw_offset))
        except (TypeError, ValueError, OverflowError):
            return {"items": [], "next_cursor": None, "total_estimate": len(filtered), "availability": "partial", "reason": {"code": "invalid_cursor", "message": "The recovery episode cursor is invalid or expired."}}
        page_size = max(1, min(int(limit), 100))
        page = filtered[offset : offset + page_size]
        next_cursor = self._encode_cursor(offset + page_size, fingerprint) if offset + page_size < len(filtered) else None
        return {"items": page, "next_cursor": next_cursor, "total_estimate": len(filtered), "availability": "available"}


class MultiviewObservabilityProjector:
    """Compose the public observability summary from published small artifacts."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()
        self.episodes = RecoveryEpisodeProjector(self.storage)

    def _paths(self, job: AnalysisJobSummary, run_id: str | None) -> tuple[Path | None, Path | None]:
        if not run_id:
            return None, None
        run_dir = self.storage.multiview_run_dir(job.id, run_id)
        return run_dir, self.storage.joint_debug_summary_json_path(job.id, run_id)

    @staticmethod
    def _run_child(run_dir: Path | None, name: Any, default: str | None = None) -> Path | None:
        if run_dir is None:
            return None
        candidate_name = str(name or default or "")
        candidate = run_dir / candidate_name
        try:
            if Path(candidate_name).name != candidate_name or candidate.resolve().parent != run_dir.resolve():
                return None
        except OSError:
            return None
        return candidate

    def project(self, job: AnalysisJobSummary, result: Any | None = None) -> dict[str, Any]:
        if job.analysisKind != "multiview":
            raise MultiviewNotApplicableError
        result_payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else (result or {})
        manifest = _read_json(self.storage.fusion_manifest_json_path(job.id))
        diagnostics = _read_json(self.storage.fusion_diagnostics_json_path(job.id))
        run_id = _run_id(job, manifest, diagnostics)
        run_dir, debug_summary_path = self._paths(job, run_id)
        debug_summary = _read_json(debug_summary_path) if debug_summary_path else None
        mode = _mode(job, manifest, diagnostics, result_payload)
        effective_mode = _effective_mode(manifest, result_payload, diagnostics)

        timing_source = diagnostics or {}
        authority_by_view = _first(timing_source.get("timing_authority_by_view"), (debug_summary or {}).get("authority", {}).get("timing_authority_by_view"))
        timing_provenance = _public_timing_provenance(timing_source.get("timing_provenance"))
        timing_present = bool(authority_by_view or timing_provenance or timing_source.get("sync_quality") or timing_source.get("authoritative_joint_eligible") is not None)
        timing_data = {
            "reference_view": _first(timing_source.get("reference_view_id"), manifest.get("reference_view_id") if manifest else None, getattr(job, "referenceViewId", None)),
            "per_view_authority": authority_by_view,
            "timing_provenance": timing_provenance,
            "sync_quality": _first(timing_source.get("sync_quality"), (debug_summary or {}).get("authority", {}).get("sync_quality")),
            "execution_mode": mode,
            "authoritative_joint_eligible": _first(timing_source.get("authoritative_joint_eligible"), result_payload.get("authoritative_joint_eligible"), (debug_summary or {}).get("authority", {}).get("authoritative_joint_eligible")),
            "authority_reason": _first(timing_source.get("authority_reason"), manifest.get("authority_reason") if manifest else None),
            "authority_reason_codes": timing_source.get("authority_reason_codes"),
            "selection_error": _first(timing_source.get("selection_error"), timing_source.get("frame_mapping_errors")),
            "frame_selection_status": _first(timing_source.get("frame_status_counts"), timing_source.get("pairing_plan")),
        }
        if not timing_present:
            sync = _section("unavailable", "diagnostics_missing", reason_code="timing_diagnostics_missing")
        else:
            sync_availability = "available" if authority_by_view and timing_data["sync_quality"] else "partial"
            sync_status = "authoritative" if timing_data["authoritative_joint_eligible"] is True else ("degraded" if mode == "joint_tracking_v2" else mode)
            sync = _section(sync_availability, sync_status, timing_data, reason_code=None if sync_availability == "available" else "timing_fields_incomplete")

        counts = diagnostics.get("fusion_status_counts") if diagnostics else None
        fusion_data = {
            "status_counts": counts,
            "sample_count": diagnostics.get("sample_count") if diagnostics else None,
            "metric_eligible_count": diagnostics.get("metric_eligible_count") if diagnostics else None,
            "view_disagreement": diagnostics.get("view_disagreement") if diagnostics else None,
            "effective_multiview_ratio": _first((diagnostics or {}).get("effective_multiview_ratio"), (manifest or {}).get("effective_multiview_ratio")),
        }
        if mode == "late_fusion_v1" and not diagnostics and not manifest:
            fusion = _section("not_applicable", "late_fusion", reason_code="late_fusion_diagnostics_missing")
        elif not counts and not diagnostics:
            fusion = _section("unavailable", "diagnostics_missing", reason_code="fusion_diagnostics_missing")
        else:
            fusion = _section("available" if counts else "partial", "completed" if counts else "partial", fusion_data, reason_code=None if counts else "fusion_counts_missing")

        funnel = (diagnostics or {}).get("recovery_funnel")
        if mode == "late_fusion_v1":
            recovery = _section("not_applicable", "not_applicable", {"funnel": None, "episode_availability": "not_applicable"}, reason_code="late_fusion_recovery_not_applicable")
        elif not isinstance(funnel, dict):
            recovery = _section("unavailable", "diagnostics_missing", {"funnel": None, "episode_availability": "unavailable"}, reason_code="recovery_funnel_missing")
        else:
            episode_path = self.storage.recovery_episodes_json_path(job.id, run_id) if run_id else None
            has_episode_artifact = bool(episode_path and episode_path.is_file())
            recovery_data = {
                "funnel": funnel,
                "episode_availability": "available" if has_episode_artifact else "partial",
                "episode_reason": None if has_episode_artifact else {"code": "episode_evidence_unavailable", "message": "当前任务只有正式漏斗，没有可分页 episode 证据。"},
            }
            recovery = _section("available" if has_episode_artifact else "partial", "completed", recovery_data, reason_code=None if has_episode_artifact else "episode_evidence_unavailable")

        refinement = (manifest or {}).get("refinement")
        refinement_diag_path = self._run_child(run_dir, (refinement or {}).get("diagnostics_artifact"), "refinement_diagnostics.json")
        refinement_diag = _read_json(refinement_diag_path) if refinement_diag_path else None
        if mode == "late_fusion_v1":
            refinement_section = _section("not_applicable", "not_applicable", {"status": "not_applicable", "final_source": None}, reason_code="late_fusion_refinement_not_applicable")
        elif not isinstance(refinement, dict):
            refinement_section = _section("unavailable", "diagnostics_missing", reason_code="refinement_manifest_missing")
        else:
            candidate_name = refinement.get("refined_artifact") or "fused_player_trajectory.f1.v2.json"
            candidate_path = self._run_child(run_dir, candidate_name)
            candidate_available = bool(candidate_path and candidate_path.is_file())
            status = str(refinement.get("status", "unknown"))
            execution_status = "completed" if status == "rejected_by_safety_gate" else status
            publication_decision = "rejected_by_safety_gate" if status == "rejected_by_safety_gate" else (
                "passed" if status == "completed" and refinement.get("final_source") == "refined_f1" else status
            )
            refinement_data = {
                "execution_status": execution_status,
                "candidate_f1": {"available": candidate_available, "artifact": str(candidate_name) if candidate_available else None},
                "publication_decision": publication_decision,
                "safety_gate": {"reason": refinement.get("reason") or (refinement_diag or {}).get("reason"), "metrics": {key: value for key, value in (refinement_diag or {}).items() if key not in {"schema_version", "status", "final_source", "reason"}}},
                "final_source": refinement.get("final_source"),
            }
            refinement_section = _section("available", status, refinement_data)

        debug_video = self.resolve_debug_video(job, run_id)
        public_debug_summary = self._public_debug_summary(debug_summary)
        if not getattr(job, "debugTraceEnabled", False):
            debug = _section("unavailable", "disabled", {"debug_trace_enabled": False, "video_available": False}, reason_code="debug_trace_disabled")
        elif debug_video:
            debug = _section("available", "ready", {"debug_trace_enabled": True, "video_available": True, "video_filename": debug_video.name, "summary": public_debug_summary})
        else:
            debug = _section("unavailable", "video_missing", {"debug_trace_enabled": True, "video_available": False, "summary": public_debug_summary}, reason_code="canonical_debug_video_missing")

        sections = {"sync": sync, "fusion": fusion, "recovery": recovery, "refinement": refinement_section, "debug": debug}
        return {
            "schema_version": "multiview_observability_summary.v1",
            "job_id": job.id,
            "run_id": run_id,
            "analysis_kind": job.analysisKind,
            "requested_mode": getattr(job, "executionMode", None),
            "execution_mode": mode,
            "effective_mode": effective_mode,
            "sections": sections,
            "sync": sync,
            "fusion": fusion,
            "recovery": recovery,
            "refinement": refinement_section,
            "debug": debug,
        }

    @staticmethod
    def _public_debug_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
        """Keep renderer facts public without returning local paths or trace metadata."""
        if not summary:
            return None
        allowed = {
            "rendered_tick_count",
            "trace_tick_count",
            "recovery_funnel",
            "recovery_evidence",
            "natural_recovery_opportunity_zero",
            "decode_errors",
            "authority",
        }
        public = {key: summary[key] for key in allowed if key in summary}
        authority = public.get("authority")
        if isinstance(authority, dict):
            public["authority"] = {
                key: authority[key]
                for key in {"execution_mode", "sync_quality", "authoritative_joint_eligible", "timing_authority_by_view"}
                if key in authority
            }
        return public

    def resolve_debug_video(self, job: AnalysisJobSummary, run_id: str | None) -> Path | None:
        if job.analysisKind != "multiview" or not run_id or not getattr(job, "debugTraceEnabled", False):
            return None
        run_dir = self.storage.multiview_run_dir(job.id, run_id).resolve()
        candidates = [
            run_dir / "canonical_debug.mp4",
            run_dir / "joint_debug_acceptance.mp4",
            run_dir / "joint_debug.mp4",
            run_dir / "debug_video.mp4",
        ]
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.resolve().parent == run_dir:
                    return candidate
            except OSError:
                continue
        return None


def get_multiview_job_or_raise(job_id: str) -> AnalysisJobSummary:
    job = get_mock_job(job_id)
    if job is None:
        raise KeyError("Analysis job not found")
    if job.analysisKind != "multiview":
        raise MultiviewNotApplicableError
    return job


__all__ = [
    "EPISODE_OUTCOMES",
    "MultiviewNotApplicableError",
    "MultiviewObservabilityProjector",
    "RecoveryEpisodeProjector",
    "get_multiview_job_or_raise",
    "structured_error",
]
