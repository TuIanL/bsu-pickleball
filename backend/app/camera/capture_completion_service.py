"""CaptureCompletionService —— 唯一定终态决策"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.camera.capture_runtime_coordinator import CaptureRuntimeOutcome
from app.camera.capture_finalizer import TrackFinalizationResult

logger = logging.getLogger(__name__)


@dataclass
class CompletionDecision:
    terminal_status: str
    warnings: list[str] = field(default_factory=list)
    analysis_available: bool = False
    default_analysis_track_id: str | None = None
    default_analysis_video_id: str | None = None


class CaptureCompletionService:
    def decide(self, outcome: CaptureRuntimeOutcome,
               results: list[TrackFinalizationResult]) -> CompletionDecision:
        warnings = list(outcome.runtime_warnings)
        default_track_id = None
        default_video_id = None

        primary_success = False
        any_success = False

        for r in results:
            if r.status in ("succeeded", "reused"):
                any_success = True
                if r.video_id:
                    default_track_id = r.capture_track_id
                    default_video_id = r.video_id
                    primary_success = True
            elif r.status == "failed":
                warnings.append(f"Track {r.capture_track_id} finalization failed")
                if not primary_success:
                    warnings.extend(r.warnings)

        if outcome.primary_track_lost:
            return CompletionDecision(
                terminal_status="failed",
                warnings=warnings + ["主分析轨不可恢复"],
            )

        if primary_success:
            status = "partial" if outcome.restart_budget_exhausted or not all(
                r.status in ("succeeded", "reused") for r in results
            ) else "completed"
            return CompletionDecision(
                terminal_status=status,
                warnings=warnings,
                analysis_available=True,
                default_analysis_track_id=default_track_id,
                default_analysis_video_id=default_video_id,
            )

        if any_success:
            return CompletionDecision(
                terminal_status="partial",
                warnings=warnings + ["主分析轨不可用，仅辅轨有素材"],
                default_analysis_track_id=default_track_id or None,
                default_analysis_video_id=default_video_id,
            )

        return CompletionDecision(
            terminal_status="failed",
            warnings=warnings + ["无可用轨道"],
        )

    def finalize_and_decide(
        self, capture_take_id: str,
        outcome: CaptureRuntimeOutcome,
        finalizer,
        fragment_infos_by_track: dict[str, list[dict]],
    ) -> CompletionDecision:
        results = []
        for track_id, frags in fragment_infos_by_track.items():
            r = finalizer.finalize_track(track_id, frags)
            results.append(r)

        decision = self.decide(outcome, results)

        self._apply_finalize_capture_take(capture_take_id, decision)

        return decision

    def _apply_finalize_capture_take(self, capture_take_id: str, decision: CompletionDecision) -> None:
        try:
            from app.database import get_session_factory
            from app.services import capture_take_service
            db = get_session_factory()()
            try:
                capture_take_service.finalize_capture_take(
                    db, capture_take_id, decision.terminal_status,
                    ended_at=datetime.now(timezone.utc),
                )
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning("finalize_capture_take failed: %s", e)
            finally:
                db.close()
        except Exception as e:
            logger.warning("completion service DB error: %s", e)
