"""
分析任务接口路由（/api/analysis）

这是系统的核心业务接口。整体流程是：
前端创建"分析任务" → 后端在后台用视觉算法分析视频 →
前端通过这些接口轮询进度、读取结果和报告。

接口一览：
- POST   /jobs                          创建分析任务
- GET    /jobs                          列出所有任务
- DELETE /jobs/{job_id}                删除单个任务（含本地产物）
- POST   /jobs/delete                  批量删除任务
- GET    /jobs/{job_id}                读取任务详情/状态
- POST   /jobs/{job_id}/cancel         取消任务
- GET    /jobs/{job_id}/result         读取分析结果（未出结果则返回状态）
- GET    /jobs/{job_id}/report         读取分析报告
- GET    /jobs/{job_id}/artifacts/{name}  读取某个分析产物（overlay 等）

补充说明：当前任务的实际处理走的是 mock_analysis（模拟实现），
真实分析由 analysis_pipeline 负责编排；接口层只管接收请求、调用服务、返回数据。
"""

from __future__ import annotations

# Literal：限定某个参数只能取固定的几个字符串值（这里用于限定 artifact 名称白名单）
# Union：表示返回值"可能是多种类型之一"
# Query：URL 查询参数
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

# 不同的响应类型：
# - FileResponse：返回一个文件（如视频/图片）
# - JSONResponse：返回 JSON 数据
# - PlainTextResponse：返回纯文本（如按行存储的 JSONL 文件）
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

# 分析相关的数据模型
from app.schemas.analysis import (
    AnalysisDeleteRequest,  # 批量删除请求（含 job_ids 列表）
    AnalysisDeleteResult,  # 单个删除的结果
    AnalysisJobCreate,  # 创建任务的请求
    AnalysisJobSummary,  # 任务摘要/状态
    AnalysisReport,  # 面向用户的分析报告
)
from app.schemas.pipeline import AnalysisPipelineResult  # 分析流水线结果（含运动指标）

# 模拟分析服务：封装任务的增删查、取消、读取结果/报告等逻辑
from app.services.mock_analysis import (
    batch_delete_analysis_jobs,
    cancel_analysis_job,
    create_analysis_job,
    delete_analysis_job,
    get_mock_job,
    get_mock_report,
    get_pipeline_result,
    list_analysis_jobs,
)
from app.services.multiview_coordinator import MultiviewPreflightError
from app.services.multiview_observability import (
    MultiviewObservabilityProjector,
    structured_error,
)
from app.services.storage_service import StorageService

# 定义路由表，前缀 /api/analysis
router = APIRouter(prefix="/api/analysis", tags=["analysis"])
# 存储服务对象，用于定位各类分析产物（artifact）在磁盘上的路径
_STORAGE = StorageService()
_MULTIVIEW_OBSERVABILITY = MultiviewObservabilityProjector(_STORAGE)


def _multiview_error(status_code: int, code: str, message: str, job_id: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=structured_error(code, message, job_id=job_id))


def _iter_file_range(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _debug_video_response(path: Path, request: Request) -> StreamingResponse:
    size = path.stat().st_size
    range_header = request.headers.get("range")
    start, end = 0, max(0, size - 1)
    status_code = 200
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(size),
        "Content-Type": "video/mp4",
    }
    if range_header:
        try:
            unit, raw_range = range_header.split("=", 1)
            if unit != "bytes" or "," in raw_range:
                raise ValueError
            raw_start, raw_end = raw_range.split("-", 1)
            if raw_start:
                start = int(raw_start)
                end = int(raw_end) if raw_end else end
            else:
                suffix = int(raw_end)
                start = max(0, size - suffix)
            if start < 0 or start >= size or end < start:
                raise ValueError
            end = min(end, size - 1)
        except (ValueError, TypeError):
            return StreamingResponse(
                iter(()),
                status_code=416,
                headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"},
                media_type="video/mp4",
            )
        status_code = 206
        headers["Content-Length"] = str(end - start + 1)
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _iter_file_range(path, start, end),
        status_code=status_code,
        headers=headers,
        media_type="video/mp4",
    )


