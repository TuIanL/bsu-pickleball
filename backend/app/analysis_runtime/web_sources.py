"""Web 来源准备及只读绑定校验，不参与算法执行。"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from app.analysis_runtime.hashing import AnalysisRuntimeError
from app.analysis_runtime.sources import prepare_source, sync_contract
from app.services.sync_anchor_service import SyncAnchorAssetService, SyncAnchorNotFoundError, _read_json


@contextmanager
def session(db=None):
    if db is not None:
        yield db
    else:
        from app.database import get_session_factory
        with get_session_factory()() as owned:
            yield owned


def take_context(db, take_id, *, prepare=False):
    service = SyncAnchorAssetService(db)
    try:
        take = service._take(take_id)
        status = service.status(take_id, require_manual=True, allow_migration=prepare)
        if status.state != "confirmed" or not status.analysis_allowed or len(status.provenance) != 2:
            raise AnalysisRuntimeError("authoritative_sync_required", "请先完成两机位同步确认", details=status.reason_codes)
        calibration = _read_json(service._paths(take, create=False)["calibration"])
        sync = sync_contract(calibration or {})
        return take, status, sync
    except SyncAnchorNotFoundError as exc:
        raise AnalysisRuntimeError("source_binding_invalid", "录制来源不可用") from exc


def prepare_take_sources(store, db, take_id):
    take, status, sync = take_context(db, take_id, prepare=True)
    service = SyncAnchorAssetService(db)
    sources = []
    for item in status.provenance:
        video = service.video_service.get_video(item.registered_video_id)
        if video is None:
            raise AnalysisRuntimeError("source_missing", "录制视频不可用")
        sources.append(prepare_source(store, Path(video.path), view_id=item.slot,
                                     camera_id=item.camera_id, video_id=video.id, require_pts=True))
    reference = next((s.view_id for s in sources if s.camera_id == sync["reference_camera"]), None)
    if reference is None:
        raise AnalysisRuntimeError("sync_reference_mismatch", "同步参考机位与来源不符")
    binding = {"take_id": take.id, "sync_revision": status.revision,
               "provenance_fingerprint": status.provenance_fingerprint}
    # 准备过程可能较长；返回前再核对确认版本和来源。
    from app.analysis_runtime.contracts import AnalysisRequest
    request = AnalysisRequest(source_ids=tuple(s.source_id for s in sources), targets=("ball.detect",),
                              window={"start_ms": 0, "end_ms": 1}, source_binding=binding, sync=sync)
    validate_binding(request, sources, db=db)
    return {"sources": [s.model_dump(mode="json") for s in sources],
            "source_ids": [s.source_id for s in sources], "reference_view_id": reference,
            "sync": sync, "source_binding": binding, "recording_session_id": take.source_session_id}


def validate_binding(request, sources, *, db=None):
    binding = request.source_binding
    if binding is None:
        return
    with session(db) as current:
        _take, status, sync = take_context(current, binding.take_id)
        expected = {(p.registered_video_id, p.slot, p.camera_id) for p in status.provenance}
        actual = {(s.video_id, s.view_id, s.camera_id) for s in sources}
        if (len(sources) != 2 or actual != expected or status.revision != binding.sync_revision
                or status.provenance_fingerprint != binding.provenance_fingerprint
                or sync_contract(request.sync or {}) != sync):
            raise AnalysisRuntimeError("source_binding_stale", "来源或同步已变化，请重新准备")


def verified_metadata(metadata, sources, binding, *, db=None):
    """仅使用登记信息验证归属；无录制声明的旧 CLI 保持兼容。"""
    take_id = binding.take_id if binding else metadata.capture_take_id
    if binding and metadata.capture_take_id not in (None, binding.take_id):
        raise AnalysisRuntimeError("source_ownership_mismatch", "录制关联与来源不一致")
    if take_id:
        with session(db) as current:
            service = SyncAnchorAssetService(current)
            try:
                take = service._take(take_id)
            except SyncAnchorNotFoundError as exc:
                raise AnalysisRuntimeError("source_ownership_mismatch", "录制不存在") from exc
            registered = service._registered_inputs(take)
            allowed = {p["registered_video_id"] for p in registered}
            if (not {s.video_id for s in sources} <= allowed
                    or metadata.recording_session_id not in (None, take.source_session_id)):
                raise AnalysisRuntimeError("source_ownership_mismatch", "录制关联与来源不一致")
            if metadata.camera_slot and (len(sources) != 1 or not any(
                p["slot"] == metadata.camera_slot and p["registered_video_id"] == sources[0].video_id for p in registered
            )):
                raise AnalysisRuntimeError("source_ownership_mismatch", "录制机位与来源不一致")
            return metadata.model_copy(update={"capture_take_id": take.id, "recording_session_id": take.source_session_id})
    if metadata.recording_session_id:
        from app.camera.sync_recorder_service import sync_recording_service
        from app.camera.session_service import session_service
        recording = sync_recording_service.get_session(metadata.recording_session_id)
        if recording is not None:
            slots = recording.registered_video_ids or {}
            allowed = set(slots.values())
            if metadata.camera_slot and (len(sources) != 1 or slots.get(metadata.camera_slot) != sources[0].video_id):
                raise AnalysisRuntimeError("source_ownership_mismatch", "录制机位与来源不一致")
        else:
            recording = session_service.get_session(metadata.recording_session_id)
            allowed = {recording.video_id} if recording else set()
        if not recording or not {s.video_id for s in sources} <= allowed:
            raise AnalysisRuntimeError("source_ownership_mismatch", "录制关联与来源不一致")
    return metadata
