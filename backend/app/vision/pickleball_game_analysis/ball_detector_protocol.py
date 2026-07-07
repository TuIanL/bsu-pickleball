"""Detector protocol for ball candidate providers."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from app.vision.pickleball_game_analysis.schemas import BallCandidate


class BallDetectorProtocol(Protocol):
    def detect(self, frame: np.ndarray, conf: float = 0.18) -> list[BallCandidate]:
        """Return ball candidates for one image frame."""