@router.post("/jobs", response_model=AnalysisJobSummary)
def create_analysis_job_route(payload: AnalysisJobCreate) -> AnalysisJobSummary:
    """
    创建分析任务

    前端提交视频 id、标定 id、分析参数后调用本接口。
    双摄任务（analysisKind=multiview）在此创建 1 个 Parent + 2 个内部 child。
    后端会记录任务，并返回它的 id 与初始状态（如 queued 排队中）。
    """
    try:
        return create_analysis_job(payload)
    except MultiviewPreflightError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "code": "multiview_preflight_failed",
                "message": str(exc),
                "issues": exc.issues,
                "diagnostics": exc.diagnostics,
            },
        )
    except ValueError as exc:
        # 双摄 preflight 不通过：返回结构化失败原因（不静默退化）
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs", response_model=list[AnalysisJobSummary])
def list_analysis_jobs_route(
    recording_session_id: str | None = Query(default=None, alias="recording_session_id"),
    include_internal: bool = Query(default=False, alias="include_internal"),
) -> list[AnalysisJobSummary]:
    """
    读取所有已知分析任务

    支持按录制 session 过滤：?recording_session_id=<sid>。
    默认只返回 visibility=public 的任务（internal child 隐藏）；include_internal=true 仅用于诊断。
    用于前端的"任务管理"页面，展示历史与当前任务列表。
    """
    jobs = list_analysis_jobs(include_internal=include_internal)
    if recording_session_id:
        jobs = [
            j
            for j in jobs
            if j.metadata.recording_session_id == recording_session_id or j.recordingSessionId == recording_session_id
        ]
    return jobs


@router.delete("/jobs/{job_id}", response_model=AnalysisDeleteResult)
def delete_analysis_job_route(job_id: str) -> AnalysisDeleteResult:
    """
    删除单个分析任务及其本地产物

    会同时删除任务记录，以及它在磁盘上的分析产物（overlay、报告等文件）。
    """
    return delete_analysis_job(job_id)


@router.post("/jobs/delete", response_model=list[AnalysisDeleteResult])
def delete_analysis_jobs_route(payload: AnalysisDeleteRequest) -> list[AnalysisDeleteResult]:
    """
    批量删除分析任务及其本地产物

    请求体里带一组 job_id，后端逐个删除并返回每个的删除结果。
    """
    return batch_delete_analysis_jobs(payload.job_ids)


@router.get("/jobs/{job_id}", response_model=AnalysisJobSummary)
def read_analysis_job(job_id: str) -> AnalysisJobSummary:
    """
    读取分析任务详情

    前端用本接口轮询任务状态（queued / processing / completed / failed），
    从而展示进度条或提示完成/失败。
    """
    job = get_mock_job(job_id)

    if job is None:
        # 任务不存在
        raise HTTPException(status_code=404, detail="Analysis job not found")

    return job


@router.post("/jobs/{job_id}/cancel", response_model=AnalysisJobSummary)
def cancel_analysis_job_route(job_id: str) -> AnalysisJobSummary:
    """
    请求取消排队中或运行中的分析任务
    """
    try:
        job = cancel_analysis_job(job_id)
    except ValueError as exc:
        # 内部 Source Job 不能被用户直接取消
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    return job


@router.get("/jobs/{job_id}/result", response_model=AnalysisPipelineResult | AnalysisJobSummary)
def read_analysis_result(job_id: str) -> AnalysisPipelineResult | AnalysisJobSummary:
    """
    读取分析结果

    如果结果（流水线产出的指标 JSON）已经生成，就直接返回结果；
    否则返回任务当前状态，让前端据此继续等待或提示失败。
    返回值类型用 Union 表示：可能是"结果"也可能是"状态摘要"。
    """
    job = get_mock_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    _STORAGE.resolve_capture_job_root(job_id, job.metadata.capture_take_id)

    result = get_pipeline_result(job_id)
    if result is not None:
        return result

    return job


@router.get("/jobs/{job_id}/report", response_model=AnalysisReport)
def read_analysis_report(job_id: str) -> AnalysisReport:
    """
    读取分析报告

    返回面向用户展示的分析报告（指标、训练建议等更易读的内容），
    比原始的 result JSON 更适合直接展示。
    """
    report = get_mock_report(job_id)

    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    return report


@router.get("/jobs/{job_id}/multiview/observability", response_model=None)
def read_multiview_observability(job_id: str) -> JSONResponse:
    """Return the product-level multiview observability projection."""
    job = get_mock_job(job_id)
    if job is None:
        return _multiview_error(404, "not_found", "Analysis job not found.", job_id)
    if job.analysisKind != "multiview":
        return _multiview_error(404, "not_applicable", "This analysis job is not multiview.", job_id)
    result = get_pipeline_result(job_id)
    try:
        return JSONResponse(_MULTIVIEW_OBSERVABILITY.project(job, result))
    except Exception as exc:  # noqa: BLE001 - keep a stable API error DTO
        return _multiview_error(500, "projection_unavailable", str(exc), job_id)


