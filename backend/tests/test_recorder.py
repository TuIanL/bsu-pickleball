from app.camera.recorder import _build_video_filter


def test_build_video_filter_uses_cfr_resolution_and_browser_pixel_format():
    assert _build_video_filter(30, "1280x720") == "fps=30,scale=1280:720,format=yuv420p"


def test_build_video_filter_ignores_invalid_resolution():
    assert _build_video_filter(30, "bad") == "fps=30,format=yuv420p"
