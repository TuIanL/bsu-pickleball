"""Future YOLO11 detector adapter.

Expected normalization:
- person/player boxes use label `player`
- pickleball boxes use label `ball`
- paddle boxes use label `paddle`
- court-line or court-region detections use court-specific labels
- all boxes are pixel coordinates in the original frame before court mapping

The lightweight backend deliberately does not import ultralytics here. Add that
dependency only when the real detector spike begins.
"""

from app.vision.detectors.base import Detection


class Yolo11DetectorAdapter:
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def detect(self, frame_path: str) -> list[Detection]:
        raise NotImplementedError(
            "YOLO11 integration is reserved for the real vision phase; "
            f"would run {self.model_path} on {frame_path}."
        )