@router.get("/jobs/{job_id}/multiview/recovery-events", response_model=None)
def read_multiview_recovery_events(
    job_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    outcome: str | None = Query(default=None),
    global_player_id: str | None = Query(default=None),
    donor_view: str | None = Query(default=None),
    target_view: str | None = Query(default=None),
    from_ms: float | None = Query(default=None, ge=0),
    to_ms: float | None = Query(default=None, ge=0),
) -> JSONResponse:
    """Return published, aggregated recovery episodes, never raw runtime ticks."""
    job = get_mock_job(job_id)
    if job is None:
        return _multiview_error(404, "not_found", "Analysis job not found.", job_id)
    if job.analysisKind != "multiview":
        return _multiview_error(404, "not_applicable", "Recovery episodes are not applicable to this job.", job_id)
    if from_ms is not None and to_ms is not None and from_ms > to_ms:
        return _multiview_error(422, "invalid_time_range", "from_ms must be less than or equal to to_ms.", job_id)
    result = get_pipeline_result(job_id)
    summary = _MULTIVIEW_OBSERVABILITY.project(job, result)
    run_id = summary.get("run_id")
    page = _MULTIVIEW_OBSERVABILITY.episodes.list_episodes(
        job=job,
        run_id=run_id,
        cursor=cursor,
        limit=limit,
        outcome=outcome,
        global_player_id=global_player_id,
        donor_view=donor_view,
        target_view=target_view,
        from_ms=from_ms,
        to_ms=to_ms,
    )
    return JSONResponse(page)


@router.get("/jobs/{job_id}/multiview/debug-video", response_model=None)
def read_multiview_debug_video(job_id: str, request: Request) -> StreamingResponse | JSONResponse:
    """Stream the published canonical debug MP4 with HTTP Range support."""
    job = get_mock_job(job_id)
    if job is None:
        return _multiview_error(404, "not_found", "Analysis job not found.", job_id)
    if job.analysisKind != "multiview":
        return _multiview_error(404, "not_applicable", "Debug replay is not applicable to this job.", job_id)
    summary = _MULTIVIEW_OBSERVABILITY.project(job, get_pipeline_result(job_id))
    path = _MULTIVIEW_OBSERVABILITY.resolve_debug_video(job, summary.get("run_id"))
    if path is None:
        return _multiview_error(404, "unavailable", "This task has no published canonical debug video.", job_id)
    return _debug_video_response(path, request)


