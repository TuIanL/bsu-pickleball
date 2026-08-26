"""
视频接口路由（/api/videos）

本文件负责处理"视频"相关的所有 HTTP 请求，主要包括三件事：
1. 上传视频文件（前端把本地视频传给服务器保存）
2. 查询某个视频的元数据（如文件名、时长、分辨率、编码格式等）
3. 返回一个可直接在浏览器里播放的视频流

这些接口会被前端的"上传视频"页面和"视频工作台"页面调用。

关于 FastAPI 的几个核心概念（小白科普）：
- APIRouter：一组相关接口的"集合"，最后整体挂到应用上。
- @router.post("/xxx") / @router.get("/xxx")：用装饰器声明"当浏览器以某方法访问某路径时，
  就执行下面的函数"。POST 一般用于提交数据，GET 一般用于查询数据。
- response_model：声明函数返回的数据按哪个"模型（Schema）"来组织，FastAPI 会据此校验和序列化。
- HTTPException：出错时抛出的异常，status_code 是 HTTP 状态码（404=找不到，400=请求有误等）。
"""

# pathlib.Path 是 Python 处理文件路径的标准工具，可用来判断文件是否存在
import json
from pathlib import Path
from urllib.parse import quote

# FastAPI 核心组件
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

# 导入"视频"相关的数据模型（Schema，规定接口接收/返回的数据长什么样）
from app.schemas.video import (
    VideoCatalogResponse,
    VideoMetadata,
    VideoTimingMaterializeResponse,
    VideoTimingResponse,
    VideoUpdateRequest,
    VideoUploadResponse,
)

# 导入真正干活的"视频服务"对象 video_service（逻辑在 services 层，不在路由层）
# UnsupportedVideoError 是我们自定义的异常：当上传的文件不是受支持的视频格式时抛出
from app.services.video_service import UnsupportedVideoError, video_service
from app.services.dual_camera_sync import read_frame_timing_sidecar, summarize_frame_timing_sidecar
from app.services.multiview_acceptance import materialize_registered_video_timing

# 创建一个路由表：
# - prefix="/api/videos" 表示本文件里所有接口的路径都以 /api/videos 开头
# - tags=["videos"] 只是给接口打个分组标签，方便在自动生成的 API 文档里归类
router = APIRouter(prefix="/api/videos", tags=["videos"])


def _inline_content_disposition(filename: str) -> str:
    # 中文等非 ASCII 文件名直接放进 Content-Disposition 会触发 Starlette 的
    # latin-1 编码（UnicodeEncodeError → 500），导致视频流加载失败。
    # 这里用 RFC 5987 的 filename* 提供 UTF-8 编码版本，fallback 用 ASCII 化文件名。
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip()
    # ASCII 化后文件名主体为空（如全中文只剩扩展名）时回退到通用名
    if not ascii_name or not ascii_name[0].isalnum():
        ascii_name = "video.mp4"
    encoded = quote(filename)
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


# 定义一个"上传视频"的接口
# @router.post("/upload") 表示：前端用 POST 方法访问 /api/videos/upload 时触发本函数
# response_model=VideoUploadResponse 表示：返回数据会按 VideoUploadResponse 这个模型格式化
@router.post("/upload", response_model=VideoUploadResponse)
# file: UploadFile = File(...) 表示从请求中取名为 file 的上传文件；
# 末尾的 ... 是 FastAPI 的写法，表示"这是必填项，前端必须提供"
async def upload_video(file: UploadFile = File(...)) -> VideoUploadResponse:
    """
    上传视频文件

    工作流程：
    1. 接收前端传来的视频文件
    2. 交给 video_service.save_upload 保存到服务器磁盘，并生成元数据
    3. 把保存结果包装成 VideoUploadResponse 返回给前端（里面通常包含 videoId 等）
    """
    try:
        # 调用业务层保存文件。这一步在文件格式不支持时会抛出 UnsupportedVideoError
        video = await video_service.save_upload(file)
    except UnsupportedVideoError as exc:
        # 文件格式不支持：返回 HTTP 400（请求有误），并把具体错误原因告诉前端
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 成功则把视频信息返回给前端
    return VideoUploadResponse(video=video)


