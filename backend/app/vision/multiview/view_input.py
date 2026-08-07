"""多视角输入（view_input）—— MultiViewViewInput：view 的输入组成契约。

`court_orientation` 属于 `CaptureTrack + Calibration` 的绑定关系，挂在 view input 上，
不写入 CaptureTrack 本身，避免污染轨道媒体语义。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.vision.multiview.court_frame import CourtOrientation


@dataclass(frozen=True)
class MultiViewViewInput:
    """一路参与多视角分析的单视角输入（capture_track + video + job + calibration + orientation）。"""

    view_id: str  # 视图标识，如 "cam_1"
    capture_track_id: str
    video_id: str
    analysis_job_id: str
    calibration_id: str
    # None = 尚未声明（job-level fallback，绝不猜测）。
    court_orientation: CourtOrientation | None = None
