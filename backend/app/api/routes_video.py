from fastapi import APIRouter, File, HTTPException, UploadFile

# 导入视频相关的模式（Schemas）
from app.schemas.video import VideoMetadata, VideoUploadResponse
# 导入视频服务和错误处理
from app.services.video_service import UnsupportedVideoError, video_service

# 定义 API 路由，前缀为 /api/videos，标签为 videos
router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(file: UploadFile = File(...)) -> VideoUploadResponse:
    """
    上传视频文件
    """
    try:
        video = await video_service.save_upload(file)
    except UnsupportedVideoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VideoUploadResponse(video=video)


@router.get("/{video_id}", response_model=VideoMetadata)
def read_video(video_id: str) -> VideoMetadata:
    """
    读取视频元数据详情
    """
    video = video_service.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
