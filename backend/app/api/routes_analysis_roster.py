"""分析前名册预检 API —— 受限 player bootstrap。

刻意保持窄接口：只回答"有哪些可确认的球员候选、锚点与质量诊断"，**不启动完整
视觉 Pipeline**。用户跳过或候选不足时，普通分析照常可创建。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.rally_context import PlayerBootstrapResult
from app.services.analysis_rally_context_service import build_player_bootstrap

router = APIRouter(prefix="/api/analysis", tags=["analysis-roster"])


def _recent_job_ids_for(capture_take_id: str | None, video_id: str | None) -> list[str]:
    """按最近优先列出该素材的候选来源任务（只读，不创建任何任务）。"""
    from app.services.mock_analysis import list_analysis_jobs

    try:
        jobs = list_analysis_jobs()
    except Exception:  # noqa: BLE001 - bootstrap 是可选前置，控制面不可用不应阻塞
        return []
    matches = [
        job
        for job in jobs
        if (capture_take_id and job.metadata.capture_take_id == capture_take_id)
        or (video_id and job.videoId == video_id)
    ]
    matches.sort(key=lambda job: (job.updatedAt or job.createdAt), reverse=True)
    return [job.id for job in matches if job.canonicalStatus == "succeeded"]


@router.get("/players/bootstrap", response_model=PlayerBootstrapResult)
def get_player_bootstrap(
    captureTakeId: str | None = Query(default=None),
    videoId: str | None = Query(default=None),
    matchFormat: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PlayerBootstrapResult:
    """返回参考帧时间点、P1–P4 候选、身份锚点与质量诊断。

    没有可复用产物时会尝试源视频的轻量首段预检；仍不可用则返回
    `unavailable`，并保持 `skippable=True`，用户可以手工填写名册与端位，或直接跳过。
    """
    return build_player_bootstrap(
        db,
        capture_take_id=captureTakeId,
        video_id=videoId,
        match_format=matchFormat,
        source_job_ids=_recent_job_ids_for(captureTakeId, videoId),
    )


@router.get("/players/bootstrap/frame")
def get_player_bootstrap_frame(
    videoId: str = Query(min_length=1),
    timestampMs: int = Query(default=0, ge=0),
) -> Response:
    """返回确认页使用的源视频参考帧，不写入分析产物。"""
    import cv2  # type: ignore

    from app.services.video_service import video_service

    video = video_service.get_available_video(videoId)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    capture = cv2.VideoCapture(str(video.path))
    try:
        if not capture.isOpened():
            raise HTTPException(status_code=404, detail="Video cannot be opened")
        capture.set(cv2.CAP_PROP_POS_MSEC, float(timestampMs))
        ok, frame = capture.read()
        if not ok or frame is None:
            raise HTTPException(status_code=404, detail="Reference frame unavailable")
        encoded, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 84])
        if not encoded:
            raise HTTPException(status_code=500, detail="Reference frame encoding failed")
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=300"},
        )
    finally:
        capture.release()