# 定义一个"查询视频目录"的接口
# GET /api/videos：只读枚举全部已注册视频元数据，供 Library 的 upload 素材目录使用。
# 不新建数据表、不创建新实体，仅把现有 video registry 暴露为可枚举 catalog。
@router.get("", response_model=VideoCatalogResponse)
def list_videos_catalog() -> VideoCatalogResponse:
    """
    列出所有已注册视频（只读）

    返回一个视频元数据列表。该接口供前端 Library 构建 upload 类型素材的独立资产目录，
    前端不再需要从分析任务列表反推「有哪些上传视频」。
    """
    return VideoCatalogResponse(videos=video_service.list_videos())


# 定义一个"查询视频元数据"的接口
# GET /api/videos/{video_id}：通过视频 id 获取它的详细信息。
# 路径里的 {video_id} 是占位符，FastAPI 会自动把实际值传给函数参数 video_id
@router.get("/{video_id}", response_model=VideoMetadata)
def read_video(video_id: str) -> VideoMetadata:
    """
    读取视频元数据详情

    只返回视频的"描述信息"（文件名、时长、分辨率、编码等），不包含视频文件本身。
    """
    # 从存储中查找这个视频
    video = video_service.get_video(video_id)
    if video is None:
        # 没找到就返回 HTTP 404（资源不存在）
        raise HTTPException(status_code=404, detail="Video not found")
    return video


# 定义一个"更新视频显示元数据"的接口
# PATCH /api/videos/{video_id}：供 Library 卡片内联编辑写入用户自定义标题/比赛日期。
# 空值表示撤销覆盖（回退到 original_filename / uploaded_at 派生值）。
@router.patch("/{video_id}", response_model=VideoMetadata)
def update_video_metadata(video_id: str, payload: VideoUpdateRequest) -> VideoMetadata:
    video = video_service.update_video(
        video_id,
        display_title=payload.display_title,
        display_date=payload.display_date,
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{video_id}/timing", response_model=VideoTimingResponse)
def read_video_timing(video_id: str) -> VideoTimingResponse:
    """Return validated source PTS rows for a registered video.

    The client addresses the media only by its registered ``video_id``. The
    sidecar path is derived from the registered media metadata, so arbitrary
    filesystem paths never enter this endpoint.
    """
    video = video_service.get_available_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Registered video not found or unavailable")

    media_path = Path(video.path).resolve(strict=False)
    sidecar_path = Path(f"{media_path}.pts.jsonl")
    if not sidecar_path.is_file():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "source_pts_missing",
                "message": "Registered video has no validated source PTS sidecar",
                "video_id": video_id,
            },
        )

    try:
        summary = summarize_frame_timing_sidecar(
            sidecar_path,
            media_path=media_path,
            require_bound_path=True,
        )
        frames = read_frame_timing_sidecar(sidecar_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "source_pts_invalid",
                "message": str(exc),
                "video_id": video_id,
            },
        ) from exc

    return VideoTimingResponse(
        authority="source_pts",
        frame_count=int(summary["frame_count"]),
        fps=float(summary["fps"]) if summary.get("fps") is not None else None,
        first_pts_seconds=float(summary["first_pts_seconds"]),
        last_pts_seconds=float(summary["last_pts_seconds"]),
        frames=[
            {
                "frame_index": frame.frame_index,
                "pts_seconds": frame.pts_seconds,
                "dts_seconds": frame.dts_seconds,
                "keyframe": frame.keyframe,
            }
            for frame in frames
        ],
    )


@router.post("/{video_id}/timing/materialize", response_model=VideoTimingMaterializeResponse)
def materialize_video_timing(video_id: str) -> VideoTimingMaterializeResponse:
    """Synchronously materialize (or reuse) a registered video's PTS sidecar.

    Idempotent repair endpoint for the sync-anchor workbench: when a video is
    missing its ``.pts.jsonl`` sidecar (e.g. a historical session completed
    before the materialization mechanism existed), this endpoint regenerates it
    from the registered media via ffprobe.  Runs on the thread pool (sync
    ``def``) so long extractions never block the event loop.
    """
    video = video_service.get_available_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Registered video not found or unavailable")

    media_path = Path(video.path).resolve(strict=False)
    result = materialize_registered_video_timing(media_path)
    if result.status != "ready" or result.timing_authority != "source_pts":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "source_pts_invalid",
                "message": result.reason or "Failed to materialize source PTS sidecar",
                "video_id": video_id,
            },
        )

    summary = result.summary or {}
    return VideoTimingMaterializeResponse(
        authority=result.timing_authority,
        status=result.status,
        reused=result.reused,
        frame_count=int(summary.get("frame_count") or 0),
        fps=float(summary["fps"]) if summary.get("fps") is not None else None,
        first_pts_seconds=float(summary["first_pts_seconds"])
        if summary.get("first_pts_seconds") is not None else None,
        last_pts_seconds=float(summary["last_pts_seconds"])
        if summary.get("last_pts_seconds") is not None else None,
        sidecar_path=result.sidecar_path,
    )


