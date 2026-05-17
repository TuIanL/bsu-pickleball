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


def test_pose_inference_auto_enables_when_rtmpose_assets_are_discovered(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    config_path = model_dir / "rtmpose" / "rtmpose-m_8xb512-700e_body8-halpe26-256x192.py"
    checkpoint_path = model_dir / "rtmpose" / "rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("# config", encoding="utf-8")
    checkpoint_path.write_text("checkpoint", encoding="utf-8")
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("PICKLEBALL_ENABLE_POSE_INFERENCE", raising=False)
    monkeypatch.delenv("PICKLEBALL_RTMPOSE_CONFIG_PATH", raising=False)
    monkeypatch.delenv("PICKLEBALL_RTMPOSE_CHECKPOINT_PATH", raising=False)
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.enable_pose_inference is True
        assert settings.rtmpose_config_path == str(config_path)
        assert settings.rtmpose_checkpoint_path == str(checkpoint_path)
    finally:
        config.get_settings.cache_clear()


def test_pose_inference_env_can_disable_discovered_assets(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    config_path = model_dir / "rtmpose" / "rtmpose-m_8xb512-700e_body8-halpe26-256x192.py"
    checkpoint_path = model_dir / "rtmpose" / "rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("# config", encoding="utf-8")
    checkpoint_path.write_text("checkpoint", encoding="utf-8")
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("PICKLEBALL_ENABLE_POSE_INFERENCE", "false")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.enable_pose_inference is False
        assert settings.rtmpose_config_path == str(config_path)
    finally:
        config.get_settings.cache_clear()


def test_primary_player_filter_configuration(monkeypatch):
    monkeypatch.setenv("PICKLEBALL_PRIMARY_PLAYER_MIN_CONFIDENCE", "0.72")
    monkeypatch.setenv("PICKLEBALL_PRIMARY_PLAYER_MAX_SUBJECTS", "2")
    monkeypatch.setenv("PICKLEBALL_PRIMARY_PLAYER_COURT_MARGIN_FT", "18")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.primary_player_min_confidence == 0.72
        assert settings.primary_player_max_subjects == 2
        assert settings.primary_player_court_margin_ft == 18
    finally:
        config.get_settings.cache_clear()


def test_multitarget_ball_configuration(monkeypatch):
    monkeypatch.setenv("PICKLEBALL_ENABLE_MULTITARGET_INFERENCE", "true")
    monkeypatch.setenv("PICKLEBALL_BALL_CONFIDENCE", "0.44")
    monkeypatch.setenv("PICKLEBALL_PADDLE_CONFIDENCE", "0.55")
    monkeypatch.setenv("PICKLEBALL_BALL_MAX_REPAIR_GAP_FRAMES", "7")
    monkeypatch.setenv("PICKLEBALL_BALL_MAX_SPEED_PX_PER_FRAME", "210")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.enable_multitarget_inference is True
        assert settings.ball_confidence == 0.44
        assert settings.paddle_confidence == 0.55
        assert settings.ball_max_repair_gap_frames == 7
        assert settings.ball_max_speed_px_per_frame == 210
    finally:
        config.get_settings.cache_clear()
