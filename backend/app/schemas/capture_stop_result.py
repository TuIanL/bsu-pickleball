"""CaptureStopResult schema —— 统一的录制停止返回值（单摄/双摄共用）。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.schemas.capture_take_summary import CaptureTakeSummary


class CaptureTrackStopResult(BaseModel):
    track_id: str
    slot: str  # "cam_1" | "cam_2"
    camera_id: str
    analysis_role: str = "default"  # "default" | "supplementary"
    status: str  # "completed" | "partial" | "failed"
    video_id: Optional[str] = None
    duration_ms: Optional[int] = None
    fragment_count: int = 1
    restart_count: int = 0


class CaptureStopResult(BaseModel):
    capture_take: Optional[CaptureTakeSummary] = None
    tracks: list[CaptureTrackStopResult] = []
    analysis_available: bool = False
    default_analysis_track_id: Optional[str] = None
    default_analysis_video_id: Optional[str] = None
    analysis_blocked_reason: Optional[str] = None
    warnings: list[str] = []


class CaptureStopResultBuilder:
    """从单摄/双摄 Session 构建统一 CaptureStopResult。"""

    @staticmethod
    def from_single_session(
        recording_session,
        capture_take=None,
        track_id: str = "",
        video_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        warnings: Optional[list[str]] = None,
    ) -> CaptureStopResult:
        track = CaptureTrackStopResult(
            track_id=track_id or recording_session.session_id,
            slot="cam_1",
            camera_id=recording_session.camera_id,
            analysis_role="default",
            status="completed" if recording_session.status == "completed" else "partial",
            video_id=video_id or recording_session.video_id,
            duration_ms=duration_ms or int((recording_session.duration_sec or 0) * 1000),
            fragment_count=1,
            restart_count=0,
        )
        take_summary = None
        if capture_take:
            take_summary = CaptureTakeSummary(
                id=capture_take.id,
                field_session_id=capture_take.field_session_id,
                capture_mode=capture_take.capture_mode.value if hasattr(capture_take.capture_mode, 'value') else str(capture_take.capture_mode),
                source_session_type=capture_take.source_session_type.value if hasattr(capture_take.source_session_type, 'value') else str(capture_take.source_session_type),
                source_session_id=capture_take.source_session_id,
                status=capture_take.status.value if hasattr(capture_take.status, 'value') else str(capture_take.status),
                started_at=capture_take.started_at,
                ended_at=capture_take.ended_at,
                duration_ms=capture_take.duration_ms,
                revision=capture_take.revision,
            )

        return CaptureStopResult(
            capture_take=take_summary,
            tracks=[track],
            analysis_available=bool(video_id or recording_session.video_id),
            default_analysis_track_id=track.track_id,
            default_analysis_video_id=video_id or recording_session.video_id,
            warnings=warnings or [],
        )

    @staticmethod
    def from_sync_session(
        sync_session,
        capture_take=None,
        cam_1_video_id: Optional[str] = None,
        cam_2_video_id: Optional[str] = None,
        cam_1_duration_ms: Optional[int] = None,
        cam_2_duration_ms: Optional[int] = None,
        warnings: Optional[list[str]] = None,
    ) -> CaptureStopResult:
        cam_slots = getattr(sync_session, "camera_slots", {}) or {}
        tracks = []

        for slot_name in ["cam_1", "cam_2"]:
            slot_info = cam_slots.get(slot_name, {})
            camera_id = getattr(slot_info, "camera_id", "") if hasattr(slot_info, "camera_id") else slot_info.get("camera_id", "")
            vid = cam_1_video_id if slot_name == "cam_1" else cam_2_video_id
            dur = cam_1_duration_ms if slot_name == "cam_1" else cam_2_duration_ms

            tracks.append(CaptureTrackStopResult(
                track_id=f"{sync_session.session_id}_{slot_name}",
                slot=slot_name,
                camera_id=str(camera_id),
                analysis_role="default" if slot_name == "cam_1" else "supplementary",
                status="completed" if vid else "partial",
                video_id=vid,
                duration_ms=dur,
                fragment_count=len(getattr(sync_session, "segments", []) or []),
                restart_count=getattr(sync_session, "total_restarts", 0),
            ))

        take_summary = None
        if capture_take:
            take_summary = CaptureTakeSummary(
                id=capture_take.id,
                field_session_id=capture_take.field_session_id,
                capture_mode=capture_take.capture_mode.value if hasattr(capture_take.capture_mode, 'value') else str(capture_take.capture_mode),
                source_session_type=capture_take.source_session_type.value if hasattr(capture_take.source_session_type, 'value') else str(capture_take.source_session_type),
                source_session_id=capture_take.source_session_id,
                status=capture_take.status.value if hasattr(capture_take.status, 'value') else str(capture_take.status),
                started_at=capture_take.started_at,
                ended_at=capture_take.ended_at,
                duration_ms=capture_take.duration_ms,
                revision=capture_take.revision,
            )

        default_track = next((t for t in tracks if t.analysis_role == "default"), tracks[0] if tracks else None)

        return CaptureStopResult(
            capture_take=take_summary,
            tracks=tracks,
            analysis_available=bool(cam_1_video_id),
            default_analysis_track_id=default_track.track_id if default_track else None,
            default_analysis_video_id=cam_1_video_id,
            warnings=warnings or [],
        )