# 定义一个"播放视频流"的接口
# GET /api/videos/{video_id}/stream：返回视频文件本身，浏览器可直接播放
@router.get("/{video_id}/stream")
def stream_video(video_id: str, request: Request) -> StreamingResponse:
    """
    浏览器可播放的源视频流

    返回一个文件响应，浏览器的 <video> 标签用它即可播放视频。
    使用 StreamingResponse 并手动管理文件句柄，避免 Starlette FileResponse
    在 range/seek 场景下出现的文件描述符泄漏。
    """
    # 先拿到视频元数据，以便知道文件在磁盘的哪里、是什么类型
    video = video_service.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    # 把字符串路径转成 Path 对象，便于检查磁盘上的文件是否真的存在
    path = Path(video.path)
    if not path.exists():
        # 元数据在，但磁盘上的文件丢失了（比如被误删）
        raise HTTPException(status_code=404, detail="Video file not found")

    # 解析为浏览器可直接播放的路径：TS→合并 MP4→faststart 播放版（存在时）
    from app.camera.ffmpeg_utils import resolve_browser_stream_path

    path = resolve_browser_stream_path(path)
    filename = path.name
    if path.suffix.lower() in (".mp4",):
        media_type = "video/mp4"

    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    def _file_iterator(start: int, end: int):
        # 同步生成器；with 语句保证文件在迭代结束后一定关闭
        with open(path, "rb") as file:
            file.seek(start)
            remaining = end - start
            chunk_size = 1024 * 1024  # 1 MiB
            while remaining > 0:
                to_read = min(chunk_size, remaining)
                chunk = file.read(to_read)
                if not chunk:
                    break
                yield chunk
                remaining -= len(chunk)

    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _inline_content_disposition(filename),
    }

    if range_header:
        # 解析 Bytes Range，例如 bytes=0-1023
        try:
            unit, range_spec = range_header.split("=", 1)
            if unit.strip().lower() != "bytes":
                raise ValueError("Only bytes ranges are supported")
            start_str, end_str = range_spec.split("-", 1)
            start = int(start_str) if start_str.strip() else 0
            end = int(end_str) + 1 if end_str.strip() else file_size
            end = min(end, file_size)
            if start < 0 or start >= file_size or start >= end:
                raise ValueError("Invalid byte range")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Range header: {exc}") from exc

        headers["Content-Range"] = f"bytes {start}-{end - 1}/{file_size}"
        headers["Content-Length"] = str(end - start)
        return StreamingResponse(
            _file_iterator(start, end),
            status_code=206,
            media_type=media_type,
            headers=headers,
        )

    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        _file_iterator(0, file_size),
        status_code=200,
        media_type=media_type,
        headers=headers,
    )


@router.get("/{video_id}/poster")
def video_poster(video_id: str, request: Request) -> FileResponse:
    """比赛库封面 poster 图（预生成，非实时解码视频流）。

    视频登记 / 上传 / 双摄合并时已由 `cover_poster.generate_poster` 落盘同名
    `*.poster.jpg`；此处仅按 video_id 解析并服务。未生成时返回 404，
    前端自动回退到视频流首帧封面。
    """
    video = video_service.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    from app.services.cover_poster import poster_path_for

    poster = poster_path_for(video.path)
    if not poster.exists() or poster.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="Poster not available")

    # 通过 Last-Modified / ETag 做条件缓存：重新合并覆盖同名 poster 后浏览器会重新拉取，
    # 等效于 `?v=<mtime>` 缓存击穿，但不污染 URL、不破坏既有引用。
    mtime = poster.stat().st_mtime
    headers = {
        "Cache-Control": "public, max-age=3600",
        "Last-Modified": _http_date(mtime),
        "ETag": f'"{int(mtime)}"',
    }
    if request.headers.get("if-none-match") == f'"{int(mtime)}"':
        from fastapi.responses import Response

        return Response(status_code=304, headers=headers)
    return FileResponse(poster, media_type="image/jpeg", headers=headers)


def _http_date(timestamp: float) -> str:
    from email.utils import formatdate

    return formatdate(timestamp, usegmt=True)
