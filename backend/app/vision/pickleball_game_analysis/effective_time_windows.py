"""比赛有效时间（KCR 分母）三层解析。

- ① job 携带 clip 区间（来自 rally 片段分析）→ 单一窗口；
- ② 关联录制单元存在时间线 rally 事件 → 窗口并集（排除 non-play/暂停/换边）；
- ③ 两者皆无 → None（调用方回退为该球员轨迹总时长）。

纯函数（rally_windows_from_events / resolve_effective_windows）不依赖 DB，可独立测试；
DB 访问封装在 _rally_windows_from_capture_take 内（惰性导入，避免模块导入期硬依赖）。
"""

from __future__ import annotations

from typing import Any, Sequence

# 这些事件类型表示"非比赛状态"：出现在未闭合的 rally 窗口内时终止该窗口。
NON_PLAY_EVENT_TYPES = {
    "non_play_start",
    "non_play_end",
    "timeout_start",
    "timeout_end",
    "side_change",
    "drill_start",
    "drill_end",
}


def rally_windows_from_events(
    events: Sequence[tuple[str, int]],
    *,
    video_duration_ms: int | None = None,
) -> list[tuple[float, float]]:
    """从 (event_type_str, timestamp_ms) 事件序列推导 rally 窗口（秒，半开区间）。

    - rally_start/rally_end 成对构成窗口；
    - 非比赛事件（non-play/timeout/side_change）会终止尚未闭合的窗口；
    - 末尾缺失 rally_end 的窗口钳制到视频时长；
    - 重叠/相邻窗口合并。
    """
    windows: list[tuple[float, float]] = []
    open_start: float | None = None
    for event_type, timestamp_ms in events:
        timestamp = timestamp_ms / 1000.0
        if event_type == "rally_start":
            if open_start is None:
                open_start = timestamp
        elif event_type == "rally_end":
            if open_start is not None:
                windows.append((open_start, timestamp))
                open_start = None
        elif event_type in NON_PLAY_EVENT_TYPES and open_start is not None:
            # 非比赛状态终止未闭合的 rally 窗口。
            windows.append((open_start, timestamp))
            open_start = None

    if open_start is not None:
        end = video_duration_ms / 1000.0 if video_duration_ms is not None else open_start
        if end > open_start:
            windows.append((open_start, end))

    windows = [window for window in windows if window[1] > window[0]]
    windows.sort()
    merged: list[tuple[float, float]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def resolve_effective_windows(
    clip_start_ms: int | None = None,
    clip_end_ms: int | None = None,
    capture_take_id: str | None = None,
    *,
    video_duration_ms: int | None = None,
) -> list[tuple[float, float]] | None:
    """三层解析比赛有效时间窗口（秒，半开区间）。返回 None 表示无比赛数据，调用方回退总时长。"""
    if clip_start_ms is not None and clip_end_ms is not None and clip_end_ms > clip_start_ms:
        return [(clip_start_ms / 1000.0, clip_end_ms / 1000.0)]
    if capture_take_id:
        windows = _rally_windows_from_capture_take(capture_take_id, video_duration_ms=video_duration_ms)
        if windows:
            return windows
    return None


def _rally_windows_from_capture_take(
    capture_take_id: str,
    *,
    video_duration_ms: int | None = None,
) -> list[tuple[float, float]] | None:
    """查询录制单元的时间线 rally 事件并推导窗口；无录制单元或无事件返回 None。"""
    try:
        from app.database import get_session_factory
        from app.services.capture_take_service import get_capture_take
        from app.services.timeline_event_service import list_timeline_events
    except ImportError:  # pragma: no cover - 仅在缺失依赖的极端环境触发
        return None

    db = get_session_factory()()
    try:
        take = get_capture_take(db, capture_take_id)
        if take is None:
            return None
        events = list_timeline_events(db, take.field_session_id, capture_take_id=capture_take_id)
    finally:
        db.close()

    pairs: list[tuple[str, int]] = []
    for event in events:
        event_type: Any = event.event_type
        type_name = event_type.value if hasattr(event_type, "value") else str(event_type)
        pairs.append((type_name, int(event.timestamp_ms)))
    windows = rally_windows_from_events(pairs, video_duration_ms=video_duration_ms)
    return windows or None
