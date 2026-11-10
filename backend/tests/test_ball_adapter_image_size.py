from types import SimpleNamespace

from app.vision.detectors.ball_adapter import YoloBallDetectorAdapter


def test_basic_ball_resolution_can_be_increased_without_changing_legacy_default():
    for size in (None, 1280):
        calls = []
        adapter = YoloBallDetectorAdapter(device="cpu", image_size=size)
        adapter._model = SimpleNamespace(predict=lambda *a, **kw: calls.append(kw) or [])
        assert adapter.detect(object(), conf=.25) == []
        assert calls[0]["device"] == "cpu" and calls[0]["conf"] == .25
        if size is None:
            assert "imgsz" not in calls[0]
        else:
            assert calls[0]["imgsz"] == 1280
