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


def test_ball_semantic_policy_defaults_to_shadow_fail_open(monkeypatch, tmp_path):
    for name in [
        "PICKLEBALL_ENABLE_BALL_SEMANTIC_POLICY",
        "PICKLEBALL_BALL_SEMANTIC_POLICY_MODE",
        "PICKLEBALL_BALL_SEMANTIC_ENFORCE_AUTHORITATIVE_NON_PLAY",
        "PICKLEBALL_BALL_SEMANTIC_ENFORCED_ROLLOUT",
        "PICKLEBALL_BALL_SEMANTIC_ROLLOUT_ID",
        "PICKLEBALL_BALL_SEMANTIC_TIMELINE_ENABLED",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(tmp_path / "empty-models"))
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.enable_ball_semantic_policy is True
        assert settings.ball_semantic_policy_mode == "shadow"
        assert settings.ball_semantic_enforce_authoritative_non_play is False
        assert settings.ball_semantic_enforced_rollout is False
        assert settings.ball_semantic_rollout_id == "default"
        assert settings.ball_semantic_timeline_enabled is True
        assert settings.ball_semantic_rally_end_min_evidence == 2
    finally:
        config.get_settings.cache_clear()


def test_ball_semantic_policy_can_be_disabled_for_rollback(monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(tmp_path / "empty-models"))
    monkeypatch.setenv("PICKLEBALL_ENABLE_BALL_SEMANTIC_POLICY", "false")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_POLICY_MODE", "enforced")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.enable_ball_semantic_policy is False
        assert settings.ball_semantic_policy_mode == "enforced"
    finally:
        config.get_settings.cache_clear()


def test_ball_semantic_enforced_rollout_is_explicit_and_identifiable(monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(tmp_path / "empty-models"))
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_POLICY_MODE", "enforced")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_ENFORCED_ROLLOUT", "true")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_ROLLOUT_ID", "take-20260720-shadow-compare")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.ball_semantic_enforced_rollout is True
        assert settings.ball_semantic_rollout_id == "take-20260720-shadow-compare"
    finally:
        config.get_settings.cache_clear()


def test_ball_semantic_boundary_calibration_settings_are_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(tmp_path / "empty-models"))
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_POLICY_VERSION", "semantic-boundary-test.v2")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_MIN_CONFIRM_TICKS", "4")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_GRACE_WINDOW_SECONDS", "0.35")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_RESCUE_MIN_CONSECUTIVE_TICKS", "3")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_RESCUE_MIN_MOTION_PIXELS", "21")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_EVIDENCE_FRESHNESS_SECONDS", "0.8")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_CONFLICT_PENALTY", "0.1")
    monkeypatch.setenv("PICKLEBALL_BALL_SEMANTIC_BOUNDARY_EVAL_ENABLED", "false")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.ball_semantic_policy_version == "semantic-boundary-test.v2"
        assert settings.ball_semantic_min_confirm_ticks == 4
        assert settings.ball_semantic_grace_window_seconds == 0.35
        assert settings.ball_semantic_rescue_min_consecutive_ticks == 3
        assert settings.ball_semantic_rescue_min_motion_pixels == 21.0
        assert settings.ball_semantic_evidence_freshness_seconds == 0.8
        assert settings.ball_semantic_conflict_penalty == 0.1
        assert settings.ball_semantic_boundary_eval_enabled is False
    finally:
        config.get_settings.cache_clear()


