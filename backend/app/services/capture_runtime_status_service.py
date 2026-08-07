"""CaptureTake 运行状态聚合服务。

依据 openspec/changes/redesign-live-recording-workspace-runtime-status：
- 复用 CaptureTake、CaptureTrack、MediaFragment 和源录制会话数据。
- 后端计算当前会话文件大小（已完成 + 活动分片）。
- 后端基于会话目录读取 shutil.disk_usage 容量。
- 后端基于最近两次快照间隔计算平均写入码率。
- 有效帧率：当前录制链路没有实时帧率诊断来源时，返回 collecting 或 unavailable，
  不得回退为目标 fps 并标记为实测。
- 只读取已由 CaptureTake 记录并校验过的会话目录，不接受任意客户端路径。
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.capture_take import CaptureTake, CaptureTakeStatus
from app.models.capture_track import CaptureTrack, SyncQuality
from app.models.media_fragment import FragmentStatus, MediaFragment
from app.schemas.capture_runtime_status import (
    CaptureTakeRuntimeStatus,
    MetricAvailability,
    MetricValue,
    RecordingMetrics,
    StorageCapacity,
    SyncRuntimeStatus,
    TrackRuntimeStatus,
)
from app.services import capture_take_service, capture_track_service

# ─────────────────────────────────────────────────────────────────────────────
# 状态枚举映射
# ─────────────────────────────────────────────────────────────────────────────

# 活跃状态：前端在 recording/stopping/recovering 阶段轮询
_ACTIVE_PHASES = {CaptureTakeStatus.starting, CaptureTakeStatus.recording}
# 终态：前端停止轮询
_TERMINAL_PHASES = {
    CaptureTakeStatus.completed,
    CaptureTakeStatus.partial,
    CaptureTakeStatus.failed,
    CaptureTakeStatus.canceled,
}

# 纳入文件大小统计的分片状态：已完成 + 正在写入 + 刚启动
# failed/interrupted 可能部分写入，但为避免误报，统一不计入
_COUNTED_FRAGMENT_STATUSES = {
    FragmentStatus.completed,
    FragmentStatus.recording,
    FragmentStatus.starting,
}


# ─────────────────────────────────────────────────────────────────────────────
# 码率采样缓存（进程内）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _BitrateSample:
    """上一次码率采样点：文件大小 + 单调时间戳。"""

    file_size_bytes: int
    monotonic_sec: float


# 按 capture_take_id 缓存上一次快照，用于计算平均写入码率
# 进程重启后缓存丢失，下次请求将返回 unavailable，符合 spec D2
_bitrate_samples: dict[str, _BitrateSample] = {}

# 码率计算的最小时间窗口（秒）：低于此窗口不计算，避免抖动
_BITRATE_MIN_WINDOW_SEC = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# 公共入口
# ─────────────────────────────────────────────────────────────────────────────


def get_capture_take_runtime_status(
    db: Session,
    capture_take_id: str,
) -> CaptureTakeRuntimeStatus | None:
    """聚合指定 CaptureTake 的运行状态快照。

    Returns:
        CaptureTakeRuntimeStatus 快照；CaptureTake 不存在时返回 None（路由层 404）。
    """
    take = capture_take_service.get_capture_take(db, capture_take_id)
    if take is None:
        return None

    tracks = capture_track_service.get_tracks_for_take(db, capture_take_id)
    fragments = (
        db.query(MediaFragment)
        .filter(MediaFragment.capture_take_id == capture_take_id)
        .order_by(MediaFragment.fragment_index.asc())
        .all()
    )

    # 按 track 分组分片
    fragments_by_track: dict[str, list[MediaFragment]] = {}
    for frag in fragments:
        fragments_by_track.setdefault(frag.capture_track_id, []).append(frag)

    # 计算每个轨道的运行状态
    track_statuses: list[TrackRuntimeStatus] = []
    track_file_sizes: list[tuple[TrackRuntimeStatus, int | None]] = []
    for track in tracks:
        track_frags = fragments_by_track.get(track.id, [])
        status = _build_track_status(track, track_frags)
        track_statuses.append(status)
        # 记录 ready 状态下的文件大小，用于 take 级聚合
        ready_size = status.file_size_bytes.value if status.file_size_bytes.state == "ready" else None
        track_file_sizes.append((status, ready_size))

    # 计算 take 级文件大小：所有 ready 轨道之和；任一轨道 error 则标记 error
    take_file_size = _aggregate_take_file_size(track_file_sizes)

    # 存储容量：基于会话目录所在文件系统
    storage = _compute_storage_capacity(take.session_dir, take.storage_root)

    # 平均写入码率：基于最近两次快照间隔
    is_active = take.status in _ACTIVE_PHASES
    bitrate = _compute_avg_bitrate(capture_take_id, take_file_size, is_active)

    # 有效帧率（take 级）：当前无实时诊断来源，按状态返回 collecting/unavailable
    effective_fps = _compute_take_effective_fps(track_statuses, take.status)

    # 目标配置：从源录制会话查询
    target_fps, target_width, target_height = _lookup_target_config(take)

    # elapsed_ms / duration_ms
    elapsed_ms = _compute_elapsed_ms(take)

    # 同步状态
    sync = _build_sync_status(take, tracks)

    recording = RecordingMetrics(
        phase=take.status.value,
        started_at=_ensure_utc(take.started_at),
        elapsed_ms=elapsed_ms,
        duration_ms=take.duration_ms if take.status in _TERMINAL_PHASES else None,
        target_fps=target_fps,
        target_width=target_width,
        target_height=target_height,
        file_size_bytes=take_file_size,
        effective_fps=effective_fps,
        avg_bitrate_bps=bitrate,
    )

    return CaptureTakeRuntimeStatus(
        capture_take_id=take.id,
        capture_mode=take.capture_mode.value,
        storage=storage,
        recording=recording,
        tracks=track_statuses,
        sync=sync,
        updated_at=datetime.now(UTC),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 轨道级指标
# ─────────────────────────────────────────────────────────────────────────────


def _build_track_status(
    track: CaptureTrack,
    fragments: list[MediaFragment],
) -> TrackRuntimeStatus:
    """构建单轨运行状态：文件大小、有效帧率、阶段、错误信息。"""
    file_size = _compute_track_file_size(fragments)
    effective_fps = _compute_track_effective_fps(fragments)
    phase = _derive_track_phase(fragments)
    error = _derive_track_error(fragments)

    return TrackRuntimeStatus(
        track_id=track.id,
        slot=track.slot.value,
        camera_id=track.camera_id,
        phase=phase,
        file_size_bytes=file_size,
        effective_fps=effective_fps,
        error=error,
    )


def _compute_track_file_size(fragments: list[MediaFragment]) -> MetricValue:
    """计算单轨文件大小：已完成分片用 DB 字段，活动分片用 os.stat。"""
    counted = [f for f in fragments if f.status in _COUNTED_FRAGMENT_STATUSES]
    if not counted:
        return MetricValue(state="ready", value=0.0)

    total = 0
    stat_errors: list[str] = []
    for frag in counted:
        # 已完成分片：DB 已写入 file_size
        if frag.status == FragmentStatus.completed and frag.file_size is not None:
            total += frag.file_size
            continue

        # 活动分片（starting/recording）：os.stat 读取实时大小
        if not frag.file_path:
            stat_errors.append(f"fragment {frag.id} 缺少 file_path")
            continue
        try:
            total += os.stat(frag.file_path).st_size
        except OSError as exc:
            stat_errors.append(f"fragment {frag.id}: {exc}")

    if stat_errors:
        # 部分活动分片不可读：返回 error 并附带可读原因
        return MetricValue(
            state="error",
            value=float(total) if total > 0 else None,
            message="; ".join(stat_errors[:2]),  # 最多 2 条避免过长
        )
    return MetricValue(state="ready", value=float(total))


def _compute_track_effective_fps(fragments: list[MediaFragment]) -> MetricValue:
    """计算单轨有效帧率。

    当前录制链路没有实时帧率诊断来源（MediaFragment 不持久化帧数）。
    按状态返回：
    - 有活动分片 → collecting（采集中，尚未产生结果）
    - 仅终态分片 → unavailable（无诊断数据）
    - 无分片 → collecting（刚启动）
    """
    if not fragments:
        return MetricValue(state="collecting")

    has_active = any(f.status in (FragmentStatus.starting, FragmentStatus.recording) for f in fragments)
    if has_active:
        return MetricValue(state="collecting")

    return MetricValue(state="unavailable", message="当前录制链路暂无有效帧率诊断来源")


def _derive_track_phase(fragments: list[MediaFragment]) -> str:
    """从分片状态推断轨道阶段。"""
    if not fragments:
        return "starting"
    statuses = {f.status for f in fragments}
    if statuses & {FragmentStatus.starting, FragmentStatus.recording}:
        return "recording"
    if FragmentStatus.failed in statuses and FragmentStatus.completed not in statuses:
        return "failed"
    if FragmentStatus.interrupted in statuses and FragmentStatus.completed not in statuses:
        return "interrupted"
    return "completed"


def _derive_track_error(fragments: list[MediaFragment]) -> str | None:
    """提取轨道级可读错误（来自失败分片的 error_message）。"""
    for frag in fragments:
        if frag.status in (FragmentStatus.failed, FragmentStatus.interrupted) and frag.error_message:
            return frag.error_message
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Take 级聚合
# ─────────────────────────────────────────────────────────────────────────────


def _aggregate_take_file_size(
    track_results: list[tuple[TrackRuntimeStatus, int | None]],
) -> MetricValue:
    """聚合 take 级文件大小：所有 ready 轨道之和；任一 error 则标记 error。"""
    if not track_results:
        return MetricValue(state="ready", value=0.0)

    error_messages: list[str] = []
    total = 0
    has_ready = False
    for _status, size in track_results:
        if size is None:
            # 该轨道非 ready（error/collecting/unavailable），收集错误信息
            continue
        total += size
        has_ready = True

    # 检查是否有 error 轨道
    for status, _ in track_results:
        if status.file_size_bytes.state == "error" and status.file_size_bytes.message:
            error_messages.append(f"{status.slot}: {status.file_size_bytes.message}")

    if error_messages and not has_ready:
        return MetricValue(state="error", message="; ".join(error_messages[:2]))
    if error_messages:
        # 部分轨道 error，但有 ready 轨道：返回 ready 值并附带警告
        return MetricValue(
            state="ready",
            value=float(total),
            message="部分轨道文件大小不可读: " + "; ".join(error_messages[:1]),
        )
    return MetricValue(state="ready", value=float(total))


def _compute_take_effective_fps(
    track_statuses: list[TrackRuntimeStatus],
    take_status: CaptureTakeStatus,
) -> MetricValue:
    """聚合 take 级有效帧率。

    当前无实时帧率诊断：活跃 → collecting，终态 → unavailable。
    """
    if take_status in _ACTIVE_PHASES:
        return MetricValue(state="collecting")
    return MetricValue(state="unavailable", message="当前录制链路暂无有效帧率诊断来源")


def _compute_elapsed_ms(take: CaptureTake) -> int | None:
    """计算已录制毫秒数：活跃状态用 now - started_at，终态用 duration_ms。"""
    if take.started_at is None:
        return None
    if take.status in _TERMINAL_PHASES:
        return take.duration_ms
    started = _ensure_utc(take.started_at)
    now = datetime.now(UTC)
    return max(0, int((now - started).total_seconds() * 1000))


# ─────────────────────────────────────────────────────────────────────────────
# 存储容量
# ─────────────────────────────────────────────────────────────────────────────


def _compute_storage_capacity(
    session_dir: str | None,
    storage_root: str | None,
) -> StorageCapacity:
    """基于会话目录所在文件系统读取容量。

    spec 要求：不得读取默认录制目录代替实际目录。
    - session_dir 存在 → 读取其所在文件系统
    - session_dir 缺失 → unavailable（不回退到默认目录）
    - 读取失败 → error + 可读原因
    """
    if not session_dir:
        return StorageCapacity(
            state="unavailable",
            message="CaptureTake 尚未绑定会话目录",
        )

    # 优先用 session_dir；若可访问，读取其所在文件系统容量
    target_path = session_dir
    try:
        path = Path(target_path)
        # 目录可能尚未创建（如刚 starting），向上找到存在的祖先目录
        probe = path
        while not probe.exists():
            if probe.parent == probe:
                # 到达根目录仍不存在，视为不可访问
                return StorageCapacity(
                    state="error",
                    message=f"会话目录路径不可访问：{target_path}",
                )
            probe = probe.parent
        usage = shutil.disk_usage(probe)
        return StorageCapacity(
            state="ready",
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
        )
    except OSError as exc:
        return StorageCapacity(
            state="error",
            message=f"读取存储容量失败：{exc}",
        )
    except Exception as exc:  # pragma: no cover - 防御性兜底
        return StorageCapacity(
            state="error",
            message=f"存储容量查询异常：{exc}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 平均写入码率
# ─────────────────────────────────────────────────────────────────────────────


def _compute_avg_bitrate(
    capture_take_id: str,
    take_file_size: MetricValue,
    is_active: bool,
) -> MetricValue:
    """基于最近两次快照间隔计算平均写入码率（bps）。

    设计：进程内缓存上一次快照的 (file_size, monotonic_sec)。
    - 首次请求：unavailable（无基线）
    - 文件大小为 error：error
    - 间隔过短（<0.5s）：返回上次值或 unavailable
    - 终态：返回最后一次 ready 值或 unavailable（不再更新缓存）
    """
    if take_file_size.state == "error":
        return MetricValue(state="error", message=take_file_size.message)
    if take_file_size.value is None:
        return MetricValue(state="unavailable", message="文件大小未知")

    current_size = int(take_file_size.value)
    now_mono = time.monotonic()
    previous = _bitrate_samples.get(capture_take_id)

    if previous is None:
        # 首次请求：建立基线，返回 unavailable
        if is_active:
            _bitrate_samples[capture_take_id] = _BitrateSample(
                file_size_bytes=current_size,
                monotonic_sec=now_mono,
            )
        return MetricValue(state="unavailable", message="尚无基线快照，等待下次轮询")

    delta_bytes = current_size - previous.file_size_bytes
    delta_sec = now_mono - previous.monotonic_sec

    # 更新基线（即使本次返回 unavailable 也更新，便于下次计算）
    if is_active:
        _bitrate_samples[capture_take_id] = _BitrateSample(
            file_size_bytes=current_size,
            monotonic_sec=now_mono,
        )

    if delta_sec < _BITRATE_MIN_WINDOW_SEC:
        # 间隔过短，码率不可靠
        return MetricValue(state="unavailable", message="采样间隔过短")
    if delta_bytes < 0:
        # 文件大小回退（可能分片被清理），不返回负码率
        return MetricValue(state="unavailable", message="文件大小异常回退")

    bitrate_bps = (delta_bytes * 8) / delta_sec
    return MetricValue(state="ready", value=bitrate_bps)


def reset_bitrate_sample(capture_take_id: str) -> None:
    """清除指定 take 的码率采样缓存（测试用，或终态后释放内存）。"""
    _bitrate_samples.pop(capture_take_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# 同步状态
# ─────────────────────────────────────────────────────────────────────────────


def _build_sync_status(
    take: CaptureTake,
    tracks: list[CaptureTrack],
) -> SyncRuntimeStatus | None:
    """构建同步状态摘要。

    - 单摄：sync 为 None（spec 允许）
    - 双摄：dual_sync 基于 CaptureTrack.sync_quality；event_sync 暂为 ready
      （事件 outbox 状态由 live_coding 管理，运行状态接口不重复查询 outbox）
    """
    is_dual = take.capture_mode.value == "dual"
    if not is_dual:
        return None

    # dual_sync：基于轨道 sync_quality 推断
    # - 所有轨道 good → ready
    # - 任一 degraded → collecting（降级但仍在同步）
    # - 任一 unknown → collecting
    # 缺少轨道信息时 → unavailable
    if not tracks:
        return SyncRuntimeStatus(
            dual_sync="unavailable",
            event_sync="ready",
            message="缺少轨道信息",
        )

    qualities = {t.sync_quality for t in tracks}
    if SyncQuality.good in qualities and not (qualities - {SyncQuality.good}):
        dual_sync: MetricAvailability = "ready"
        dual_quality = "good"
    elif SyncQuality.degraded in qualities:
        dual_sync = "collecting"
        dual_quality = "degraded"
    else:
        dual_sync = "collecting"
        dual_quality = "unknown"

    return SyncRuntimeStatus(
        dual_sync=dual_sync,
        dual_sync_quality=dual_quality,
        event_sync="ready",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 目标配置查询
# ─────────────────────────────────────────────────────────────────────────────


def _lookup_target_config(
    take: CaptureTake,
) -> tuple[float | None, int | None, int | None]:
    """从源录制会话查询目标 fps 和分辨率。

    返回 (target_fps, target_width, target_height)。
    查询失败或会话不存在时返回 (None, None, None)。
    """
    try:
        if take.source_session_type.value == "recording":
            from app.camera.session_service import session_service

            session = session_service.get_session(take.source_session_id)
            if session is None:
                return None, None, None
            fps = float(session.fps) if session.fps else None
            width, height = _parse_resolution(session.resolution)
            return fps, width, height

        if take.source_session_type.value == "sync_recording":
            from app.camera.sync_recorder_service import sync_recording_service

            session = sync_recording_service.get_session(take.source_session_id)
            if session is None:
                return None, None, None
            fps = float(session.fps) if session.fps else None
            width, height = _parse_resolution(session.resolution)
            return fps, width, height
    except Exception:
        # 目标配置查询失败不应导致整个快照失败
        return None, None, None

    return None, None, None


def _parse_resolution(resolution: str | None) -> tuple[int | None, int | None]:
    """解析 '1920x1080' 格式的分辨率字符串。"""
    if not resolution or "x" not in resolution:
        return None, None
    try:
        w_str, h_str = resolution.lower().split("x", 1)
        return int(w_str), int(h_str)
    except (ValueError, IndexError):
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """确保 datetime 带 UTC 时区信息。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
