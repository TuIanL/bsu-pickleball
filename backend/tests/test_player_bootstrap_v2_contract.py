"""`player-bootstrap.v2` 契约的接线测试。

预检引擎的判定逻辑由 `test_player_bootstrap_preflight.py` 覆盖；这里只验证
**服务层接线**：模型开关、视频不可读、片段范围解析、候选画面 URL 与
"画面时间/机位一致"的契约，以及旧契约读取路径仍在。

依赖真实模型与真实视频的部分不在这里断言（需要真实素材）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services import analysis_rally_context_service as ctx_svc
from app.services import player_bootstrap_preflight_runtime as runtime
from app.services.player_bootstrap_preflight import (
    DIAG_PREFLIGHT_NO_CALIBRATION,
    BootstrapPreflightConfig,
    clear_preflight_cache,
)


@dataclass
class _StubVideo:
    path: Path


@dataclass
class _StubFrameSource:
    """替代 Cv2ViewFrameSource：不读真实视频，按时刻构造替身帧。"""

    views: list[Any]
    fps: float = 30.0
    frame_count: int = 3000
    reads: list[tuple[str, int]] = field(default_factory=list)
    released: bool = False

    def read(self, view_id: str, frame_index: int) -> Any:
        import numpy as np

        self.reads.append((view_id, frame_index))
        frame = np.zeros((120, 240, 3), dtype="uint8")
        timestamp_ms = int(round(frame_index / self.fps * 1000))
        frame[0, 0, 0] = timestamp_ms & 0xFF
        frame[0, 0, 1] = (timestamp_ms >> 8) & 0xFF
        frame[0, 0, 2] = (timestamp_ms >> 16) & 0xFF
        return frame

    def release(self) -> None:
        self.released = True


@dataclass
class _StubDetector:
    """两人稳定在场，靠时刻区分是否在片段内。"""

    min_ts_ms: int = 0
    max_ts_ms: int = 10**9

    def detect(self, frame: Any) -> list[Any]:
        timestamp_ms = int(frame[0, 0, 0]) | (int(frame[0, 0, 1]) << 8) | (int(frame[0, 0, 2]) << 16)
        if not (self.min_ts_ms <= timestamp_ms <= self.max_ts_ms):
            return []
        return [_StubDetection([20.0, 40.0, 44.0, 96.0], 0.9), _StubDetection([120.0, 40.0, 144.0, 96.0], 0.8)]


@dataclass(frozen=True)
class _StubDetection:
    bbox: list[float]
    confidence: float


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_preflight_cache()
    runtime.clear_video_metadata_cache()
    yield
    clear_preflight_cache()
    runtime.clear_video_metadata_cache()


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch, *, video_available: bool = True
) -> dict[str, _StubFrameSource]:
    """替换预检运行时依赖；返回的 dict 在服务调用之后才被填充。"""
    created: dict[str, _StubFrameSource] = {}

    def _factory(views):
        source = _StubFrameSource(views=list(views))
        created["source"] = source
        return source

    def _attach(context, _video_service):
        for view in context.views:
            if view.video_id:
                view.video_path = Path(f"/stub/{view.video_id}.mp4")
                view.fps = 30.0
                view.frame_count = 3000

    monkeypatch.setattr(runtime, "Cv2ViewFrameSource", _factory)
    monkeypatch.setattr(runtime, "attach_video_paths", _attach)
    monkeypatch.setattr(runtime, "build_court_projector", lambda **_kwargs: None)
    monkeypatch.setattr(runtime, "build_appearance_extractor", lambda: None)
    if not video_available:
        # 走"源视频不可读"分支：不解析任何机位。
        monkeypatch.setattr(runtime, "resolve_preflight_context", lambda *a, **k: runtime.PreflightRuntimeContext())

        def _attach_none(context, _video_service):
            for view in context.views:
                view.video_path = None

        monkeypatch.setattr(runtime, "attach_video_paths", _attach_none)

    monkeypatch.setattr(
        "app.vision.player_tracking_engine.person_detector.PersonDetector",
        lambda **_kwargs: _StubDetector(),
    )
    monkeypatch.setattr(
        "app.services.video_service.video_service.get_available_video",
        lambda video_id: _StubVideo(path=Path(f"/stub/{video_id}.mp4")) if video_available else None,
    )
    return created


def _settings(*, inference: bool) -> Settings:
    return Settings(enable_model_inference=inference)


def test_v2_contract_shape_and_frame_urls(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: _settings(inference=True))
    patch_source = _patch_runtime(monkeypatch)

    result = ctx_svc.build_player_bootstrap_v2(
        None,
        video_id="video-abc",
        match_format="doubles",
        clip_start_ms=1000,
        clip_end_ms=6000,
    )
    source = patch_source["source"]

    assert result.schema_version == "player-bootstrap.v2"
    assert result.expected_player_count == 4
    assert result.clip_start_ms == 1000
    assert result.clip_end_ms == 6000
    assert result.sampled_frame_count > 0
    assert result.bootstrap_cache_key
    # 只有两人可靠 → 诚实返回不足，而不是补人
    assert result.status == "insufficient_candidates"
    assert len(result.candidates) == 2
    assert {candidate.suggested_slot for candidate in result.candidates} == {1, 2}
    assert len({candidate.candidate_id for candidate in result.candidates}) == 2
    for candidate in result.candidates:
        assert candidate.view_id == "cam_1"
        assert candidate.frame_url is not None and f"videoId=video-abc" in candidate.frame_url
        assert f"timestampMs={candidate.timestamp_ms}" in candidate.frame_url
        # 人物画面与它标注的时间、机位是同一次观测
        assert candidate.crop_url is not None
        assert f"timestampMs={candidate.timestamp_ms}" in candidate.crop_url
        assert "bbox=" in candidate.crop_url
        # 没有标定 → 不伪造球场证据
        assert candidate.court_xy is None
        assert candidate.evidence.target_court_membership is None
        # 没有投影就判不出侧向：字段诚实为 None，而不是猜一个端点
        assert candidate.evidence.side is None
    codes = {item.code for item in result.diagnostics}
    assert DIAG_PREFLIGHT_NO_CALIBRATION in codes
    # 片段范围之外的帧不应被采样
    assert all(1000 <= source_ts <= 6000 for _view, _frame, source_ts in _read_timestamps(source))
    assert source.reads  # 确实读了帧，而不是走了空路径
    assert source.released is True


def test_v2_cached_result_skips_detector_loading_and_frame_reads(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: _settings(inference=True))
    sources = _patch_runtime(monkeypatch)
    arguments = dict(video_id="video-abc", match_format="doubles", clip_start_ms=1000, clip_end_ms=6000)
    first = ctx_svc.build_player_bootstrap_v2(None, **arguments)
    assert first.candidates

    def _unexpected_detector(**_kwargs):
        raise AssertionError("cached preflight must not reload the detector")

    monkeypatch.setattr(
        "app.vision.player_tracking_engine.person_detector.PersonDetector", _unexpected_detector
    )
    second = ctx_svc.build_player_bootstrap_v2(None, **arguments)
    assert [candidate.candidate_id for candidate in second.candidates] == [
        candidate.candidate_id for candidate in first.candidates
    ]
    assert sources["source"].reads == []
    assert sources["source"].released is True


def test_video_metadata_is_reused_for_the_same_file(monkeypatch, tmp_path):
    import cv2

    path = tmp_path / "video.mp4"
    path.write_bytes(b"stub")
    opens = []

    class _Capture:
        def __init__(self, source):
            opens.append(source)

        def isOpened(self):
            return True

        def get(self, prop):
            return 60 if prop == cv2.CAP_PROP_FPS else 3600

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", _Capture)
    video_service = SimpleNamespace(get_available_video=lambda _id: _StubVideo(path))
    first = runtime.PreflightRuntimeContext(views=[runtime.PreflightViewContext("cam_1", video_id="v")])
    second = runtime.PreflightRuntimeContext(views=[runtime.PreflightViewContext("cam_1", video_id="v")])
    runtime.attach_video_paths(first, video_service)
    runtime.attach_video_paths(second, video_service)
    assert len(opens) == 1
    assert second.views[0].fps == 60
    assert second.views[0].frame_count == 3600


def _read_timestamps(source: _StubFrameSource) -> list[tuple[str, int, int]]:
    return [
        (view_id, frame_index, int(round(frame_index / source.fps * 1000)))
        for view_id, frame_index in source.reads
    ]


def test_v2_reports_model_disabled(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: _settings(inference=False))
    result = ctx_svc.build_player_bootstrap_v2(
        None, video_id="video-abc", match_format="doubles", clip_start_ms=0, clip_end_ms=5000
    )
    assert result.status == "unavailable"
    assert result.unavailable_reason == "bootstrap_model_inference_disabled"
    assert result.candidates == []
    assert result.skippable is True


def test_v2_reports_unreadable_video(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: _settings(inference=True))
    _patch_runtime(monkeypatch, video_available=False)
    result = ctx_svc.build_player_bootstrap_v2(
        None, video_id="video-missing", match_format="doubles", clip_start_ms=0, clip_end_ms=5000
    )
    assert result.status == "unavailable"
    assert result.unavailable_reason == "bootstrap_video_unavailable"
    assert result.consumers_enabled is True


def test_v2_clip_range_falls_back_to_video_length(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: _settings(inference=True))
    _patch_runtime(monkeypatch)
    result = ctx_svc.build_player_bootstrap_v2(
        None, video_id="video-abc", match_format="doubles", clip_start_ms=0, clip_end_ms=None
    )
    # 替身帧源 3000 帧 @30fps → 100 秒
    assert result.clip_end_ms == pytest.approx(100_000, abs=1000)


def test_v1_contract_path_is_still_readable(monkeypatch):
    """v1 客户端仍能拿到旧响应（复用已有产物优先，其次才是首段预检）。"""
    monkeypatch.setattr("app.core.config.get_settings", lambda: _settings(inference=False))
    result = ctx_svc.build_player_bootstrap(
        None, capture_take_id="take-x", video_id=None, match_format="doubles"
    )
    assert result.schema_version == "player-bootstrap.v1"
    assert result.status == "unavailable"


def test_preflight_config_signature_changes_with_budget():
    """配置进缓存键：改预算必须失效缓存，否则会复用旧的钉死结果。"""
    from app.services.player_bootstrap_preflight import bootstrap_cache_key

    base = dict(
        video_signature="v1",
        clip_start_ms=0,
        clip_end_ms=1000,
        match_format="doubles",
        sync_signature="good",
        calibration_signature="cal",
        model_version="yolo11n.pt",
    )
    a = bootstrap_cache_key(**base, config=BootstrapPreflightConfig())
    b = bootstrap_cache_key(**base, config=BootstrapPreflightConfig(max_frames_total=8))
    assert a != b
    assert bootstrap_cache_key(**base, config=BootstrapPreflightConfig()) == a
