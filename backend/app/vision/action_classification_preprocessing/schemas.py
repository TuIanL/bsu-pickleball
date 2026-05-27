"""配置和 manifest 结构，用于动作分类训练样本导出。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


SelectionStrategy = Literal["largest", "near-left", "near-right", "track-iou", "manual-initial-bbox"]
MissingFramePolicy = Literal["skip"]


class ActionPreprocessingError(ValueError):
    """Raised when action preprocessing cannot proceed with the supplied inputs."""


@dataclass(frozen=True)
class ROIConfig:
    x1_ratio: float = 0.02
    y1_ratio: float = 0.30
    x2_ratio: float = 0.98
    y2_ratio: float = 0.98

    def __post_init__(self) -> None:
        values = (self.x1_ratio, self.y1_ratio, self.x2_ratio, self.y2_ratio)
        if not all(0.0 <= value <= 1.0 for value in values):
            raise ActionPreprocessingError("ROI ratios must be between 0 and 1")
        if not self.x1_ratio < self.x2_ratio:
            raise ActionPreprocessingError("ROI x1_ratio must be less than x2_ratio")
        if not self.y1_ratio < self.y2_ratio:
            raise ActionPreprocessingError("ROI y1_ratio must be less than y2_ratio")


@dataclass(frozen=True)
class CLAHEConfig:
    enabled: bool = True
    clip_limit: float = 2.0
    tile_grid_size: int = 8

    def __post_init__(self) -> None:
        if self.clip_limit <= 0:
            raise ActionPreprocessingError("CLAHE clip_limit must be greater than 0")
        if self.tile_grid_size <= 0:
            raise ActionPreprocessingError("CLAHE tile_grid_size must be greater than 0")


@dataclass(frozen=True)
class DenoiseConfig:
    enabled: bool = False
    kernel_size: int = 3
    sigma: float = 0.0

    def __post_init__(self) -> None:
        if self.kernel_size <= 0 or self.kernel_size % 2 == 0:
            raise ActionPreprocessingError("Denoise kernel_size must be a positive odd integer")
        if self.sigma < 0:
            raise ActionPreprocessingError("Denoise sigma must be greater than or equal to 0")


@dataclass(frozen=True)
class ActionPreprocessingConfig:
    input_path: Path | str
    output_root: Path | str
    label: str
    target_fps: float = 20.0
    roi: ROIConfig = field(default_factory=ROIConfig)
    clahe: CLAHEConfig = field(default_factory=CLAHEConfig)
    detect_on_enhanced: bool = False
    denoise: DenoiseConfig = field(default_factory=DenoiseConfig)
    detector_model_path: str = "yolo11n.pt"
    detector_confidence: float = 0.5
    detector_device: str | None = None
    selection_strategy: SelectionStrategy = "largest"
    manual_initial_bbox: list[float] | None = None
    missing_frame_policy: MissingFramePolicy = "skip"
    bbox_expand_scale: float = 1.4
    output_size: int = 224
    clip_length: int = 16
    clip_stride: int = 16
    jpeg_quality: int = 95
    overwrite: bool = False
    start_seconds: float = 0.0
    end_seconds: float | None = None
    manifest_name: str = "manifest.json"

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_path", Path(self.input_path).expanduser())
        object.__setattr__(self, "output_root", Path(self.output_root).expanduser())
        object.__setattr__(self, "label", self.label.strip())
        if not self.label:
            raise ActionPreprocessingError("label must not be empty")
        if self.target_fps <= 0:
            raise ActionPreprocessingError("target_fps must be greater than 0")
        if not 0.0 <= self.detector_confidence <= 1.0:
            raise ActionPreprocessingError("detector_confidence must be between 0 and 1")
        if self.selection_strategy not in {"largest", "near-left", "near-right", "track-iou", "manual-initial-bbox"}:
            raise ActionPreprocessingError(f"Unknown selection_strategy: {self.selection_strategy}")
        if self.selection_strategy == "manual-initial-bbox" and self.manual_initial_bbox is None:
            raise ActionPreprocessingError("manual_initial_bbox is required for manual-initial-bbox strategy")
        if self.manual_initial_bbox is not None:
            _validate_bbox(self.manual_initial_bbox, "manual_initial_bbox")
        if self.missing_frame_policy != "skip":
            raise ActionPreprocessingError(f"Unknown missing_frame_policy: {self.missing_frame_policy}")
        if self.bbox_expand_scale <= 0:
            raise ActionPreprocessingError("bbox_expand_scale must be greater than 0")
        if self.output_size <= 0:
            raise ActionPreprocessingError("output_size must be greater than 0")
        if self.clip_length <= 0:
            raise ActionPreprocessingError("clip_length must be greater than 0")
        if self.clip_stride <= 0:
            raise ActionPreprocessingError("clip_stride must be greater than 0")
        if not 1 <= self.jpeg_quality <= 100:
            raise ActionPreprocessingError("jpeg_quality must be between 1 and 100")
        if self.start_seconds < 0:
            raise ActionPreprocessingError("start_seconds must be greater than or equal to 0")
        if self.end_seconds is not None and self.end_seconds < self.start_seconds:
            raise ActionPreprocessingError("end_seconds must be greater than or equal to start_seconds")
        if not self.manifest_name.endswith(".json"):
            raise ActionPreprocessingError("manifest_name must end with .json")

    def to_manifest_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["input_path"] = str(self.input_path)
        payload["output_root"] = str(self.output_root)
        return payload


@dataclass(frozen=True)
class ROIRecord:
    ratios: dict[str, float]
    bbox: list[int]
    source_width: int
    source_height: int

    @property
    def offset(self) -> list[int]:
        return [self.bbox[0], self.bbox[1]]


@dataclass
class FrameSample:
    source_path: str
    frame_index: int
    timestamp_seconds: float
    output_path: str
    file_name: str
    roi: dict[str, Any]
    detection_count: int
    selection_strategy: str
    confidence: float
    bbox_roi: list[float]
    bbox_source: list[float]
    crop_bbox_roi: list[int]
    crop_bbox_source: list[int]


@dataclass
class ClipRecord:
    label: str
    video_stem: str
    clip_index: int
    output_dir: str
    frames: list[FrameSample]


@dataclass
class VideoManifest:
    source_path: str
    source_name: str
    output_stem: str
    fps: float | None = None
    frame_count: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    processed_frame_count: int = 0
    selected_frame_count: int = 0
    skipped_frame_count: int = 0
    clips_written: int = 0
    frames_written: int = 0
    clips: list[ClipRecord] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def dataclass_to_dict(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: dataclass_to_dict(item) for key, item in value.items()}
    return value


def _validate_bbox(values: list[float], label: str) -> None:
    if len(values) != 4:
        raise ActionPreprocessingError(f"{label} must contain exactly four numbers")
    x1, y1, x2, y2 = [float(value) for value in values]
    if not x1 < x2 or not y1 < y2:
        raise ActionPreprocessingError(f"{label} must be [x1, y1, x2, y2] with positive width and height")
