"""Exercise projection switches through the real single-view pipeline."""
import pytest

from app.core.config import get_settings
from app.services import analysis_pipeline
import test_api_smoke
from test_api_smoke import test_pipeline_generates_tracking_and_pose_overlay_artifacts as run_pipeline_case


@pytest.mark.parametrize('jsonl,overlay', [(False, False), (False, True), (True, False), (True, True)])
def test_projection_switches_and_release(tmp_path, monkeypatch, jsonl, overlay):
    settings = get_settings()
    monkeypatch.setattr(settings, 'enable_projection_debug_jsonl', jsonl)
    monkeypatch.setattr(settings, 'enable_projection_debug_overlay', overlay)
    counts = dict(jsonl=0, overlay=0, minimap=0, jsonl_closed=0, overlay_closed=0)
    for name, key in [('ProjectionDebugWriter', 'jsonl'), ('ProjectionDebugOverlayWriter', 'overlay')]:
        original = getattr(analysis_pipeline, name)
        def wrap(*args, _original=original, _key=key, **kwargs):
            counts[_key] += 1
            writer = _original(*args, **kwargs)
            close = writer.close
            def counted_close():
                counts[_key + '_closed'] += 1
                return close()
            monkeypatch.setattr(writer, 'close', counted_close)
            return writer
        monkeypatch.setattr(analysis_pipeline, name, wrap)
    minimap = analysis_pipeline.MinimapVisualizer
    def counted_minimap(*args, **kwargs):
        counts['minimap'] += 1
        return minimap(*args, **kwargs)
    monkeypatch.setattr(analysis_pipeline, 'MinimapVisualizer', counted_minimap)
    run_pipeline_case(tmp_path)
    assert counts == dict(jsonl=int(jsonl), overlay=int(overlay), minimap=int(jsonl),
                          jsonl_closed=int(jsonl), overlay_closed=int(overlay))


def test_projection_writers_close_when_tracking_fails(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_projection_debug_jsonl", True)
    monkeypatch.setattr(settings, "enable_projection_debug_overlay", True)
    closed = {"jsonl": 0, "overlay": 0}

    for name, key in (("ProjectionDebugWriter", "jsonl"), ("ProjectionDebugOverlayWriter", "overlay")):
        original = getattr(analysis_pipeline, name)

        def wrap(*args, _original=original, _key=key, **kwargs):
            writer = _original(*args, **kwargs)
            close = writer.close

            def counted_close():
                closed[_key] += 1
                return close()

            monkeypatch.setattr(writer, "close", counted_close)
            return writer

        monkeypatch.setattr(analysis_pipeline, name, wrap)

    class FailingDetector:
        def detect_frame(self, frame, frame_index):
            raise RuntimeError("injected tracking failure")

    monkeypatch.setattr(test_api_smoke, "StaticDetector", FailingDetector)
    # The top-level pipeline reports stage failures instead of leaking them,
    # but the tracking finally block must still release both diagnostics.
    with pytest.raises(AssertionError, match="failed"):
        run_pipeline_case(tmp_path)
    assert closed == {"jsonl": 1, "overlay": 1}
