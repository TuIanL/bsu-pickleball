from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.video import VideoMetadata, VideoUploadResponse
from app.services.video_service import UnsupportedVideoError, video_service

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(file: UploadFile = File(...)) -> VideoUploadResponse:
    try:
        video = await video_service.save_upload(file)
    except UnsupportedVideoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VideoUploadResponse(video=video)


@router.get("/{video_id}", response_model=VideoMetadata)
def read_video(video_id: str) -> VideoMetadata:
    video = video_service.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
