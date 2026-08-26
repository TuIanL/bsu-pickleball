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


def test_patch_updates_display_metadata(monkeypatch):
    """PATCH /api/videos/{id} 写入用户自定义显示标题/日期（library-card-metadata-editing）。"""
    from app.schemas.video import VideoUpdateRequest

    stored: dict[str, VideoMetadata] = {"v1": _video("v1")}

    def fake_get(video_id):
        return stored.get(video_id)

    def fake_update(video_id, *, display_title=None, display_date=None):
        meta = stored[video_id]
        updated = meta.model_copy(
            update={
                "display_title": (display_title or "").strip() or None,
                "display_date": display_date,
            }
        )
        stored[video_id] = updated
        return updated

    monkeypatch.setattr(routes_video.video_service, "get_video", fake_get)
    monkeypatch.setattr(routes_video.video_service, "update_video", fake_update)

    result = routes_video.update_video_metadata(
        "v1",
        VideoUpdateRequest(display_title="自定义名称", display_date="2026-08-15"),
    )
    assert result.display_title == "自定义名称"
    assert result.display_date is not None
    assert result.display_date.year == 2026

    # 空值撤销覆盖
    result2 = routes_video.update_video_metadata(
        "v1",
        VideoUpdateRequest(display_title=""),
    )
    assert result2.display_title is None


def test_patch_missing_video_returns_404(monkeypatch):
    """PATCH 不存在的 video 返回 404。"""
    from fastapi import HTTPException

    from app.schemas.video import VideoUpdateRequest

    monkeypatch.setattr(routes_video.video_service, "get_video", lambda video_id: None)
    monkeypatch.setattr(routes_video.video_service, "update_video", lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc_info:
        routes_video.update_video_metadata("missing", VideoUpdateRequest(display_title="x"))
    assert exc_info.value.status_code == 404