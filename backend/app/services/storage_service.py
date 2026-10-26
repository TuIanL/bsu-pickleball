"""本地文件存储服务 —— 管理上传视频、JSON 产物、标定文件和临时文件的读写。

这个服务不碰任何"业务逻辑"，它只负责：
1. 把所有数据落到磁盘上的某个目录；
2. 给每种产物（视频、标定、跟踪结果、报告……）提供统一、固定的文件路径。

这样上层代码（video_service、analysis_pipeline 等）就不用关心"文件到底放哪"，
只要调用 `storage.xxx_path(job_id)` 拿到路径即可。

`Settings` 来自 app.core.config，里面集中了所有目录配置。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path, PureWindowsPath
from typing import Any

from app.core.config import Settings, get_settings
from app.services.analysis_run_trace import TRACE_FILE_NAME

logger = logging.getLogger(__name__)


class CaptureSessionResolutionError(RuntimeError):
    """CaptureTake lookup or storage resolution failed; callers may degrade locally."""

    def __init__(self, reason_code: str, message: str = "CaptureTake session directory is unavailable") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class StorageService:
    """本地文件存储助手，用于 MVP 阶段的上传视频与 JSON 产物管理。"""

    _capture_job_roots: dict[str, Path] = {}
    _capture_job_session_dirs: dict[str, Path] = {}
    _capture_job_degradation: dict[str, str] = {}
    _capture_job_roots_lock = threading.RLock()

    def __init__(self, settings: Settings | None = None) -> None:
        # 没传就用全局配置；settings.ensure_data_dirs() 会确保各目录已创建
        self.settings = settings or get_settings()
        self.settings.ensure_data_dirs()

    @property
    def uploads_dir(self) -> Path:
        # 上传视频存放目录
        return self.settings.resolved_uploads_dir

    @property
    def outputs_dir(self) -> Path:
        # 分析产物（JSON、图片、视频）根目录
        return self.settings.resolved_outputs_dir

    @property
    def calibrations_dir(self) -> Path:
        # 标定文件目录
        return self.settings.resolved_calibrations_dir

    @property
    def tmp_dir(self) -> Path:
        # 临时文件目录
        return self.settings.resolved_tmp_dir

    @staticmethod
    def _safe_join(root: str | Path, *parts: str | Path) -> Path:
        """Join an artifact path and reject traversal, absolute injection, and symlink escape."""
        safe_root = Path(root).expanduser().resolve(strict=False)
        for part in parts:
            segment = Path(part)
            if segment.is_absolute() or ".." in segment.parts:
                raise ValueError("Artifact path escapes its authorized root")
        candidate = safe_root.joinpath(*parts).resolve(strict=False)
        try:
            candidate.relative_to(safe_root)
        except ValueError as exc:
            raise ValueError("Artifact path escapes its authorized root") from exc
        return candidate

    def write_json(self, path: Path, payload: dict[str, Any]) -> Path:
        # 普通写 JSON：先建目录，再写文件（ensure_ascii=False 保留中文）
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def register_capture_job(cls, job_id: str, session_dir: str | Path) -> Path:
        session_root = Path(session_dir).expanduser().resolve()
        if not session_root.is_dir():
            raise CaptureSessionResolutionError("capture_storage_unavailable")
        with cls._capture_job_roots_lock:
            existing = cls._capture_job_roots.get(job_id)
            if existing is not None:
                if cls._capture_job_session_dirs.get(job_id) != session_root:
                    raise CaptureSessionResolutionError("capture_session_changed")
                return existing
            root = cls._safe_join(session_root, "analysis", job_id)
            root.mkdir(parents=True, exist_ok=True)
            cls._capture_job_session_dirs.setdefault(job_id, session_root)
            cls._capture_job_roots.setdefault(job_id, root)
            cls._capture_job_degradation.pop(job_id, None)
            return cls._capture_job_roots[job_id]

    @classmethod
    def register_capture_job_from_take(cls, job_id: str, capture_take_id: str) -> Path | None:
        """Restore a capture root; return ``None`` only for a valid empty session_dir."""
        with cls._capture_job_roots_lock:
            existing = cls._capture_job_roots.get(job_id)
            if existing is not None:
                session_root = cls._capture_job_session_dirs.get(job_id)
                if session_root is not None and session_root.is_dir():
                    return existing
                raise CaptureSessionResolutionError("capture_storage_unavailable")
            session_root = cls._read_capture_session_dir(capture_take_id)
            if session_root is None:
                return None
            return cls.register_capture_job(job_id, session_root)

    @classmethod
    def unregister_capture_job(cls, job_id: str) -> None:
        with cls._capture_job_roots_lock:
            cls._capture_job_roots.pop(job_id, None)
            cls._capture_job_session_dirs.pop(job_id, None)
            cls._capture_job_degradation.pop(job_id, None)

    @classmethod
    def capture_job_root(cls, job_id: str) -> Path | None:
        with cls._capture_job_roots_lock:
            if job_id in cls._capture_job_degradation:
                return None
            return cls._capture_job_roots.get(job_id)

    @classmethod
    def capture_job_degradation_reason(cls, job_id: str) -> str | None:
        with cls._capture_job_roots_lock:
            return cls._capture_job_degradation.get(job_id)

    def _mark_capture_job_degraded(self, job_id: str, reason_code: str, exc: Exception | None = None) -> None:
        with self._capture_job_roots_lock:
            self._capture_job_degradation.setdefault(job_id, reason_code)
            marker = self._safe_join(self._degraded_artifact_root(job_id), ".storage.json")
            self.write_json_atomic(marker, {"status": "degraded", "reason": self._capture_job_degradation[job_id]})
        logger.warning(
            "Capture artifact storage degraded for job %s (%s)",
            job_id,
            reason_code,
            exc_info=(type(exc), exc, exc.__traceback__) if exc is not None else None,
        )

    def _restore_degraded_root(self, job_id: str) -> bool:
        """Keep a degraded job readable after restart or storage reconnection.

        The directory is authoritative even for older jobs without a marker. Never
        move an existing degraded result back to an empty external root implicitly.
        """
        root = self._degraded_artifact_root(job_id)
        if not root.is_dir():
            return False
        reason = "capture_storage_unavailable"
        marker = self._safe_join(root, ".storage.json")
        if marker.is_file():
            try:
                payload = self.read_json(marker)
                if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
                    reason = payload["reason"]
            except (OSError, ValueError):
                logger.warning("Unable to read degraded storage marker for job %s", job_id, exc_info=True)
        self._capture_job_degradation.setdefault(job_id, reason)
        return True

    def resolve_capture_job_root(self, job_id: str, capture_take_id: str | None = None) -> Path | None:
        with self._capture_job_roots_lock:
            self._restore_degraded_root(job_id)
            reason = self._capture_job_degradation.get(job_id)
            if reason is not None:
                return self._degraded_artifact_root(job_id)
            root = self._capture_job_roots.get(job_id)
            if root is not None:
                session_root = self._capture_job_session_dirs.get(job_id)
                if session_root is not None and not session_root.is_dir():
                    self._mark_capture_job_degraded(job_id, "capture_storage_unavailable")
                    return self._degraded_artifact_root(job_id)
                return root
            if capture_take_id:
                try:
                    root = self.register_capture_job_from_take(job_id, capture_take_id)
                except CaptureSessionResolutionError as exc:
                    self._mark_capture_job_degraded(job_id, exc.reason_code, exc)
                    return self._degraded_artifact_root(job_id)
                if root is not None:
                    return root
            return None

    def _degraded_artifact_root(self, job_id: str) -> Path:
        return self._safe_join(self.outputs_dir, "_degraded", job_id)

    def _job_artifact_root(self, job_id: str) -> Path:
        with self._capture_job_roots_lock:
            self._restore_degraded_root(job_id)
            if job_id in self._capture_job_degradation:
                return self._degraded_artifact_root(job_id)
            root = self._capture_job_roots.get(job_id)
            if root is not None:
                session_root = self._capture_job_session_dirs.get(job_id)
                if session_root is not None and not session_root.is_dir():
                    self._mark_capture_job_degraded(job_id, "capture_storage_unavailable")
                    return self._degraded_artifact_root(job_id)
                return root
            return self._safe_join(self.outputs_dir, job_id)

    def _artifact_path(self, job_id: str, *parts: str | Path) -> Path:
        return self._safe_join(self._job_artifact_root(job_id), *parts)

    @classmethod
    def _read_capture_session_dir(cls, capture_take_id: str) -> Path | None:
        """只读解析 CaptureTake 的 `session_dir`。

        刻意**不**调用 `register_capture_job`：那个方法会 `mkdir`，在外接存储
        未挂载时会抛异常并被吞掉，从而把调用方静默引向本地目录。
        """
        try:
            from app.database import get_session_factory
            from app.models.capture_take import CaptureTake

            db = get_session_factory()()
            try:
                take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
                if take is None:
                    raise CaptureSessionResolutionError("capture_take_not_found")
                if not take.session_dir:
                    return None
                session_root = Path(take.session_dir).expanduser().resolve()
                if not session_root.is_dir():
                    raise CaptureSessionResolutionError("capture_storage_unavailable")
                return session_root
            finally:
                db.close()
        except CaptureSessionResolutionError:
            raise
        except Exception as exc:
            raise CaptureSessionResolutionError("capture_session_lookup_failed") from exc

    def resolve_run_trace_path(self, job_id: str, capture_take_id: str | None = None) -> Path:
        """分析运行轨迹的位置：与其余产物同址，且跨进程可解析。

        正式采集任务的产物根位于外接存储（`<session_dir>/analysis/<job_id>`）。
        Worker 是独立进程，内存里的 `_capture_job_roots` 注册表不一定存在，因此
        这里按 CaptureTake 的 `session_dir` 回源解析。

        CaptureTake 或会话目录无法解析时，统一切到独立降级根；调用方可读取降级原因，
        避免静默混入普通本地任务目录。
        """
        with self._capture_job_roots_lock:
            registered = self._capture_job_roots.get(job_id)
        if registered is not None:
            root = self.resolve_capture_job_root(job_id, capture_take_id)
            if root is not None:
                return self._safe_join(root, TRACE_FILE_NAME)
        if capture_take_id:
            root = self.resolve_capture_job_root(job_id, capture_take_id)
            if root is not None:
                return self._safe_join(root, TRACE_FILE_NAME)
        return self._artifact_path(job_id, TRACE_FILE_NAME)

    def formal_segmentation_artifact_path(
        self, job_id: str, capture_take_id: str | None = None, *, create_root: bool = True
    ) -> Path:
        """Deterministic formal artifact location; candidate namespace is never used."""
        root = (
            self.resolve_capture_job_root(job_id, capture_take_id)
            if capture_take_id
            else self._job_artifact_root(job_id)
        )
        root = root or self._safe_join(self.outputs_dir, job_id)
        if create_root:
            root.mkdir(parents=True, exist_ok=True)
        return self._safe_join(root, "match_state_segmentation.json")

    def logical_artifact_reference(self, job_id: str, path: str | Path | None) -> str | None:
        """Return a stable logical reference without exposing a local absolute path."""
        if path is None:
            return None
        root = self.capture_job_root(job_id)
        prefix = f"analysis/{job_id}"
        if root is None and self.capture_job_degradation_reason(job_id):
            root = self._degraded_artifact_root(job_id)
            prefix = f"degraded/{job_id}"
        if root is None:
            root = self._safe_join(self.outputs_dir, job_id)
        candidate = Path(path).expanduser().resolve(strict=False)
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            return str(path)
        return f"{prefix}/{relative.as_posix()}"

    def logical_run_trace_reference(self, job_id: str, path: str | Path) -> str:
        """Reuse artifact references, with a stable fallback for unavailable targets."""
        reference = self.logical_artifact_reference(job_id, path)
        if reference and not Path(reference).is_absolute() and not PureWindowsPath(reference).is_absolute():
            return reference
        prefix = "degraded" if self.capture_job_degradation_reason(job_id) else "analysis"
        return f"{prefix}/{job_id}/{TRACE_FILE_NAME}"

    def publicize_pipeline_result(self, result):
        """Replace capture artifact filesystem paths with logical references."""
        from app.schemas.pipeline import AnalysisArtifacts

        if (
            self.capture_job_root(result.job_id) is None
            and self.capture_job_degradation_reason(result.job_id) is None
        ):
            return result
        fields = result.artifacts.model_dump()
        for name, value in fields.items():
            if name.endswith("_path") and value:
                fields[name] = self.logical_artifact_reference(result.job_id, value)
        return result.model_copy(update={"artifacts": AnalysisArtifacts.model_validate(fields)})

    def write_json_atomic(self, path: Path, payload: dict[str, Any]) -> Path:
        # 原子写 JSON：先写临时文件，再用 os.replace 整体替换，
        # 避免写到一半进程崩溃导致文件损坏（保证要么旧、要么新，不会半截）。
        path.parent.mkdir(parents=True, exist_ok=True)
        # API 与 external analysis-worker 可能同时刷新同一个兼容快照。
        # 临时文件名必须是每次写入唯一的；固定的 ``.name.tmp`` 会让一个
        # 写入者替换/删除另一个写入者的临时文件，最终在 os.replace 处抛
        # FileNotFoundError，并可能连带杀掉 Worker 的 heartbeat 线程。
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(6):
                try:
                    os.replace(tmp_path, path)
                    break
                except PermissionError as exc:
                    # Concurrent readers/writers can temporarily deny DELETE
                    # sharing on Windows. Keep the unique temporary file and
                    # bound the retry rather than failing the worker heartbeat.
                    if os.name != "nt" or getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 5:
                        raise
                    time.sleep(0.01 * (attempt + 1))
        except Exception:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise
        return path

    def read_json(self, path: Path) -> dict[str, Any]:
        # 读取并解析 JSON 文件
        return json.loads(path.read_text(encoding="utf-8"))

    def write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> Path:
        # 写入 JSON Lines：每行一个 JSON 对象（逐帧检测/球轨迹等共享合同）。
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False))
                handle.write("\n")
        return path

    def read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        # 读取 JSON Lines，返回逐行解析后的对象列表
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    @staticmethod
    def delete_path(path: Path) -> bool:
        # 删除一个文件或目录（目录用递归删除）；不存在则视为"已删除成功"
        if not path.exists():
            return False
        from app.analysis_runtime.retention import assert_unpinned
        assert_unpinned(get_settings(), path)
        if path.is_dir():
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                # macOS 可能在递归删除期间生成/移除 ._ 元数据文件；重试并忽略
                # 同一目录内已消失的条目，保证删除接口具备幂等性。
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)
            return True
        try:
            path.unlink()
        except FileNotFoundError:
            return True
        return True

    @staticmethod
    def delete_path_tree(path: Path) -> bool:
        # 与 delete_path 等价（保留别名，语义更明确：删除整棵树）
        return StorageService.delete_path(path)

    # ------------------------------------------------------------------
    # 下面是一组"路径构造器"：给定 job_id / video_id 等，返回固定路径。
    # 用统一的方法生成路径，能保证"写"和"读"用的路径永远一致。
    # ------------------------------------------------------------------

    def output_json_path(self, job_id: str) -> Path:
        # 整个分析任务的汇总结果 JSON
        with self._capture_job_roots_lock:
            use_job_root = job_id in self._capture_job_roots or job_id in self._capture_job_degradation
        if use_job_root:
            return self._safe_join(self._job_artifact_root(job_id), "result.json")
        return self._safe_join(self.outputs_dir, f"{job_id}.json")

    def artifact_attempt_marker_path(self, job_id: str) -> Path:
        """Marker hiding a result while an execution attempt is incomplete."""
        result_path = self.output_json_path(job_id)
        return self._safe_join(result_path.parent, f".{result_path.name}.incomplete")

    def begin_artifact_attempt(self, job_id: str, *, attempt: int, stage: str) -> None:
        """Hide stale result data and mark the current attempt incomplete."""
        result_path = self.output_json_path(job_id)
        marker_path = self.artifact_attempt_marker_path(job_id)
        self.write_json_atomic(
            marker_path,
            {"job_id": job_id, "attempt": attempt, "stage": stage, "status": "incomplete"},
        )
        try:
            result_path.unlink()
        except FileNotFoundError:
            pass

    def complete_artifact_attempt(self, job_id: str) -> None:
        """Publish the result by removing its incomplete marker."""
        marker_path = self.artifact_attempt_marker_path(job_id)
        try:
            marker_path.unlink()
        except FileNotFoundError:
            pass

    def artifact_attempt_is_incomplete(self, job_id: str) -> bool:
        return self.artifact_attempt_marker_path(job_id).exists()

    def job_json_path(self, job_id: str) -> Path:
        # 任务状态摘要 JSON（jobs 子目录）
        return self._safe_join(self.outputs_dir, "jobs", f"{job_id}.json")

    def jobs_dir(self) -> Path:
        # 所有任务摘要所在的目录
        return self._safe_join(self.outputs_dir, "jobs")

    def report_json_path(self, job_id: str) -> Path:
        # 前端展示用报告 JSON
        return self._safe_join(self.outputs_dir, "reports", f"{job_id}.json")

    def tracking_json_path(self, job_id: str) -> Path:
        # 跟踪结果 JSON（每个 job 一个独立子目录）
        return self._artifact_path(job_id, "tracking_result.json")

    def calibration_diagnostics_json_path(self, job_id: str) -> Path:
        return self._artifact_path(job_id, "calibration_diagnostics.json")

    def tracking_overlay_json_path(self, job_id: str) -> Path:
        # 检测叠加（每一帧检测框）JSON
        return self._artifact_path(job_id, "tracking_overlay.json")

    def player_selection_json_path(self, job_id: str) -> Path:
        # 主球员选择结果 JSON
        return self._artifact_path(job_id, "player_selection.json")

    def player_selection_training_samples_json_path(self, job_id: str) -> Path:
        # 主球员选择用于训练的样本 JSON
        return self._artifact_path(job_id, "player_selection_training_samples.json")

    def ball_overlay_json_path(self, job_id: str) -> Path:
        # 球的检测叠加 JSON
        return self._artifact_path(job_id, "ball_overlay.json")

    def detections_jsonl_path(self, job_id: str) -> Path:
        # 原始检测结果（JSON Lines，每行一条）
        return self._artifact_path(job_id, "detections.jsonl")

    def ball_trajectory_json_path(self, job_id: str) -> Path:
        # 球轨迹 JSON
        return self._artifact_path(job_id, "ball_trajectory.json")

    def cleaned_ball_trajectory_json_path(self, job_id: str) -> Path:
        # 清洗后的球轨迹 JSON
        return self._artifact_path(job_id, "cleaned_ball_trajectory.json")

    def bounce_events_json_path(self, job_id: str) -> Path:
        # 球弹跳事件 JSON
        return self._artifact_path(job_id, "bounce_events.json")

    def reconstructed_ball_trajectory_json_path(self, job_id: str) -> Path:
        # 事件切分重建球轨迹 JSON（第三套数据）
        return self._artifact_path(job_id, "reconstructed_ball_trajectory.json")

    def ball_semantic_timeline_json_path(self, job_id: str) -> Path:
        # 比赛语义驱动球搜索策略诊断（Shadow/Enforced 共用）
        return self._artifact_path(job_id, "ball_semantic_timeline.json")

    def ball_semantic_boundary_eval_json_path(self, job_id: str) -> Path:
        # 语义回合边界校准评估（证据账本、边界事件与指标）
        return self._artifact_path(job_id, "ball_semantic_boundary_eval.json")

    def multiview_ball_stereo_evidence_path(self, job_id: str) -> Path:
        # 多视角球立体证据 JSON（不可变原始证据，v1）
        return self._artifact_path(job_id, "multiview_ball_stereo_evidence.json")

    def analysis_overlay_video_path(self, job_id: str) -> Path:
        # 分析叠加视频（mp4）
        return self._artifact_path(job_id, "analysis_overlay.mp4")

    def position_visualizations_dir(self, job_id: str) -> Path:
        # 位置可视化目录（热力图、散点图都在其下）
        return self._artifact_path(job_id, "position_visualizations")

    def heatmaps_dir(self, job_id: str) -> Path:
        # 热力图目录
        return self._safe_join(self.position_visualizations_dir(job_id), "heatmaps")

    def scatter_plots_dir(self, job_id: str) -> Path:
        # 散点图目录
        return self._safe_join(self.position_visualizations_dir(job_id), "scatter_plots")

    def structured_visualization_data_dir(self, job_id: str) -> Path:
        # 结构化可视化数据目录（JSON，供前端 SVG 渲染）
        return self._safe_join(self.position_visualizations_dir(job_id), "structured")

    def structured_visualization_data_path(self, job_id: str) -> Path:
        # 结构化可视化数据 JSON 文件路径
        return self._safe_join(self.structured_visualization_data_dir(job_id), "data.json")

    def roster_manifest_json_path(self, job_id: str) -> Path:
        # global-player-roster.v1（诊断 / 映射 contract）
        return self._artifact_path(job_id, "roster.json")

    def fused_player_overlay_json_path(self, job_id: str) -> Path:
        # multiview-fused-player-overlay.v1（joint 模式正式球员叠加层）
        return self._artifact_path(job_id, "fused_player_overlay.json")

    def player_display_diagnostics_json_path(self, job_id: str) -> Path:
        # player-display-diagnostics.v1（joint 模式逐球员逐 stage 显示漏斗）
        return self._artifact_path(job_id, "player_display_diagnostics.json")

    def four_player_identification_quality_json_path(self, job_id: str) -> Path:
        return self._artifact_path(job_id, "four_player_identification_quality.json")

    def bootstrap_display_backfill_json_path(self, job_id: str) -> Path:
        # bootstrap_display_backfill.v1（joint 启动阶段展示回填，display-only 旁路产物）
        return self._artifact_path(job_id, "bootstrap_display_backfill.json")

    def heatmaps_manifest_json_path(self, job_id: str) -> Path:
        # 热力图清单（索引）JSON
        return self._safe_join(self.heatmaps_dir(job_id), "manifest.json")

    def scatter_plots_manifest_json_path(self, job_id: str) -> Path:
        # 散点图清单（索引）JSON
        return self._safe_join(self.scatter_plots_dir(job_id), "manifest.json")

    def pose_overlay_json_path(self, job_id: str) -> Path:
        # 姿态骨架叠加 JSON
        return self._artifact_path(job_id, "pose_overlay.json")

    def serve_events_json_path(self, job_id: str) -> Path:
        # 发球开始事件 JSON
        return self._artifact_path(job_id, "serve_events.json")

    def serve_debug_candidates_json_path(self, job_id: str) -> Path:
        # 发球候选调试 JSON
        return self._artifact_path(job_id, "serve_debug_candidates.json")

    def bootstrap_binding_audit_json_path(self, job_id: str) -> Path:
        # bootstrap anchor → 正式 canonical Player 的绑定审计
        return self._artifact_path(job_id, "bootstrap_binding_audit.json")

    def bootstrap_binding_audit_conflict_json_path(self, job_id: str) -> Path:
        # 7.3：Rally/Shot 派生审计与权威审计的逐槽位分歧（不覆盖权威文件）
        return self._artifact_path(job_id, "bootstrap_binding_audit_conflict.json")

    def serve_score_series_json_path(self, job_id: str) -> Path:
        # 发球评分时间序列 JSON
        return self._artifact_path(job_id, "serve_score_series.json")

    def serve_clips_manifest_json_path(self, job_id: str) -> Path:
        # 发球片段导出清单 JSON
        return self._artifact_path(job_id, "serve_clips_manifest.json")

    def serve_debug_overlay_video_path(self, job_id: str) -> Path:
        # 发球调试叠加视频
        return self._artifact_path(job_id, "serve_debug_overlay.mp4")

    def serve_clips_dir(self, job_id: str) -> Path:
        # 发球片段（mp4）目录
        return self._artifact_path(job_id, "serve_clips")

    def player_trajectory_json_path(self, job_id: str) -> Path:
        # 球员轨迹 JSON
        return self._artifact_path(job_id, "players_trajectory.json")

    def performance_insights_json_path(self, job_id: str) -> Path:
        # performance-insights.v1（表现洞察事实层，post-pipeline 可独立再生成）
        return self._artifact_path(job_id, "performance_insights.json")

    def shot_rally_events_json_path(self, job_id: str) -> Path:
        # shot-rally-events.v1（canonical Rally/Shot 事实层）
        return self._artifact_path(job_id, "shot_rally_events.json")

    def shot_landings_json_path(self, job_id: str) -> Path:
        # shot-landings.v1（canonical Shot 的首次正式落点事实）
        return self._artifact_path(job_id, "shot_landings.json")

    def metric_snapshot_json_path(self, job_id: str) -> Path:
        # metric-snapshot.v1（分母感知描述性指标）
        return self._artifact_path(job_id, "metric_snapshot.json")

    def kitchen_arrival_json_path(self, job_id: str) -> Path:
        # kitchen-arrival.v1（发球队厨房线到位事实）
        return self._artifact_path(job_id, "kitchen_arrival.json")

    def normalized_metrics_json_path(self, job_id: str) -> Path:
        # normalized-metric-snapshot.v1（规范化指标与评分资格中间层）
        return self._artifact_path(job_id, "normalized_metrics.json")

    def player_trajectory_csv_path(self, job_id: str) -> Path:
        # 球员轨迹 CSV（方便用 Excel 打开）
        return self._artifact_path(job_id, "players_trajectory.csv")

    def player_render_trajectory_path(self, job_id: str) -> Path:
        # 渲染轨迹 JSON（逐帧坐标，仅用于小地图视频）
        return self._artifact_path(job_id, "player_render_trajectory.json")

    def fused_trajectory_json_path(self, job_id: str) -> Path:
        # 多视角融合球员轨迹 JSON（Composer 发布到 Parent artifact 命名空间）
        return self._artifact_path(job_id, "fused_player_trajectory.json")

    def fusion_diagnostics_json_path(self, job_id: str) -> Path:
        # 多视角融合诊断 JSON（融合质量指标）
        return self._artifact_path(job_id, "fused_diagnostics.json")

    def fusion_manifest_json_path(self, job_id: str) -> Path:
        # 多视角产物清单 JSON（Parent 唯一产品出口，前端据此消费）
        return self._artifact_path(job_id, "fused_manifest.json")

    def multiview_run_dir(self, job_id: str, run_id: str) -> Path:
        """Return the immutable run directory owned by a multiview parent."""
        # Joint/fusion runs are siblings of the parent job artifact root:
        # `<capture>/analysis/multiview/<run_id>` or `<outputs>/multiview/<run_id>`.
        analysis_root = self._job_artifact_root(job_id).parent
        return self._safe_join(analysis_root, "multiview", run_id)

    def recovery_episodes_json_path(self, job_id: str, run_id: str) -> Path:
        return self._safe_join(self.multiview_run_dir(job_id, run_id), "recovery_episodes.v1.json")

    def joint_debug_summary_json_path(self, job_id: str, run_id: str) -> Path:
        return self._safe_join(self.multiview_run_dir(job_id, run_id), "joint_debug_summary.v1.json")

    def canonical_debug_video_path(self, job_id: str, run_id: str) -> Path:
        return self._safe_join(self.multiview_run_dir(job_id, run_id), "canonical_debug.mp4")

    def court_view_roi_json_path(self, job_id: str) -> Path:
        # 球场视角与检测 ROI（感兴趣区域）JSON
        return self._artifact_path(job_id, "court_view_roi.json")

    def video_metadata_path(self, video_id: str) -> Path:
        # 视频元数据 JSON（放在 uploads_dir）
        return self._safe_join(self.uploads_dir, f"{video_id}.json")

    def calibration_json_path(self, calibration_id: str) -> Path:
        # 标定结果 JSON
        return self._safe_join(self.calibrations_dir, f"{calibration_id}.json")

    def metric_court_scene_root(self, take_dir: str | Path) -> Path:
        """CaptureTake-scoped scene calibration directory."""
        return self._safe_join(take_dir, "metadata", "metric-court-scene")

    def metric_court_scene_draft_path(self, take_dir: str | Path) -> Path:
        return self._safe_join(self.metric_court_scene_root(take_dir), "draft.json")

    def metric_court_scene_current_path(self, take_dir: str | Path) -> Path:
        return self._safe_join(self.metric_court_scene_root(take_dir), "current.json")

    def metric_court_scene_revision_path(self, take_dir: str | Path, revision: int) -> Path:
        return self._safe_join(self.metric_court_scene_root(take_dir), "revisions", f"revision-{revision}.json")

    def preview_image_path(self, calibration_id: str) -> Path:
        # 标定预览图（png）
        return self._safe_join(self.outputs_dir, f"{calibration_id}-preview.png")

    def automatic_calibration_preview_path(self, suggestion_id: str) -> Path:
        # 自动标定建议预览图
        return self._safe_join(self.outputs_dir, "calibration-previews", f"{suggestion_id}.png")