# 允许的 artifact（分析产物）名称白名单。
# 用 Literal 限定后，只有这些名字能被这个路由匹配，避免用户随意访问任意文件，更安全。
@router.get("/jobs/{job_id}/artifacts/{artifact_name}", response_model=None)
def read_analysis_artifact(
    job_id: str,
    artifact_name: Literal[
        "tracking-overlay",  # 轨迹叠加数据（JSON）
        "player-selection",  # 主球员筛选结果
        "player-selection-training-samples",  # 主球员筛选的训练样本
        "ball-overlay",  # 球的叠加数据
        "detections",  # 逐帧检测框（JSONL 文本）
        "ball-trajectory",  # 球轨迹
        "cleaned-ball-trajectory",  # 清洗后的球轨迹
        "bounce-events",  # 弹跳事件
        "reconstructed-ball-trajectory",  # 事件切分重建球轨迹
        "analysis-overlay-video",  # 分析叠加视频（mp4 文件）
        "position-heatmaps",  # 位置热力图清单
        "position-scatter-plots",  # 位置散点图清单
        "pose-overlay",  # 姿态骨架叠加
        "player-trajectories",  # 球员轨迹
        "player-render-trajectories",  # 渲染轨迹（逐帧坐标，仅用于小地图）
        "fused-trajectory",  # 多视角融合球员轨迹（Parent 命名空间产物）
        "fusion-diagnostics",  # 多视角融合诊断（融合质量）
        "fused-manifest",  # 多视角产物清单（Parent 唯一产品出口）
        "serve-events",  # 发球事件
        "serve-debug-candidates",  # 发球候选（调试用）
        "serve-score-series",  # 发球评分序列
        "serve-clips-manifest",  # 发球片段清单
        "serve-debug-overlay",  # 发球调试叠加视频
        "court-view-roi",  # 场地视角 ROI（感兴趣区域）
        "calibration-diagnostics",  # 标定质量诊断
    ],
) -> JSONResponse | FileResponse | PlainTextResponse:
    """
    读取浏览器可消费的分析 overlay 产物

    根据 artifact 名称，到磁盘找到对应的产物文件并返回。
    不同产物返回类型不同：视频返回文件、检测记录返回纯文本、其余返回 JSON。
    """
    # 先确认任务存在，不存在就直接报错
    job = get_mock_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    _STORAGE.resolve_capture_job_root(job_id, job.metadata.capture_take_id)

    # 下面一大段 if / elif 就是：根据 artifact 名称，
    # 用存储服务（_STORAGE）拼出对应的磁盘文件路径。
    # 每一种产物在 _STORAGE 里都有专门的路径方法。
    if artifact_name == "tracking-overlay":
        path = _STORAGE.tracking_overlay_json_path(job_id)
    elif artifact_name == "player-selection":
        path = _STORAGE.player_selection_json_path(job_id)
    elif artifact_name == "player-selection-training-samples":
        path = _STORAGE.player_selection_training_samples_json_path(job_id)
    elif artifact_name == "ball-overlay":
        path = _STORAGE.ball_overlay_json_path(job_id)
    elif artifact_name == "detections":
        path = _STORAGE.detections_jsonl_path(job_id)
    elif artifact_name == "ball-trajectory":
        path = _STORAGE.ball_trajectory_json_path(job_id)
    elif artifact_name == "cleaned-ball-trajectory":
        path = _STORAGE.cleaned_ball_trajectory_json_path(job_id)
    elif artifact_name == "bounce-events":
        path = _STORAGE.bounce_events_json_path(job_id)
    elif artifact_name == "reconstructed-ball-trajectory":
        path = _STORAGE.reconstructed_ball_trajectory_json_path(job_id)
    elif artifact_name == "analysis-overlay-video":
        path = _STORAGE.analysis_overlay_video_path(job_id)
    elif artifact_name == "position-heatmaps":
        path = _STORAGE.heatmaps_manifest_json_path(job_id)
    elif artifact_name == "position-scatter-plots":
        path = _STORAGE.scatter_plots_manifest_json_path(job_id)
    elif artifact_name == "pose-overlay":
        path = _STORAGE.pose_overlay_json_path(job_id)
    elif artifact_name == "player-trajectories":
        path = _STORAGE.player_trajectory_json_path(job_id)
    elif artifact_name == "player-render-trajectories":
        path = _STORAGE.player_render_trajectory_path(job_id)
    elif artifact_name == "fused-trajectory":
        path = _STORAGE.fused_trajectory_json_path(job_id)
    elif artifact_name == "fusion-diagnostics":
        path = _STORAGE.fusion_diagnostics_json_path(job_id)
    elif artifact_name == "fused-manifest":
        path = _STORAGE.fusion_manifest_json_path(job_id)
    elif artifact_name == "serve-events":
        path = _STORAGE.serve_events_json_path(job_id)
    elif artifact_name == "serve-debug-candidates":
        path = _STORAGE.serve_debug_candidates_json_path(job_id)
    elif artifact_name == "serve-score-series":
        path = _STORAGE.serve_score_series_json_path(job_id)
    elif artifact_name == "serve-clips-manifest":
        path = _STORAGE.serve_clips_manifest_json_path(job_id)
    elif artifact_name == "court-view-roi":
        path = _STORAGE.court_view_roi_json_path(job_id)
    elif artifact_name == "calibration-diagnostics":
        path = _STORAGE.calibration_diagnostics_json_path(job_id)
    else:
        # 上面没显式列出的（如 serve-debug-overlay）走这个兜底分支
        path = _STORAGE.serve_debug_overlay_video_path(job_id)

    # 文件不存在就报错
    if not path.exists():
        raise HTTPException(status_code=404, detail="Analysis artifact not found")

    # 按产物类型决定返回方式：
    # 1) 视频类（叠加调试视频、分析叠加视频）→ 直接返回 mp4 文件
    if artifact_name in {"serve-debug-overlay", "analysis-overlay-video"}:
        return FileResponse(path, media_type="video/mp4")
    # 2) 检测记录是 JSONL（每行一个 JSON 对象）→ 以纯文本返回，方便逐行读取
    if artifact_name == "detections":
        return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="application/x-ndjson")
    # 3) 其余都是 JSON 文件 → 读取后以 JSON 形式返回
    return JSONResponse(_STORAGE.read_json(path))


@router.get("/jobs/{job_id}/artifacts/position-visualization-images/{kind}/{file_name}", response_model=None)
def read_position_visualization_image(
    job_id: str,
    kind: Literal["heatmaps", "scatter_plots"],
    file_name: str,
) -> FileResponse:
    """读取位置可视化 manifest 中引用的 PNG 图片。"""
    job = get_mock_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    safe_name = Path(file_name).name
    if safe_name != file_name or not safe_name.lower().endswith(".png"):
        raise HTTPException(status_code=404, detail="Analysis artifact not found")
    base_dir = _STORAGE.heatmaps_dir(job_id) if kind == "heatmaps" else _STORAGE.scatter_plots_dir(job_id)
    path = base_dir / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Analysis artifact not found")
    return FileResponse(path, media_type="image/png")


@router.get("/jobs/{job_id}/visualization-data", response_model=None)
def read_structured_visualization_data(job_id: str) -> JSONResponse:
    """返回结构化可视化数据，供前端 SVG 渲染。

    旧 job / job 未完成时返回 404，前端据此降级到 PNG。
    """
    job = get_mock_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    path = _STORAGE.structured_visualization_data_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Structured visualization data not available")
    return JSONResponse(_STORAGE.read_json(path))
