"""CaptureRuntimeCoordinator —— 运行期轨道协调器"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.camera.recording_policy import (
    CoordinatorActionType, TrackRuntimeEvent, CaptureRuntimeSnapshot,
    TrackRuntimeState, RecordingPolicy, RESTART_BUDGET,
)
from app.camera.track_recorder import (
    TrackRecorder, FragmentStartSpec, FragmentExit, FragmentHandle,
)

logger = logging.getLogger(__name__)


@dataclass
class CaptureRuntimeOutcome:
    """录制运行期最终结果汇总"""
    stopped_by_user: bool = False              # 是否由用户主动停止
    primary_track_lost: bool = False           # 主轨道是否丢失
    unavailable_track_ids: list[str] = field(default_factory=list)  # 不可用轨道列表
    restart_budget_exhausted: bool = False     # 重启预算是否耗尽
    runtime_warnings: list[str] = field(default_factory=list)       # 运行时警告列表


@dataclass
class TrackRuntimeInfo:
    """单条轨道的运行时配置与状态"""
    track_id: str
    slot: str                        # 机位槽位：cam_1 / cam_2
    camera_id: str                   # 摄像头 ID
    analysis_role: str               # 分析角色：default / supplementary
    stream_url: str                  # RTSP 流地址
    output_dir: str                  # 输出目录
    fps: int = 60
    sync_to_host_clock: bool = False # 是否使用本机时钟同步
    fragment_index: int = 0          # 当前分段序号
    rotation_index: int = 0          # 轮转序号（重启后递增）
    restart_count: int = 0           # 累计重启次数
    is_running: bool = False         # 当前是否正在录制
    current_fragment_id: str = ""    # 当前分段 ID
    current_fragment_start_offset_ms: int = 0  # 当前分段在录制时间轴中的起始偏移


class CaptureRuntimeCoordinator:
    """运行期轨道协调器：管理多个 TrackRecorder 实例，根据故障策略自动恢复"""
    def __init__(self, fragment_repo=None, clock=None):
        self._fragment_repo = fragment_repo      # 片段仓储（可选）
        self._clock = clock                      # 时钟源（可选）
        self._tracks: dict[str, TrackRuntimeInfo] = {}    # 轨道 ID -> 运行时信息
        self._recorders: dict[str, TrackRecorder] = {}    # 轨道 ID -> TrackRecorder
        self._handles: dict[str, FragmentHandle] = {}     # 轨道 ID -> 当前分段句柄
        self._event_queue: queue.Queue[TrackRuntimeEvent] = queue.Queue()  # 事件队列
        self._policy: RecordingPolicy | None = None       # 故障恢复策略
        self._stopping = False                # 是否正在停止
        self._outcome = CaptureRuntimeOutcome()           # 最终结果
        self._take_id = ""                    # CaptureTake ID
        self._started_at_ms: int = 0          # 启动时的单调时钟（毫秒）

    def start_tracks(self, take_id: str, tracks_info: list[TrackRuntimeInfo],
                     policy: RecordingPolicy) -> None:
        """启动所有轨道的录制，注册故障策略并启动事件循环"""
        self._take_id = take_id
        self._policy = policy
        self._stopping = False
        self._outcome = CaptureRuntimeOutcome()
        self._started_at_ms = int(time.monotonic() * 1000) if not self._clock else self._clock.monotonic_ms()

        for info in tracks_info:
            self._tracks[info.track_id] = info
            self._recorders[info.track_id] = TrackRecorder()

        self._start_fragments_together([info.track_id for info in tracks_info])

        threading.Thread(target=self._event_loop, daemon=True).start()

    def _start_fragment_for_track(
        self,
        track_id: str,
        launch_barrier: threading.Barrier | None = None,
    ) -> FragmentHandle | None:
        """为指定轨道启动一个新的 FFmpeg 分段录制"""
        info = self._tracks[track_id]
        recorder = self._recorders[track_id]

        fid = f"frag_{uuid.uuid4().hex[:12]}"
        take_start_offset = int(time.monotonic() * 1000) - self._started_at_ms if self._started_at_ms else 0

        output_path = Path(info.output_dir) / f"{info.track_id}_s{info.fragment_index}.ts"

        if self._fragment_repo:
            try:
                self._fragment_repo.create_starting(
                    capture_take_id=self._take_id,
                    capture_track_id=track_id,
                    fragment_index=info.fragment_index,
                    rotation_index=info.rotation_index,
                    file_path=output_path,
                    take_start_offset_ms=take_start_offset,
                )
            except Exception as e:
                logger.warning("Fragment repo create failed: %s", e)

        spec = FragmentStartSpec(
            capture_take_id=self._take_id,
            capture_track_id=track_id,
            fragment_id=fid,
            camera_id=info.camera_id,
            stream_url=info.stream_url,
            output_path=output_path,
            fragment_index=info.fragment_index,
            rotation_index=info.rotation_index,
            take_start_offset_ms=take_start_offset,
            fps=info.fps,
            sync_to_host_clock=info.sync_to_host_clock,
        )

        info.current_fragment_id = fid
        info.current_fragment_start_offset_ms = take_start_offset
        info.is_running = True

        handle = recorder.start_fragment(
            spec,
            lambda exit_info: self._on_fragment_exit(track_id, exit_info),
            launch_barrier=launch_barrier,
        )
        return handle

    def _start_fragments_together(self, track_ids: list[str]) -> None:
        """Launch a group of FFmpeg processes at one software synchronization point."""
        if not track_ids:
            return
        if len(track_ids) == 1:
            handle = self._start_fragment_for_track(track_ids[0])
            if handle:
                self._handles[track_ids[0]] = handle
            return

        barrier = threading.Barrier(len(track_ids))
        handles: dict[str, FragmentHandle] = {}
        failures: list[tuple[str, Exception]] = []
        result_lock = threading.Lock()

        def start_one(track_id: str) -> None:
            try:
                handle = self._start_fragment_for_track(track_id, barrier)
                if handle:
                    with result_lock:
                        handles[track_id] = handle
            except Exception as exc:
                barrier.abort()
                with result_lock:
                    failures.append((track_id, exc))

        workers = [threading.Thread(target=start_one, args=(track_id,)) for track_id in track_ids]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        if failures:
            failed_track, error = failures[0]
            raise RuntimeError(f"failed to start track {failed_track}") from error
        self._handles.update(handles)

    def _on_fragment_exit(self, track_id: str, exit_info: FragmentExit) -> None:
        """回调：某个轨道的分段退出后，构造事件放入事件队列"""
        info = self._tracks.get(track_id)
        if not info:
            return
        info.is_running = False

        is_primary = info.analysis_role == "default"
        event = TrackRuntimeEvent(
            track_id=track_id,
            fragment_id=exit_info.fragment_id,
            is_primary=is_primary,
            unexpected=exit_info.unexpected,
            return_code=exit_info.return_code,
            restart_count=info.restart_count,
        )
        self._event_queue.put(event)

    def _event_loop(self) -> None:
        """后台事件循环：从队列取出事件，调用策略决策并执行动作"""
        while not self._stopping:
            try:
                event = self._event_queue.get(timeout=1)
            except queue.Empty:
                continue

            if self._stopping:
                break

            snapshot = self._build_snapshot()
            if self._policy:
                actions = self._policy.decide(event, snapshot)
            else:
                actions = []

            for action in actions:
                if self._stopping:
                    break
                self._execute_action(action)

    def _build_snapshot(self) -> CaptureRuntimeSnapshot:
        """构建当前所有轨道的状态快照供策略使用"""
        states = {}
        for tid, info in self._tracks.items():
            states[tid] = TrackRuntimeState(
                track_id=tid,
                is_primary=info.analysis_role == "default",
                is_running=info.is_running,
                restart_count=info.restart_count,
                fragment_index=info.fragment_index,
            )
        primary = next((tid for tid, info in self._tracks.items() if info.analysis_role == "default"), "")
        return CaptureRuntimeSnapshot(primary_track_id=primary, track_states=states)

    def _execute_action(self, action) -> None:
        """执行策略决策出的单个动作（停止全部 / 重启全部 / 重启失败轨道）"""
        if action.type == CoordinatorActionType.STOP_ALL:
            self._stop_all_recorders()
        elif action.type == CoordinatorActionType.RESTART_ALL:
            if action.delay_seconds > 0:
                time.sleep(action.delay_seconds)
            self._stop_all_recorders()
            if self._stopping:
                return
            self._increment_rotation()
            restartable_track_ids: list[str] = []
            for tid in action.track_ids:
                info = self._tracks.get(tid)
                if info:
                    info.fragment_index += 1
                    info.restart_count += 1
                    if info.restart_count >= RESTART_BUDGET:
                        self._outcome.restart_budget_exhausted = True
                        if info.analysis_role == "default":
                            self._outcome.primary_track_lost = True
                        self._outcome.unavailable_track_ids.append(tid)
                        continue
                    restartable_track_ids.append(tid)
            self._start_fragments_together(restartable_track_ids)
        elif action.type == CoordinatorActionType.RESTART_FAILED_TRACK:
            if action.delay_seconds > 0:
                time.sleep(action.delay_seconds)
            for tid in action.track_ids:
                info = self._tracks.get(tid)
                if info:
                    info.fragment_index += 1
                    info.restart_count += 1
                    if info.restart_count >= RESTART_BUDGET:
                        self._outcome.restart_budget_exhausted = True
                        self._outcome.unavailable_track_ids.append(tid)
                        if info.analysis_role == "default":
                            self._outcome.primary_track_lost = True
                        continue
                    self._start_fragment_for_track(tid)

    def _stop_all_recorders(self) -> None:
        """并行停止所有录制器"""
        self._request_stops_together(list(self._handles.values()), "coordinator_stop_all")

    @staticmethod
    def _request_stops_together(handles: list[FragmentHandle], reason: str) -> None:
        """并行向所有句柄发送停止请求"""
        def request_stop(handle: FragmentHandle) -> None:
            try:
                handle.request_stop(reason)
            except Exception:
                pass

        workers = [threading.Thread(target=request_stop, args=(handle,)) for handle in handles]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

    def _increment_rotation(self) -> None:
        """递增所有轨道的轮转序号（重启后文件不覆盖）"""
        for info in self._tracks.values():
            info.rotation_index += 1

    def stop_tracks(self) -> tuple[list[dict], CaptureRuntimeOutcome]:
        """停止所有轨道录制，返回分段信息列表和最终结果"""
        self._stopping = True
        self._outcome.stopped_by_user = True

        self._request_stops_together(list(self._handles.values()), "user_stopped")

        fragments = []
        for tid, handle in list(self._handles.items()):
            try:
                result = handle.wait(timeout=30)
                info = self._tracks.get(tid, TrackRuntimeInfo("", "", "", "", "", ""))
                fragments.append({
                    "track_id": tid,
                    "slot": info.slot,
                    "fragment_id": result.fragment_id,
                    "status": result.status,
                    "file_size": result.file_size,
                    "file_path": f"{info.output_dir}/{info.track_id}_s{info.fragment_index}.ts",
                    "fragment_index": info.fragment_index,
                    "rotation_index": info.rotation_index,
                    "restart_count": info.restart_count,
                    "take_start_offset_ms": self._tracks[tid].current_fragment_start_offset_ms,
                })
            except Exception as e:
                logger.warning("stop track %s failed: %s", tid, e)

        return fragments, self._outcome
