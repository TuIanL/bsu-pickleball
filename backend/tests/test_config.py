from app.core import config


def test_overlay_frame_stride_defaults_to_60fps_friendly_value(monkeypatch):
    monkeypatch.delenv("PICKLEBALL_OVERLAY_FRAME_STRIDE", raising=False)
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.overlay_frame_stride == 2
    finally:
        config.get_settings.cache_clear()


def test_overlay_frame_stride_env_override_is_preserved(monkeypatch):
    monkeypatch.setenv("PICKLEBALL_OVERLAY_FRAME_STRIDE", "5")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.overlay_frame_stride == 5
    finally:
        config.get_settings.cache_clear()
