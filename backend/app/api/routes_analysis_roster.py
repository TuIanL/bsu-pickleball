"""分析前名册预检 API —— 受限 player bootstrap。

刻意保持窄接口：只回答"有哪些可确认的球员候选、锚点与质量诊断"，**不启动完整
视觉 Pipeline**。用户跳过或候选不足时，普通分析照常可创建。

契约版本：

- `contract=v2`（默认）：`player-bootstrap.v2`，以 `candidate_id` 表达预检候选身份，
  与用户 P 槽位、正式 `Player_N` 严格分离；确认页默认消费这一版。
- `contract=v1`：`player-bootstrap.v1`，沿用历史"已有产物优先"的读取路径，
  仅供尚未升级的旧客户端使用。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.rally_context import PlayerBootstrapResult, PlayerBootstrapResultV2
from app.services.analysis_rally_context_service import (
    build_player_bootstrap,
    build_player_bootstrap_v2,
)

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


@router.get("/players/bootstrap", response_model=None)
def get_player_bootstrap(
    captureTakeId: str | None = Query(default=None),
    videoId: str | None = Query(default=None),
    videoIdB: str | None = Query(default=None),
    matchFormat: str | None = Query(default=None),
    clipStartMs: int | None = Query(default=None, ge=0),
    clipEndMs: int | None = Query(default=None, ge=0),
    contract: Literal["v1", "v2"] = Query(default="v2"),
    db: Session = Depends(get_db),
) -> dict:
    """返回 P1–P4 候选、身份锚点、可核对画面与质量诊断。

    没有可复用产物时会对**所选片段的多个时间窗口**做有界预检；仍不可用则返回
    `unavailable`，并保持 `skippable=True`，用户可以手工填写名册与端位，或直接跳过。

    返回 `dict` 而不是固定 `response_model`：v1/v2 两个契约的 `schema_version` 是
    互斥字面量，用联合类型序列化容易在运行时选错分支，故显式按契约构造并序列化。
    """
    if contract == "v1":
        result: PlayerBootstrapResult | PlayerBootstrapResultV2 = build_player_bootstrap(
            db,
            capture_take_id=captureTakeId,
            video_id=videoId,
            match_format=matchFormat,
            source_job_ids=_recent_job_ids_for(captureTakeId, videoId),
        )
    else:
        result = build_player_bootstrap_v2(
            db,
            capture_take_id=captureTakeId,
            video_id=videoId,
            video_id_b=videoIdB,
            match_format=matchFormat,
            clip_start_ms=clipStartMs,
            clip_end_ms=clipEndMs,
        )
    return result.model_dump(mode="json")


@router.get("/players/bootstrap/frame")
def get_player_bootstrap_frame(
    videoId: str = Query(min_length=1),
    timestampMs: int = Query(default=0, ge=0),
    bbox: str | None = Query(default=None),
) -> Response:
    """返回确认页使用的源视频参考帧，不写入分析产物。

    传入 `bbox=x1,y1,x2,y2` 时只返回该框的裁剪图（人物候选画面）。裁剪由同一个
    `videoId` + `timestampMs` 决定，因此卡片画面与它标注的时间/机位必然一致。
    """
    import cv2  # type: ignore

    from app.services.video_service import video_service

    video = video_service.get_available_video(videoId)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    crop_box = _parse_bbox(bbox)
    capture = cv2.VideoCapture(str(video.path))
    try:
        if not capture.isOpened():
            raise HTTPException(status_code=404, detail="Video cannot be opened")
        capture.set(cv2.CAP_PROP_POS_MSEC, float(timestampMs))
        ok, frame = capture.read()
        if not ok or frame is None:
            raise HTTPException(status_code=404, detail="Reference frame unavailable")
        if crop_box is not None:
            height, width = frame.shape[:2]
            x1 = max(0, min(width - 1, int(round(crop_box[0]))))
            y1 = max(0, min(height - 1, int(round(crop_box[1]))))
            x2 = max(x1 + 1, min(width, int(round(crop_box[2]))))
            y2 = max(y1 + 1, min(height, int(round(crop_box[3]))))
            frame = frame[y1:y2, x1:x2]
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


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """解析 `bbox=x1,y1,x2,y2`；格式不合法时按"不裁剪"处理，不报错。"""
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(part) for part in parts)
    except ValueError:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2
