"""Persist SQLite-backed capture timeline data beside the media."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment
from app.models.capture_take import CaptureTake
from app.models.capture_track import CaptureTrack
from app.models.live_coding_state import LiveCodingState
from app.models.timeline_event import SessionTimelineEvent
from app.services.capture_storage_service import capture_storage_plan_from_dir, write_json_atomic

logger = logging.getLogger(__name__)


# 将时间线事件模型转换为可序列化的字典
def _frame_index(timestamp_ms: int, fps: float | None) -> int | None:
    """Map a capture-relative timestamp to the nearest source frame."""
    if not fps or fps <= 0:
        return None
    return max(0, int(round(timestamp_ms * fps / 1000.0)))


def _event_payload(event: SessionTimelineEvent, *, fps: float | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(event.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {
        "id": event.id,
        "field_session_id": event.field_session_id,
        "recording_session_id": event.recording_session_id,
        "capture_take_id": event.capture_take_id,
        "timestamp_ms": event.timestamp_ms,
        "frame_index": _frame_index(event.timestamp_ms, fps),
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "event_type": event.event_type.value,
        "source": event.source.value,
        "label": event.label,
        "note": event.note,
        "payload": payload,
        "is_undone": event.is_undone,
    }


# 将采集 take 的时间线数据（事件、片段、实时状态）快照到磁盘 JSON 文件
def snapshot_capture_timeline(
    db: Session,
    capture_take_id: str,
    *,
    fps: float | None = None,
    video_sources: list[dict[str, Any]] | None = None,
) -> bool:
    take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
    if take is None or not take.session_dir:
        return False
    try:
        plan = capture_storage_plan_from_dir(take.session_dir)
        # Event edits can trigger another snapshot after media registration
        # preserve the finalized timebase/source mapping when callers omit it.
        existing_annotation: dict[str, Any] = {}
        try:
            existing_annotation = json.loads(
                (plan.timeline_dir / "annotation_manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            pass
        if fps is None:
            fps = (existing_annotation.get("timebase") or {}).get("fps")
        if video_sources is None:
            existing_sources = existing_annotation.get("sources")
            if isinstance(existing_sources, list):
                video_sources = existing_sources
        events = (
            db.query(SessionTimelineEvent)
            .filter(SessionTimelineEvent.capture_take_id == capture_take_id)
            .order_by(SessionTimelineEvent.timestamp_ms.asc(), SessionTimelineEvent.created_at.asc())
            .all()
        )
        segments = (
            db.query(CaptureSegment)
            .filter(CaptureSegment.capture_take_id == capture_take_id)
            .order_by(CaptureSegment.start_ms.asc(), CaptureSegment.created_at.asc())
            .all()
        )
        state = db.query(LiveCodingState).filter(LiveCodingState.capture_take_id == capture_take_id).first()
        event_rows = [_event_payload(event, fps=fps) for event in events]
        segment_rows = [
            {
                "id": segment.id,
                "segment_type": segment.segment_type.value,
                "parent_segment_id": segment.parent_segment_id,
                "ordinal": segment.ordinal,
                "label": segment.label,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "start_frame_index": _frame_index(segment.start_ms, fps),
                "end_frame_index": _frame_index(segment.end_ms, fps),
                "effective_start_ms": segment.effective_start_ms,
                "effective_end_ms": segment.effective_end_ms,
                "status": segment.status.value,
                "source": segment.source.value,
                "is_highlight": segment.is_highlight,
            }
            for segment in segments
        ]
        state_row = (
            None
            if state is None
            else {
                "capture_take_id": state.capture_take_id,
                "revision": state.revision,
                "set_ordinal": state.set_ordinal,
                "game_ordinal": state.game_ordinal,
                "rally_ordinal": state.rally_ordinal,
                "non_play": state.non_play,
                "match_phase": state.match_phase,
                "intermission_kind": state.intermission_kind,
                "current_set_segment_id": state.current_set_segment_id,
                "current_game_segment_id": state.current_game_segment_id,
                "current_rally_segment_id": state.current_rally_segment_id,
            }
        )
        write_json_atomic(
            plan.timeline_dir / "events.json",
            {"schema_version": "capture_events.v1", "capture_take_id": capture_take_id, "events": event_rows},
        )
        write_json_atomic(
            plan.timeline_dir / "markers.json",
            {
                "schema_version": "capture_markers.v1",
                "capture_take_id": capture_take_id,
                "markers": [e for e in event_rows if e["event_type"] == "custom_marker"],
            },
        )
        write_json_atomic(
            plan.timeline_dir / "segments.json",
            {"schema_version": "capture_segments.v1", "capture_take_id": capture_take_id, "segments": segment_rows},
        )
        write_json_atomic(
            plan.timeline_dir / "live_state.json",
            {"schema_version": "capture_live_state.v1", "capture_take_id": capture_take_id, "state": state_row},
        )
        tracks = (
            db.query(CaptureTrack)
            .filter(CaptureTrack.capture_take_id == capture_take_id)
            .order_by(CaptureTrack.slot.asc())
            .all()
        )
        track_sources = video_sources or [
            {
                "track_id": track.id,
                "slot": track.slot.value,
                "camera_id": track.camera_id,
                "video_id": track.video_id,
                "offset_ms": track.offset_ms,
            }
            for track in tracks
        ]
        write_json_atomic(
            plan.timeline_dir / "annotation_manifest.json",
            {
                "schema_version": "capture_annotation.v1",
                "capture_take_id": capture_take_id,
                "timebase": {
                    "unit": "milliseconds",
                    "origin": "capture_take_start",
                    "fps": fps,
                    "frame_index_rounding": "nearest",
                },
                "sync_calibration": {
                    "schema_version": "dual_camera_sync_calibration.v1",
                    "status": "unknown",
                    "reason": "cross-camera calibration anchors unavailable",
                },
                "sources": track_sources,
                "events_file": "events.json",
                "segments_file": "segments.json",
            },
        )
        return True
    except OSError as exc:
        logger.error("写入 CaptureTake %s 时间线归档失败: %s", capture_take_id, exc)
        return False
