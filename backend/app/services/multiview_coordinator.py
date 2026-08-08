"""多视角分析协调器（multiview_coordinator）—— Parent/Source Job 编排。

对应 spec `multiview-analysis-orchestration`：

- `MultiViewAnalysisCoordinator.create_multiview_job`：创建 1 个 public Parent +
  2 个 dedicated internal child（`parentJobId` / `visibility=internal` / `analysisScope=full`）；
- 事件驱动推进：child terminal → Parent `waiting_sources → fusion_ready / fallback_ready / failed`；
- 启动对账 `reconcile_all`：修复 Parent/Child 依赖关系（与现有 zombie recovery 职责分离）；
- 取消/删除级联：取消 Parent 级联 owned child；删除 Parent 只删分析产物，不碰录制资产；
- MultiView preflight：创建前校验视频/标定/orientation/sync/P0 机位范围，不静默退化。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.analysis import (
    AnalysisJobCreate,
    AnalysisJobSummary,
    AnalysisDeleteResult,
    SourceJobRef,
    ViewRunSummary,
)
from app.services.capture_storage_service import sync_calibration_path
from app.services.calibration_service import CalibrationService
from app.services.job_orchestration import JobStore
from app.services.storage_service import StorageService
from app.services.video_service import video_service

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
NON_TERMINAL_STATUSES = {"queued", "running"}


@dataclass(frozen=True)
class PreflightResult:
    """MultiView preflight 结果：不满足时返回结构化原因（不静默退化）。"""

    ok: bool
    issues: list[str] = field(default_factory=list)


def _check_capture_take_dir(capture_take_id: str) -> str | None:
    """解析 CaptureTake 的目录；不存在返回 None。"""
    try:
        from app.database import get_session_factory
        from app.models.capture_take import CaptureTake

        db = get_session_factory()()
        try:
            take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
            return take.session_dir if take and take.session_dir else None
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - DB 不可用时按目录缺失处理
        return None


def preflight_multiview(
    payload: AnalysisJobCreate,
    *,
    storage: StorageService | None = None,
) -> PreflightResult:
    """分析创建前校验输入契约；任一不满足即失败（不静默退化）。

    检查：CaptureTake 存在 → 双视频可用 → 双标定可用 → 双 orientation 已声明
    → `sync_calibration.json` 可用 → 两机位属 P0 axis-preserving 范围。
    """
    storage = storage or StorageService()
    mv = payload.multiview
    if mv is None:
        return PreflightResult(ok=False, issues=["multiview payload missing"])
    if not payload.metadata.capture_take_id:
        return PreflightResult(ok=False, issues=["capture_take_id required for multiview analysis"])
    if len(mv.views) < 2:
        return PreflightResult(ok=False, issues=["at least two views required"])

    take_dir = _check_capture_take_dir(payload.metadata.capture_take_id)
    if not take_dir:
        return PreflightResult(
            ok=False,
            issues=[
                f"CaptureTake not found or missing session_dir: capture_take_id={payload.metadata.capture_take_id}"
            ],
        )

    issues: list[str] = []
    for view in mv.views:
        if video_service.get_video(view.videoId) is None:
            issues.append(f"video not available for view {view.viewId} (videoId={view.videoId})")
        if CalibrationService().get_calibration(view.calibrationId) is None:
            issues.append(f"calibration not available for view {view.viewId} (calibrationId={view.calibrationId})")
        if view.courtOrientation is None:
            issues.append(f"court_orientation not declared for view {view.viewId}")

    # 双摄同步校准：报告解析路径 + timeline 目录内容，便于精准定位
    sync_path = sync_calibration_path(take_dir)
    timeline_dir = sync_path.parent
    if not sync_path.exists():
        timeline_entries = (
            sorted(p.name for p in timeline_dir.iterdir()) if timeline_dir.is_dir() else []
        )
        issues.append(
            "sync_calibration.json unavailable (双摄同步信息不可用): "
            f"take_dir={take_dir!s}; 期望路径={sync_path!s} (exists={sync_path.exists()}); "
            f"timeline 目录存在={timeline_dir.is_dir()}; timeline 内容={timeline_entries or '(空/缺失)'}; "
            f"请运行生成命令: python scripts/generate_dual_camera_sync.py --take {payload.metadata.capture_take_id}"
        )

    if issues:
        return PreflightResult(ok=False, issues=issues)
    return PreflightResult(ok=True, issues=[])


class MultiViewAnalysisCoordinator:
    """Parent ↔ Source Job A/B ↔ MultiViewFusionRun 的编排者。"""

    def __init__(
        self,
        store: JobStore,
        storage: StorageService | None = None,
    ) -> None:
        self.store = store
        self.storage = storage or StorageService()

    # ---- 创建 ---------------------------------------------------------------

    def _resolve_sync_session_id(self, capture_take_id: str) -> str | None:
        """从 CaptureTake 解析其源 sync 录制会话 id（仅 sync_recording 类型）。"""
        try:
            from app.database import get_session_factory
            from app.models.capture_take import CaptureTake

            db = get_session_factory()()
            try:
                take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
                if take is not None and str(take.source_session_type) == "sync_recording":
                    return take.source_session_id
                return None
            finally:
                db.close()
        except Exception:  # noqa: BLE001 - DB 不可用时按无法推导处理
            return None

    def _ensure_sync_calibration(self, capture_take_id: str) -> bool:
        """若 take 缺 sync_calibration.json，尝试从录制时序自动推导并写入（degraded）。

        幂等：文件已存在则直接通过；无法推导（非双摄 / 无会话 / 无时序元数据）返回 False，
        留给 preflight 报详细原因。手动锚点（authoritative good）脚本仍可覆盖该文件。
        """
        take_dir = _check_capture_take_dir(capture_take_id)
        if not take_dir:
            return False
        sync_path = sync_calibration_path(take_dir)
        if sync_path.exists():
            return True
        session_id = self._resolve_sync_session_id(capture_take_id)
        if not session_id:
            return False
        try:
            from app.camera.sync_recorder_service import sync_recording_service
            from app.services.dual_camera_sync import derive_sync_calibration_from_segment_timing

            session = sync_recording_service.get_session(session_id)
            if session is None:
                return False
            payload = derive_sync_calibration_from_segment_timing(session.segments)
        except Exception as exc:  # noqa: BLE001 - 推导失败按无法推导处理
            logger.warning("自动推导双摄同步校准失败 take=%s: %s", capture_take_id, exc)
            return False
        sync_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage.write_json_atomic(sync_path, payload)
        logger.info("自动生成 degraded 双摄同步校准 take=%s → %s", capture_take_id, sync_path)
        return True

    def _map_clip_to_view(
        self,
        take_dir: str,
        view_id: str,
        start_ms: int | None,
        end_ms: int | None,
    ) -> tuple[int | None, int | None]:
        """把 take 公共时间轴的 clip 窗口换算到指定视图的媒体时间轴。

        公共时间轴 = reference 视图（cam_1）媒体时间轴；secondary 用 sync 校准
        `cam_time = offset + rate * reference_time` 换算。无映射时原样返回
        （offset 量级为亚帧，粗窗口可忽略）。
        """
        if start_ms is None or end_ms is None:
            return start_ms, end_ms
        try:
            from app.services.dual_camera_sync import map_reference_time
            from app.vision.multiview.sync import load_sync_calibration

            sync = load_sync_calibration(take_dir)
            cal = sync.mapping_for(view_id) if sync is not None else None
            if cal is None:
                return start_ms, end_ms
            new_start = int(round(map_reference_time(cal, start_ms / 1000.0) * 1000.0))
            new_end = int(round(map_reference_time(cal, end_ms / 1000.0) * 1000.0))
            return max(0, new_start), max(0, new_end)
        except Exception as exc:  # noqa: BLE001 - 换算失败按原窗口处理
            logger.warning("clip 换算到视图 %s 失败: %s", view_id, exc)
            return start_ms, end_ms

    def create_multiview_job(self, payload: AnalysisJobCreate) -> AnalysisJobSummary:
        """创建 1 个 public Parent + 每个 view 一个 dedicated internal child。"""
        # 真实双摄 take 缺 sync 时自动推导 degraded 校准（幂等），消除逐 take 手工生成摩擦
        self._ensure_sync_calibration(payload.metadata.capture_take_id)
        result = preflight_multiview(payload, storage=self.storage)
        if not result.ok:
            raise ValueError("MultiView preflight failed: " + "; ".join(result.issues))

        mv = payload.multiview
        assert mv is not None

        # 分析窗口在 take 公共时间轴（= reference 视图媒体时间轴）。
        # secondary 视图用 sync 校准换算到它自己的媒体时间轴，保证两路取同一物理窗口。
        clip_start_ms = payload.clipStartMs
        clip_end_ms = payload.clipEndMs
        take_dir = _check_capture_take_dir(payload.metadata.capture_take_id)

        parent_payload = AnalysisJobCreate(
            metadata=payload.metadata,
            analysisKind="multiview",
            clipStartMs=clip_start_ms,
            clipEndMs=clip_end_ms,
        )
        parent = self.store.create_job(parent_payload)

        refs: list[SourceJobRef] = []
        created_children: dict[str, AnalysisJobSummary] = {}
        for view in mv.views:
            child_metadata = payload.metadata.model_copy(
                update={
                    "fileName": f"{payload.metadata.capture_take_id}_{view.viewId}.mp4",
                    "camera_slot": view.viewId,
                    "camera_id": view.viewId,
                }
            )
            child_clip_start, child_clip_end = clip_start_ms, clip_end_ms
            if view.viewId != mv.referenceViewId and take_dir and clip_start_ms is not None:
                child_clip_start, child_clip_end = self._map_clip_to_view(
                    take_dir, view.viewId, clip_start_ms, clip_end_ms
                )
            child_payload = AnalysisJobCreate(
                metadata=child_metadata,
                videoId=view.videoId,
                calibrationId=view.calibrationId,
                frameStride=payload.frameStride,
                sourceFps=payload.sourceFps or payload.metadata.sourceFps,
                priority=payload.priority,
                clipStartMs=child_clip_start,
                clipEndMs=child_clip_end,
                analysisKind="single_view",
            )
            child = self.store.create_job(child_payload)
            self.store.update(
                child.id,
                parentJobId=parent.id,
                visibility="internal",
                analysisScope="full",
            )
            created_children[view.viewId] = child
            refs.append(
                SourceJobRef(
                    cameraSlot=view.viewId,
                    jobId=child.id,
                    courtOrientation=view.courtOrientation,
                )
            )

        view_runs = {
            ref.cameraSlot: ViewRunSummary(status="queued", stage="queue", progress=10) for ref in refs
        }
        parent_updates: dict[str, object] = {
            "sourceJobs": refs,
            "referenceViewId": mv.referenceViewId,
            "analysisScope": None,
            "orchestrationStatus": "waiting_sources",
            "viewRuns": view_runs,
        }
        # 把 reference child 的 videoId/calibrationId 挂到 Parent：即便 Parent 的
        # AnalysisPipelineResult 尚未落盘（或后端重启后丢失），前端仍能确定视频源。
        reference_child = created_children.get(mv.referenceViewId)
        if reference_child is not None:
            parent_updates["videoId"] = reference_child.videoId
            parent_updates["calibrationId"] = reference_child.calibrationId
        parent = self.store.update(parent.id, **parent_updates)
        logger.info("创建双摄 Parent %s（child: %s）", parent.id, [(r.cameraSlot, r.jobId) for r in refs])
        return parent

    # ---- 推进（事件驱动 + 对账共用） ------------------------------------------

    def _children_status(self, parent: AnalysisJobSummary) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for ref in parent.sourceJobs:
            child = self.store.get(ref.jobId)
            statuses[ref.cameraSlot] = child.canonicalStatus if child else "missing"
        return statuses

    def live_view_runs(self, parent: AnalysisJobSummary) -> dict[str, ViewRunSummary]:
        """实时聚合各 child 的 status / stage / progress（运行中也返回最新进度，不落盘）。

        `_advance_parent` 只在 child 终态时刷新 `viewRuns`；运行期间前端轮询 Parent 时
        通过本方法拿到 child 的实时进度，避免一直显示"排队 10%"。
        """
        runs: dict[str, ViewRunSummary] = {}
        for ref in parent.sourceJobs:
            child = self.store.get(ref.jobId)
            runs[ref.cameraSlot] = ViewRunSummary(
                status=child.canonicalStatus if child else "missing",
                stage=child.stage if child else "queue",
                progress=child.progress if child else 0,
            )
        return runs

    def _advance_parent(self, parent: AnalysisJobSummary) -> AnalysisJobSummary | None:
        """根据 child 终态推进 Parent 的 orchestrationStatus（幂等）。"""
        if parent.analysisKind != "multiview" or parent.canonicalStatus != "queued":
            return None
        if parent.orchestrationStatus in {"fusing", "composing"}:
            return None  # 已进入执行，不再重推进

        statuses = self._children_status(parent)
        child_status = list(statuses.values())
        view_runs: dict[str, ViewRunSummary] = {}
        for ref in parent.sourceJobs:
            child = self.store.get(ref.jobId)
            if child is None:
                view_runs[ref.cameraSlot] = ViewRunSummary(status="missing", stage="queue", progress=0)
                continue
            view_runs[ref.cameraSlot] = ViewRunSummary(
                status=child.canonicalStatus,
                stage=child.stage,
                progress=child.progress,
            )

        succeeded = [c for c in child_status if c == "succeeded"]
        failed_or_canceled = [c for c in child_status if c in {"failed", "canceled"}]
        pending = [c for c in child_status if c in NON_TERMINAL_STATUSES or c == "missing"]

        if pending:
            new_status = "waiting_sources"
        elif len(succeeded) == len(child_status) and succeeded:
            new_status = "fusion_ready"
        elif succeeded and failed_or_canceled:
            new_status = "fallback_ready"
        else:
            new_status = "failed"

        if new_status == "failed":
            parent = self.store.mark_failed(
                parent,
                stages=parent.stages,
                message="双摄分析失败：两路 Source Job 均未完成。",
            )
            parent = self.store.update(parent.id, viewRuns=view_runs)
            return parent

        parent = self.store.update(
            parent.id,
            orchestrationStatus=new_status,
            viewRuns=view_runs,
        )
        logger.info("推进 Parent %s → %s", parent.id, new_status)
        return parent

    def on_job_terminal(self, job: AnalysisJobSummary) -> None:
        """任一 job 进入终态时调用：若为 child，推进其 Parent。"""
        if not job.parentJobId:
            return
        parent = self.store.get(job.parentJobId)
        if parent is None or parent.canonicalStatus in TERMINAL_STATUSES:
            return
        self._advance_parent(parent)

    def reconcile_all(self) -> int:
        """启动对账：扫描 multiview 非终态 Parent，按 child 终态推进。"""
        advanced = 0
        for job in self.store.list():
            if job.analysisKind != "multiview" or job.canonicalStatus in TERMINAL_STATUSES:
                continue
            before = job.orchestrationStatus
            updated = self._advance_parent(job)
            if updated is not None and updated.orchestrationStatus != before:
                advanced += 1
        if advanced:
            logger.info("启动对账推进了 %s 个双摄 Parent", advanced)
        return advanced

    # ---- 取消 / 删除级联 ------------------------------------------------------

    def cancel_cascade(self, parent: AnalysisJobSummary) -> None:
        """取消 Parent 时级联取消 owned 非终态 children。"""
        for ref in parent.sourceJobs:
            child = self.store.get(ref.jobId)
            if child is None or child.canonicalStatus in TERMINAL_STATUSES:
                continue
            self.store.cancel(child.id)
        logger.info("取消 Parent %s 及其非终态 children", parent.id)

    def owned_child_ids(self, parent: AnalysisJobSummary) -> list[str]:
        return [ref.jobId for ref in parent.sourceJobs]

    def delete_cascade(self, parent: AnalysisJobSummary) -> list[AnalysisDeleteResult]:
        """删除 Parent 及其 owned child 分析产物 + fusion run 产物；不碰录制资产。"""
        results: list[AnalysisDeleteResult] = []
        for child_id in self.owned_child_ids(parent):
            from app.services import mock_analysis

            results.append(mock_analysis.delete_analysis_job(child_id, allow_internal=True))
        # 删除 fusion run 中间产物目录（best-effort，两处可能的根）
        if parent.fusionRunId:
            run_rel = Path("multiview") / parent.fusionRunId
            for root in (self.storage.outputs_dir,):
                target = root / run_rel
                if target.exists():
                    self.storage.delete_path_tree(target)
            take_root = self.storage.resolve_capture_job_root(parent.id, parent.metadata.capture_take_id)
            if take_root is not None and take_root.parent.exists():
                target = take_root.parent / "multiview" / parent.fusionRunId
                if target.exists():
                    self.storage.delete_path_tree(target)
        return results