def test_pose_inference_auto_enables_when_rtmpose_assets_are_discovered(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    config_path = model_dir / "rtmpose" / "rtmpose-m_8xb512-700e_body8-halpe26-256x192.py"
    checkpoint_path = (
        model_dir / "rtmpose" / "rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth"
    )
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
    checkpoint_path = (
        model_dir / "rtmpose" / "rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth"
    )
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


def test_court_aware_attention_selector_configuration(monkeypatch):
    monkeypatch.setenv("PICKLEBALL_PRIMARY_PLAYER_WINDOW_FRAMES", "45")
    monkeypatch.setenv("PICKLEBALL_PRIMARY_PLAYER_TARGET_COURT_THRESHOLD", "0.61")
    monkeypatch.setenv("PICKLEBALL_PRIMARY_PLAYER_QUALITY_THRESHOLD", "0.33")
    monkeypatch.setenv("PICKLEBALL_ENABLE_ATTENTION_PLAYER_SELECTOR", "true")
    monkeypatch.setenv("PICKLEBALL_ATTENTION_PLAYER_SELECTOR_MODEL_PATH", "/tmp/selector.pt")
    monkeypatch.setenv("PICKLEBALL_ATTENTION_PLAYER_SELECTOR_CONFIDENCE", "0.77")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.primary_player_window_frames == 45
        assert settings.primary_player_target_court_threshold == 0.61
        assert settings.primary_player_quality_threshold == 0.33
        assert settings.enable_attention_player_selector is True
        assert settings.attention_player_selector_model_path == "/tmp/selector.pt"
        assert settings.attention_player_selector_confidence == 0.77
    finally:
        config.get_settings.cache_clear()


def test_analysis_artifact_configuration_defaults_enable_outputs(monkeypatch, tmp_path):
    for name in [
        "PICKLEBALL_BALL_MODEL_PATH",
        "PICKLEBALL_ENABLE_BALL_DETECTION",
        "PICKLEBALL_ENABLE_BOUNCE_DETECTION",
        "PICKLEBALL_ENABLE_ANALYSIS_OVERLAY_VIDEO",
        "PICKLEBALL_ENABLE_POSITION_VISUALIZATIONS",
        "PICKLEBALL_VISUALIZATION_LANGUAGE",
    ]:
        monkeypatch.delenv(name, raising=False)
    # Keep the default contract independent from repository model assets.
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(tmp_path / "empty-models"))
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.ball_model_path is None
        assert settings.enable_ball_detection is True
        assert settings.enable_bounce_detection is True
        assert settings.enable_analysis_overlay_video is True
        assert settings.enable_position_visualizations is True
        assert settings.visualization_language == "zh-CN"
    finally:
        config.get_settings.cache_clear()


def test_ball_model_path_auto_discovers_local_ball_model(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    ball_model_path = model_dir / "ball" / "tennis-ball.pt"
    ball_model_path.parent.mkdir(parents=True)
    ball_model_path.write_text("weights", encoding="utf-8")
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("PICKLEBALL_BALL_MODEL_PATH", raising=False)
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.ball_model_path == str(ball_model_path)
    finally:
        config.get_settings.cache_clear()


def test_court_line_model_path_auto_discovers_local_model(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    court_model_path = model_dir / "court-line" / "best.pt"
    court_model_path.parent.mkdir(parents=True)
    court_model_path.write_text("weights", encoding="utf-8")
    monkeypatch.setenv("PICKLEBALL_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("PICKLEBALL_COURT_LINE_MODEL_PATH", raising=False)
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.court_line_model_path == str(court_model_path)
    finally:
        config.get_settings.cache_clear()


def test_analysis_artifact_configuration_env_overrides(monkeypatch):
    monkeypatch.setenv("PICKLEBALL_BALL_MODEL_PATH", "/tmp/ball.pt")
    monkeypatch.setenv("PICKLEBALL_ENABLE_BALL_DETECTION", "false")
    monkeypatch.setenv("PICKLEBALL_ENABLE_BOUNCE_DETECTION", "false")
    monkeypatch.setenv("PICKLEBALL_ENABLE_ANALYSIS_OVERLAY_VIDEO", "false")
    monkeypatch.setenv("PICKLEBALL_ENABLE_POSITION_VISUALIZATIONS", "false")
    monkeypatch.setenv("PICKLEBALL_VISUALIZATION_LANGUAGE", "en-US")
    config.get_settings.cache_clear()

    try:
        settings = config.get_settings()
        assert settings.ball_model_path == "/tmp/ball.pt"
        assert settings.enable_ball_detection is False
        assert settings.enable_bounce_detection is False
        assert settings.enable_analysis_overlay_video is False
        assert settings.enable_position_visualizations is False
        assert settings.visualization_language == "en-US"
    finally:
        config.get_settings.cache_clear()
