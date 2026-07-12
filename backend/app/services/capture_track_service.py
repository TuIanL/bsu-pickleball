"""CaptureTrack 服务层 —— 轨道创建与时间偏移管理。"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_track import (
    AnalysisRole,
    CaptureTrack,
    CaptureTrackSlot,
    OffsetSource,
    SyncQuality,
    TrackRole,
)

# 轨道 ID 前缀
_ID_PREFIX = "tr"


# 生成带前缀的唯一 ID（tr_ + 12 位随机十六进制）
def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


# 创建一条轨道记录（记录相机、角色与时间偏移等同步信息）
def create_track(
    db: Session,
    *,
    capture_take_id: str,
    camera_id: str,
    role: str,
    slot: str = "cam_1",
    analysis_role: str = "default",
    video_id: str | None = None,
    offset_ms: int = 0,
    offset_source: str = "assumed",
    sync_quality: str = "unknown",
) -> CaptureTrack:
    track = CaptureTrack(
        id=_generate_id(),
        capture_take_id=capture_take_id,
        camera_id=camera_id,
        role=TrackRole(role),
        slot=CaptureTrackSlot(slot),
        analysis_role=AnalysisRole(analysis_role),
        video_id=video_id,
        offset_ms=offset_ms,
        offset_source=OffsetSource(offset_source),
        sync_quality=SyncQuality(sync_quality),
    )
    db.add(track)
    db.flush()
    return track


# 获取某个 take 下的全部轨道，按角色排序
def get_tracks_for_take(db: Session, capture_take_id: str) -> list[CaptureTrack]:
    return (
        db.query(CaptureTrack)
        .filter(CaptureTrack.capture_take_id == capture_take_id)
        .order_by(CaptureTrack.role.asc())
        .all()
    )
