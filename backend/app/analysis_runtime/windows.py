"""有界窗口与事件选择纯函数。"""
from __future__ import annotations
from app.analysis_runtime.contracts import Window
from app.analysis_runtime.hashing import AnalysisRuntimeError


def clamp_window(window: Window, duration_ms: int) -> Window:
    start, end = max(0, window.start_ms), min(duration_ms, window.end_ms)
    if end <= start:
        raise AnalysisRuntimeError("window_no_media_intersection", "窗口与媒体无有效交集")
    return Window(start_ms=start, end_ms=end)


def selected(event: dict, window: Window, selector: str) -> bool:
    if selector == "sample_time.v1":
        return window.start_ms <= event["time_ms"] < window.end_ms
    if selector == "contact_time.v1":
        contact = event.get("contact_ms")
        return contact is not None and window.start_ms <= contact < window.end_ms
    if selector == "interval_intersects.v1":
        return event["start_ms"] < window.end_ms and event["end_ms"] > window.start_ms
    raise AnalysisRuntimeError("unknown_output_selector", selector)
