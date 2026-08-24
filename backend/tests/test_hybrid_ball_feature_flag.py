from app.core.config import Settings, get_settings


def test_hybrid_ball_feature_flag_defaults_on():
    assert Settings().enable_hybrid_ball_trajectory is True


def test_hybrid_ball_feature_flag_reads_environment(monkeypatch):
    monkeypatch.setenv("PICKLEBALL_ENABLE_HYBRID_BALL_TRAJECTORY", "false")
    get_settings.cache_clear()
    try:
        assert get_settings().enable_hybrid_ball_trajectory is False
    finally:
        get_settings.cache_clear()
