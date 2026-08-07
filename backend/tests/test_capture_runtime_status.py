"""后端测试 —— CaptureTake 运行状态聚合服务。

覆盖场景（spec 1.6）：
- 单摄活跃录制
- 双摄活跃录制
- 终态录制（completed）
- 部分轨道失败
- 存储错误
- 不存在的 Take（404 等价）

直接调用聚合服务，避免依赖录制会话服务的复杂启动流程；
通过手动构造 CaptureTake / CaptureTrack / MediaFragment 和 tmp_path 上的真实分片文件
验证文件大小、存储容量、码率、有效帧率、同步状态的聚合逻辑。
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

# 确保可导入 backend.app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_session_factory, init_db  # noqa: E402

init_db()

from app.models.capture_take import CaptureMode, CaptureTake, CaptureTakeStatus, SourceSessionType  # noqa: E402
from app.models.capture_track import (  # noqa: E402
    AnalysisRole,
    CaptureTrack,
    CaptureTrackSlot,
    OffsetSource,
    SyncQuality,
    TrackRole,
)
from app.models.field_session import FieldSession  # noqa: E402
from app.models.media_fragment import FragmentStatus, MediaFragment  # noqa: E402
from app.services import capture_runtime_status_service as runtime_svc  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# 测试夹具
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """提供独立数据库会话，测试结束清理创建的活跃 CaptureTake，避免污染其他测试。"""
    session = get_session_factory()()
    try:
        # 包装 _make_take 以追踪创建的 take id
        yield session
    finally:
        # 清理本测试创建的所有 CaptureTake（含关联的 track/fragment 由外键级联或手动删）
        try:
            # 查找本测试产生的活跃 take（started_at 在近 4 小时内、status 为活跃）
            from datetime import datetime, timedelta

            from app.models.capture_take import CaptureTake as _CT
            from app.models.capture_take import CaptureTakeStatus as _CTS
            from app.models.capture_track import CaptureTrack as _TR
            from app.models.field_session import FieldSession as _FS
            from app.models.media_fragment import MediaFragment as _MF

            cutoff = datetime.now(UTC) - timedelta(hours=4)
            active_takes = (
                session.query(_CT)
                .filter(_CT.status.in_([_CTS.starting, _CTS.recording]))
                .filter(_CT.started_at >= cutoff)
                .all()
            )
            for take in active_takes:
                # 删除关联的 fragment 和 track
                session.query(_MF).filter(_MF.capture_take_id == take.id).delete(synchronize_session=False)
                session.query(_TR).filter(_TR.capture_take_id == take.id).delete(synchronize_session=False)
                # 标记为 canceled 避免活跃检测
                take.status = _CTS.canceled
            # 删除测试创建的 FieldSession（title 标记为 runtime-status-test）
            session.query(_FS).filter(_FS.title == "runtime-status-test").delete(synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


def _make_field_session(db, court_name: str = "test-court") -> FieldSession:
    """创建一个最小化的 FieldSession 记录。"""
    import uuid

    fs = FieldSession(
        id=f"fs_{uuid.uuid4().hex[:8]}",
        title="runtime-status-test",
        venue="test-venue",
        court_name=court_name,
        capture_mode="practice",
        match_format="doubles",
        camera_setup="dual",
        status="active",
    )
    db.add(fs)
    db.flush()
    return fs


def _make_take(
    db,
    *,
    fs: FieldSession,
    capture_mode: str = "single",
    status: CaptureTakeStatus = CaptureTakeStatus.recording,
    session_dir: str | None = None,
    storage_root: str | None = None,
    source_session_id: str | None = None,
    started_at: datetime | None = None,
    duration_ms: int | None = None,
) -> CaptureTake:
    """创建一个 CaptureTake 记录。"""
    import uuid

    take = CaptureTake(
        id=f"ct_{uuid.uuid4().hex[:8]}",
        field_session_id=fs.id,
        capture_mode=CaptureMode(capture_mode),
        source_session_type=SourceSessionType.recording,
        source_session_id=source_session_id or f"rec_{uuid.uuid4().hex[:8]}",
        storage_root=storage_root,
        session_dir=session_dir,
        storage_status="available",
        status=status,
        started_at=started_at or datetime.now(UTC),
        ended_at=datetime.now(UTC)
        if status
        in {
            CaptureTakeStatus.completed,
            CaptureTakeStatus.failed,
            CaptureTakeStatus.canceled,
            CaptureTakeStatus.partial,
        }
        else None,
        duration_ms=duration_ms,
        revision=0,
    )
    db.add(take)
    db.flush()
    return take


def _make_track(
    db,
    *,
    take: CaptureTake,
    slot: str = "cam_1",
    camera_id: str = "cam-1",
    sync_quality: str = "good",
) -> CaptureTrack:
    """创建一个 CaptureTrack 记录。"""
    import uuid

    track = CaptureTrack(
        id=f"tr_{uuid.uuid4().hex[:8]}",
        capture_take_id=take.id,
        camera_id=camera_id,
        role=TrackRole.primary if slot == "cam_1" else TrackRole.secondary,
        slot=CaptureTrackSlot(slot),
        analysis_role=AnalysisRole.default if slot == "cam_1" else AnalysisRole.supplementary,
        video_id=None,
        offset_ms=0,
        offset_source=OffsetSource.assumed,
        sync_quality=SyncQuality(sync_quality),
    )
    db.add(track)
    db.flush()
    return track


def _make_fragment(
    db,
    *,
    track: CaptureTrack,
    take: CaptureTake,
    file_path: str,
    status: FragmentStatus = FragmentStatus.completed,
    file_size: int | None = None,
    fragment_index: int = 0,
    error_message: str | None = None,
) -> MediaFragment:
    """创建一个 MediaFragment 记录。"""
    import uuid

    frag = MediaFragment(
        id=f"frag_{uuid.uuid4().hex[:8]}",
        capture_take_id=take.id,
        capture_track_id=track.id,
        fragment_index=fragment_index,
        rotation_index=0,
        file_path=file_path,
        status=status,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC)
        if status
        not in {
            FragmentStatus.starting,
            FragmentStatus.recording,
        }
        else None,
        file_size=file_size,
        error_message=error_message,
    )
    db.add(frag)
    db.flush()
    return frag


# ─────────────────────────────────────────────────────────────────────────────
# 1. 单摄活跃录制
# ─────────────────────────────────────────────────────────────────────────────


def test_single_camera_active_recording_returns_storage_and_file_size(db, tmp_path):
    """单摄 recording 状态：应返回存储容量、文件大小（含活动分片）和 collecting 帧率。"""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="single",
        status=CaptureTakeStatus.recording,
        session_dir=str(session_dir),
        storage_root=str(tmp_path),
    )
    track = _make_track(db, take=take, slot="cam_1", sync_quality="good")

    # 已完成分片：DB 已有 file_size
    _make_fragment(
        db,
        track=track,
        take=take,
        file_path=str(session_dir / "frag_0.ts"),
        status=FragmentStatus.completed,
        file_size=1024 * 1024,  # 1 MB
        fragment_index=0,
    )
    # 活动分片：DB file_size=None，需要 os.stat 读取真实文件
    active_frag_path = session_dir / "frag_1.ts"
    active_frag_path.write_bytes(b"x" * (512 * 1024))  # 512 KB
    _make_fragment(
        db,
        track=track,
        take=take,
        file_path=str(active_frag_path),
        status=FragmentStatus.recording,
        file_size=None,
        fragment_index=1,
    )

    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)  # 清除可能的码率缓存

    status = runtime_svc.get_capture_take_runtime_status(db, take.id)

    assert status is not None
    assert status.capture_take_id == take.id
    assert status.capture_mode == "single"

    # 存储：应读取 tmp_path 所在文件系统
    assert status.storage.state == "ready"
    assert status.storage.total_bytes > 0
    assert status.storage.free_bytes > 0
    assert status.storage.used_bytes > 0

    # 录制阶段
    assert status.recording.phase == "recording"
    assert status.recording.target_fps is None  # 源会话不存在，target 未知
    assert status.recording.elapsed_ms is not None and status.recording.elapsed_ms >= 0

    # 文件大小：1MB + 512KB = 1.5MB
    assert status.recording.file_size_bytes.state == "ready"
    assert status.recording.file_size_bytes.value == pytest.approx(1024 * 1024 + 512 * 1024)

    # 有效帧率：有活动分片 → collecting
    assert status.recording.effective_fps.state == "collecting"

    # 码率：首次请求无基线 → unavailable
    assert status.recording.avg_bitrate_bps.state == "unavailable"

    # 单摄：sync 为 None
    assert status.sync is None

    # 轨道
    assert len(status.tracks) == 1
    assert status.tracks[0].slot == "cam_1"
    assert status.tracks[0].phase == "recording"
    assert status.tracks[0].file_size_bytes.state == "ready"


# ─────────────────────────────────────────────────────────────────────────────
# 2. 双摄活跃录制
# ─────────────────────────────────────────────────────────────────────────────


def test_dual_camera_active_recording_returns_per_track_status(db, tmp_path):
    """双摄 recording：应返回 cam_1/cam_2 独立状态和 dual_sync 摘要。"""
    session_dir = tmp_path / "session_dual"
    session_dir.mkdir()
    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="dual",
        status=CaptureTakeStatus.recording,
        session_dir=str(session_dir),
    )
    track1 = _make_track(db, take=take, slot="cam_1", sync_quality="good")
    track2 = _make_track(db, take=take, slot="cam_2", sync_quality="degraded")

    # cam_1 分片
    frag1 = session_dir / "cam1_0.ts"
    frag1.write_bytes(b"a" * 2048)
    _make_fragment(
        db,
        track=track1,
        take=take,
        file_path=str(frag1),
        status=FragmentStatus.completed,
        file_size=2048,
        fragment_index=0,
    )
    # cam_2 分片
    frag2 = session_dir / "cam2_0.ts"
    frag2.write_bytes(b"b" * 1024)
    _make_fragment(
        db,
        track=track2,
        take=take,
        file_path=str(frag2),
        status=FragmentStatus.recording,
        file_size=None,
        fragment_index=0,
    )

    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)

    status = runtime_svc.get_capture_take_runtime_status(db, take.id)

    assert status is not None
    assert status.capture_mode == "dual"
    assert len(status.tracks) == 2
    slots = {t.slot for t in status.tracks}
    assert slots == {"cam_1", "cam_2"}

    # 文件大小：cam_1 已完成 2048 + cam_2 活动 1024 = 3072
    assert status.recording.file_size_bytes.state == "ready"
    assert status.recording.file_size_bytes.value == pytest.approx(3072)

    # dual_sync：cam_2 为 degraded → collecting
    assert status.sync is not None
    assert status.sync.dual_sync == "collecting"
    assert status.sync.dual_sync_quality == "degraded"


# ─────────────────────────────────────────────────────────────────────────────
# 3. 终态录制
# ─────────────────────────────────────────────────────────────────────────────


def test_terminal_take_returns_last_metrics_and_stops_bitrate_updates(db, tmp_path):
    """终态录制：应返回 duration_ms、unavailable 帧率，且不再更新码率缓存。"""
    session_dir = tmp_path / "session_done"
    session_dir.mkdir()
    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="single",
        status=CaptureTakeStatus.completed,
        session_dir=str(session_dir),
        duration_ms=60_000,
    )
    track = _make_track(db, take=take, slot="cam_1")
    _make_fragment(
        db,
        track=track,
        take=take,
        file_path=str(session_dir / "done.ts"),
        status=FragmentStatus.completed,
        file_size=5000,
        fragment_index=0,
    )

    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)

    status = runtime_svc.get_capture_take_runtime_status(db, take.id)

    assert status is not None
    assert status.recording.phase == "completed"
    assert status.recording.duration_ms == 60_000
    assert status.recording.elapsed_ms == 60_000
    # 终态帧率：unavailable
    assert status.recording.effective_fps.state == "unavailable"
    # 终态码率：无基线 → unavailable，且不应写入缓存
    assert status.recording.avg_bitrate_bps.state == "unavailable"
    assert take.id not in runtime_svc._bitrate_samples


# ─────────────────────────────────────────────────────────────────────────────
# 4. 部分轨道失败
# ─────────────────────────────────────────────────────────────────────────────


def test_partial_track_failure_reports_error_but_keeps_ready_total(db, tmp_path):
    """一个轨道活动分片不可读（os.stat 失败）时：该轨道 error，take 总大小仍 ready。"""
    session_dir = tmp_path / "session_partial"
    session_dir.mkdir()
    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="dual",
        status=CaptureTakeStatus.recording,
        session_dir=str(session_dir),
    )
    track1 = _make_track(db, take=take, slot="cam_1", sync_quality="good")
    track2 = _make_track(db, take=take, slot="cam_2", sync_quality="good")

    # cam_1 正常
    frag1 = session_dir / "cam1.ts"
    frag1.write_bytes(b"x" * 1000)
    _make_fragment(
        db,
        track=track1,
        take=take,
        file_path=str(frag1),
        status=FragmentStatus.completed,
        file_size=1000,
        fragment_index=0,
    )
    # cam_2 活动分片指向不存在的路径 → os.stat 失败
    _make_fragment(
        db,
        track=track2,
        take=take,
        file_path=str(session_dir / "missing.ts"),
        status=FragmentStatus.recording,
        file_size=None,
        fragment_index=0,
    )

    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)

    status = runtime_svc.get_capture_take_runtime_status(db, take.id)

    assert status is not None
    # cam_2 轨道 error
    cam2_status = next(t for t in status.tracks if t.slot == "cam_2")
    assert cam2_status.file_size_bytes.state == "error"
    assert cam2_status.file_size_bytes.message is not None

    # cam_1 轨道 ready
    cam1_status = next(t for t in status.tracks if t.slot == "cam_1")
    assert cam1_status.file_size_bytes.state == "ready"

    # take 总大小：仍有 ready 轨道，返回 ready 值 + 警告 message
    assert status.recording.file_size_bytes.state == "ready"
    assert status.recording.file_size_bytes.value == pytest.approx(1000)


# ─────────────────────────────────────────────────────────────────────────────
# 5. 存储错误
# ─────────────────────────────────────────────────────────────────────────────


def test_storage_error_when_disk_usage_fails(db, tmp_path, monkeypatch):
    """shutil.disk_usage 抛 OSError：返回 storage error，不回退到默认目录。"""
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="single",
        status=CaptureTakeStatus.recording,
        session_dir=str(session_dir),
    )
    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)

    # 模拟磁盘读取失败
    def _fail_disk_usage(_path):
        raise OSError("simulated storage failure")

    monkeypatch.setattr(
        "app.services.capture_runtime_status_service.shutil.disk_usage",
        _fail_disk_usage,
    )

    status = runtime_svc.get_capture_take_runtime_status(db, take.id)

    assert status is not None
    assert status.storage.state == "error"
    assert status.storage.message is not None
    # 不得回退到默认目录推断容量
    assert status.storage.total_bytes is None


def test_storage_unavailable_when_session_dir_is_none(db):
    """CaptureTake 尚未绑定 session_dir：返回 unavailable，不抛异常。"""
    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="single",
        status=CaptureTakeStatus.starting,
        session_dir=None,
    )
    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)

    status = runtime_svc.get_capture_take_runtime_status(db, take.id)

    assert status is not None
    assert status.storage.state == "unavailable"
    assert status.storage.message is not None


# ─────────────────────────────────────────────────────────────────────────────
# 6. 不存在的 Take
# ─────────────────────────────────────────────────────────────────────────────


def test_nonexistent_take_returns_none(db):
    """不存在的 CaptureTake ID：聚合服务返回 None（路由层映射为 404）。"""
    status = runtime_svc.get_capture_take_runtime_status(db, "ct_does_not_exist")
    assert status is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. 码率缓存逻辑
# ─────────────────────────────────────────────────────────────────────────────


def test_bitrate_computed_on_second_snapshot(db, tmp_path):
    """两次快照间隔足够时：第二次返回 ready 码率。"""
    session_dir = tmp_path / "session_bitrate"
    session_dir.mkdir()
    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="single",
        status=CaptureTakeStatus.recording,
        session_dir=str(session_dir),
    )
    track = _make_track(db, take=take, slot="cam_1")

    # 初始分片
    frag_path = session_dir / "frag.ts"
    frag_path.write_bytes(b"x" * 1024)
    _make_fragment(
        db,
        track=track,
        take=take,
        file_path=str(frag_path),
        status=FragmentStatus.recording,
        file_size=None,
        fragment_index=0,
    )
    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)

    # 第一次请求：unavailable（建立基线）
    status1 = runtime_svc.get_capture_take_runtime_status(db, take.id)
    assert status1.recording.avg_bitrate_bps.state == "unavailable"

    # 写入更多数据
    frag_path.write_bytes(b"x" * (1024 + 100_000))

    # 强制时间推进（码率最小窗口 0.5s）
    time.sleep(0.6)

    # 第二次请求：应返回 ready 码率
    status2 = runtime_svc.get_capture_take_runtime_status(db, take.id)
    assert status2.recording.avg_bitrate_bps.state == "ready"
    assert status2.recording.avg_bitrate_bps.value > 0

    runtime_svc.reset_bitrate_sample(take.id)


# ─────────────────────────────────────────────────────────────────────────────
# 8. 安全边界：不接受客户端路径覆盖
# ─────────────────────────────────────────────────────────────────────────────


def test_runtime_status_uses_only_take_session_dir_not_client_path(db, tmp_path):
    """runtime status 只读取 CaptureTake.session_dir，客户端无法注入任意路径。"""
    real_dir = tmp_path / "real_session"
    real_dir.mkdir()
    fake_dir = tmp_path / "fake_session"
    fake_dir.mkdir()
    # fake_dir 写入大文件作为陷阱
    (fake_dir / "trap.ts").write_bytes(b"x" * 1_000_000)

    fs = _make_field_session(db)
    take = _make_take(
        db,
        fs=fs,
        capture_mode="single",
        status=CaptureTakeStatus.recording,
        session_dir=str(real_dir),
    )
    track = _make_track(db, take=take, slot="cam_1")
    frag_path = real_dir / "frag.ts"
    frag_path.write_bytes(b"y" * 500)
    _make_fragment(
        db,
        track=track,
        take=take,
        file_path=str(frag_path),
        status=FragmentStatus.recording,
        file_size=None,
        fragment_index=0,
    )
    db.commit()
    runtime_svc.reset_bitrate_sample(take.id)

    status = runtime_svc.get_capture_take_runtime_status(db, take.id)

    assert status is not None
    # 文件大小应为 500（real_dir），而非 1_000_000（fake_dir 陷阱）
    assert status.recording.file_size_bytes.state == "ready"
    assert status.recording.file_size_bytes.value == pytest.approx(500)
