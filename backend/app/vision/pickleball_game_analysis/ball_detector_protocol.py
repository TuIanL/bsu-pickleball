"""Detector protocol for ball candidate providers."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from app.vision.pickleball_game_analysis.schemas import BallCandidate


class BallDetectorProtocol(Protocol):
    """
    球检测器的"接口约定"（Protocol = 结构化类型，也叫鸭子类型接口）。

    Protocol 不要求显式继承，只要某个类实现了 detect() 方法、签名匹配，
    就被视为"满足这个协议"。这样 BallTracker 可以接受任意球检测器实现。

    实现者需提供的接口：
        detect(frame, conf=0.18) -> list[BallCandidate]
        （对一帧图像返回若干球候选框，conf 为置信度阈值）
    """

    def detect(self, frame: np.ndarray, conf: float = 0.18) -> list[BallCandidate]:
        """Return ball candidates for one image frame."""
