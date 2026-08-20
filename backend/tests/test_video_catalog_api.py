from datetime import UTC, datetime

import pytest

from app.api import routes_video
from app.schemas.video import VideoCatalogResponse, VideoMetadata


def _video(video_id: str, source: str = "upload") -> VideoMetadata:
    return VideoMetadata(
        id=video_id,
        original_filename=f"{video_id}.mp4",
        content_type="video/mp4",
        size_bytes=1024,
        path=f"/tmp/{video_id}.mp4",
        uploaded_at=datetime.now(UTC),
        source=source,
    )


def test_catalog_returns_all_registered_videos(monkeypatch):
    videos = [_video("v1"), _video("v2", source="recording")]
    monkeypatch.setattr(routes_video.video_service, "list_videos", lambda: videos)

    result = routes_video.list_videos_catalog()

    assert isinstance(result, VideoCatalogResponse)
    assert [v.id for v in result.videos] == ["v1", "v2"]


def test_catalog_empty_list_is_stable(monkeypatch):
    monkeypatch.setattr(routes_video.video_service, "list_videos", lambda: [])

    result = routes_video.list_videos_catalog()

    assert result.videos == []


def test_catalog_is_readonly_upload_still_uses_upload_route():
    # catalog 接口只暴露枚举；真正的写入仍只走 POST /upload，catalog 无创建逻辑。
    catalog_routes = [r for r in routes_video.router.routes if getattr(r, "path", "") == "/api/videos"]
    assert any(r.methods and "GET" in r.methods for r in catalog_routes)
    # 没有任何非 GET 方法挂在 /api/videos catalog path 上（POST 均属 /upload）
    assert all(
        not (r.methods and "POST" in r.methods)
        for r in catalog_routes
    )