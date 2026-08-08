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
import os
import shutil
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings


class StorageService:
    """本地文件存储助手，用于 MVP 阶段的上传视频与 JSON 产物管理。"""

    _capture_job_roots: dict[str, Path] = {}

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

    def write_json(self, path: Path, payload: dict[str, Any]) -> Path:
        # 普通写 JSON：先建目录，再写文件（ensure_ascii=False 保留中文）
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def register_capture_job(cls, job_id: str, session_dir: str | Path) -> None:
        root = Path(session_dir).expanduser().resolve() / "analysis" / job_id
        root.mkdir(parents=True, exist_ok=True)
        cls._capture_job_roots[job_id] = root

    @classmethod
    def register_capture_job_from_take(cls, job_id: str, capture_take_id: str) -> Path | None:
        """Restore a capture job's artifact root from the SQLite CaptureTake index."""
        try:
            from app.database import get_session_factory
            from app.models.capture_take import CaptureTake

            db = get_session_factory()()
            try:
                take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
                if not take or not take.session_dir:
                    return None
                cls.register_capture_job(job_id, take.session_dir)
                return cls._capture_job_roots[job_id]
            finally:
                db.close()
        except Exception:
            return None

    @classmethod
    def unregister_capture_job(cls, job_id: str) -> None:
        cls._capture_job_roots.pop(job_id, None)

    @classmethod
    def capture_job_root(cls, job_id: str) -> Path | None:
        return cls._capture_job_roots.get(job_id)

    def resolve_capture_job_root(self, job_id: str, capture_take_id: str | None = None) -> Path | None:
        root = self._capture_job_roots.get(job_id)
        if root:
            return root
        if capture_take_id:
            return self.register_capture_job_from_take(job_id, capture_take_id)
        return None

    def _job_artifact_root(self, job_id: str) -> Path:
        return self._capture_job_roots.get(job_id, self.outputs_dir / job_id)

    def logical_artifact_reference(self, job_id: str, path: str | Path | None) -> str | None:
        """Return a stable logical reference without exposing a local absolute path."""
        if path is None:
            return None
        root = self.capture_job_root(job_id)
        if root is None:
            return str(path)
        candidate = Path(path).expanduser().resolve(strict=False)
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            return str(path)
        return f"analysis/{job_id}/{relative.as_posix()}"

    def publicize_pipeline_result(self, result):
        """Replace capture artifact filesystem paths with logical references."""
        from app.schemas.pipeline import AnalysisArtifacts

        if self.capture_job_root(result.job_id) is None:
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
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
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
        if path.is_dir():
            shutil.rmtree(path)
            return True
        path.unlink()
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
        capture_root = self._capture_job_roots.get(job_id)
        return (capture_root / "result.json") if capture_root else self.outputs_dir / f"{job_id}.json"

    def job_json_path(self, job_id: str) -> Path:
        # 任务状态摘要 JSON（jobs 子目录）
        return self.outputs_dir / "jobs" / f"{job_id}.json"

    def jobs_dir(self) -> Path:
        # 所有任务摘要所在的目录
        return self.outputs_dir / "jobs"

    def report_json_path(self, job_id: str) -> Path:
        # 前端展示用报告 JSON
        return self.outputs_dir / "reports" / f"{job_id}.json"

    def tracking_json_path(self, job_id: str) -> Path:
        # 跟踪结果 JSON（每个 job 一个独立子目录）
        return self._job_artifact_root(job_id) / "tracking_result.json"

    def calibration_diagnostics_json_path(self, job_id: str) -> Path:
        return self._job_artifact_root(job_id) / "calibration_diagnostics.json"

    def tracking_overlay_json_path(self, job_id: str) -> Path:
        # 检测叠加（每一帧检测框）JSON
        return self._job_artifact_root(job_id) / "tracking_overlay.json"

    def player_selection_json_path(self, job_id: str) -> Path:
        # 主球员选择结果 JSON
        return self._job_artifact_root(job_id) / "player_selection.json"

    def player_selection_training_samples_json_path(self, job_id: str) -> Path:
        # 主球员选择用于训练的样本 JSON
        return self._job_artifact_root(job_id) / "player_selection_training_samples.json"

    def ball_overlay_json_path(self, job_id: str) -> Path:
        # 球的检测叠加 JSON
        return self._job_artifact_root(job_id) / "ball_overlay.json"

    def detections_jsonl_path(self, job_id: str) -> Path:
        # 原始检测结果（JSON Lines，每行一条）
        return self._job_artifact_root(job_id) / "detections.jsonl"

    def ball_trajectory_json_path(self, job_id: str) -> Path:
        # 球轨迹 JSON
        return self._job_artifact_root(job_id) / "ball_trajectory.json"

    def cleaned_ball_trajectory_json_path(self, job_id: str) -> Path:
        # 清洗后的球轨迹 JSON
        return self._job_artifact_root(job_id) / "cleaned_ball_trajectory.json"

    def bounce_events_json_path(self, job_id: str) -> Path:
        # 球弹跳事件 JSON
        return self._job_artifact_root(job_id) / "bounce_events.json"

    def reconstructed_ball_trajectory_json_path(self, job_id: str) -> Path:
        # 事件切分重建球轨迹 JSON（第三套数据）
        return self._job_artifact_root(job_id) / "reconstructed_ball_trajectory.json"

    def analysis_overlay_video_path(self, job_id: str) -> Path:
        # 分析叠加视频（mp4）
        return self._job_artifact_root(job_id) / "analysis_overlay.mp4"

    def position_visualizations_dir(self, job_id: str) -> Path:
        # 位置可视化目录（热力图、散点图都在其下）
        return self._job_artifact_root(job_id) / "position_visualizations"

    def heatmaps_dir(self, job_id: str) -> Path:
        # 热力图目录
        return self.position_visualizations_dir(job_id) / "heatmaps"

    def scatter_plots_dir(self, job_id: str) -> Path:
        # 散点图目录
        return self.position_visualizations_dir(job_id) / "scatter_plots"

    def structured_visualization_data_dir(self, job_id: str) -> Path:
        # 结构化可视化数据目录（JSON，供前端 SVG 渲染）
        return self.position_visualizations_dir(job_id) / "structured"

    def structured_visualization_data_path(self, job_id: str) -> Path:
        # 结构化可视化数据 JSON 文件路径
        return self.structured_visualization_data_dir(job_id) / "data.json"

    def heatmaps_manifest_json_path(self, job_id: str) -> Path:
        # 热力图清单（索引）JSON
        return self.heatmaps_dir(job_id) / "manifest.json"

    def scatter_plots_manifest_json_path(self, job_id: str) -> Path:
        # 散点图清单（索引）JSON
        return self.scatter_plots_dir(job_id) / "manifest.json"

    def pose_overlay_json_path(self, job_id: str) -> Path:
        # 姿态骨架叠加 JSON
        return self._job_artifact_root(job_id) / "pose_overlay.json"

    def serve_events_json_path(self, job_id: str) -> Path:
        # 发球开始事件 JSON
        return self._job_artifact_root(job_id) / "serve_events.json"

    def serve_debug_candidates_json_path(self, job_id: str) -> Path:
        # 发球候选调试 JSON
        return self._job_artifact_root(job_id) / "serve_debug_candidates.json"

    def serve_score_series_json_path(self, job_id: str) -> Path:
        # 发球评分时间序列 JSON
        return self._job_artifact_root(job_id) / "serve_score_series.json"

    def serve_clips_manifest_json_path(self, job_id: str) -> Path:
        # 发球片段导出清单 JSON
        return self._job_artifact_root(job_id) / "serve_clips_manifest.json"

    def serve_debug_overlay_video_path(self, job_id: str) -> Path:
        # 发球调试叠加视频
        return self._job_artifact_root(job_id) / "serve_debug_overlay.mp4"

    def serve_clips_dir(self, job_id: str) -> Path:
        # 发球片段（mp4）目录
        return self._job_artifact_root(job_id) / "serve_clips"

    def player_trajectory_json_path(self, job_id: str) -> Path:
        # 球员轨迹 JSON
        return self._job_artifact_root(job_id) / "players_trajectory.json"

    def player_trajectory_csv_path(self, job_id: str) -> Path:
        # 球员轨迹 CSV（方便用 Excel 打开）
        return self._job_artifact_root(job_id) / "players_trajectory.csv"

    def player_render_trajectory_path(self, job_id: str) -> Path:
        # 渲染轨迹 JSON（逐帧坐标，仅用于小地图视频）
        return self._job_artifact_root(job_id) / "player_render_trajectory.json"

    def fused_trajectory_json_path(self, job_id: str) -> Path:
        # 多视角融合球员轨迹 JSON（Composer 发布到 Parent artifact 命名空间）
        return self._job_artifact_root(job_id) / "fused_player_trajectory.json"

    def fusion_diagnostics_json_path(self, job_id: str) -> Path:
        # 多视角融合诊断 JSON（融合质量指标）
        return self._job_artifact_root(job_id) / "fused_diagnostics.json"

    def fusion_manifest_json_path(self, job_id: str) -> Path:
        # 多视角产物清单 JSON（Parent 唯一产品出口，前端据此消费）
        return self._job_artifact_root(job_id) / "fused_manifest.json"

    def court_view_roi_json_path(self, job_id: str) -> Path:
        # 球场视角与检测 ROI（感兴趣区域）JSON
        return self._job_artifact_root(job_id) / "court_view_roi.json"

    def video_metadata_path(self, video_id: str) -> Path:
        # 视频元数据 JSON（放在 uploads_dir）
        return self.uploads_dir / f"{video_id}.json"

    def calibration_json_path(self, calibration_id: str) -> Path:
        # 标定结果 JSON
        return self.calibrations_dir / f"{calibration_id}.json"

    def preview_image_path(self, calibration_id: str) -> Path:
        # 标定预览图（png）
        return self.outputs_dir / f"{calibration_id}-preview.png"

    def automatic_calibration_preview_path(self, suggestion_id: str) -> Path:
        # 自动标定建议预览图
        return self.outputs_dir / "calibration-previews" / f"{suggestion_id}.png"
