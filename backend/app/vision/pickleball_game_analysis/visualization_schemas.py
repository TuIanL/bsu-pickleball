"""Visualization helpers for match-analysis artifacts."""

from __future__ import annotations

import json  # JSON 序列化（写出清单文件）
# dataclass 相关：asdict（转字典）、dataclass、field（自定义字段）、is_dataclass（判断）。
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum  # 枚举类型（处理枚举值的序列化）
from math import isfinite  # 判断浮点是否有限（排除 NaN/inf）
from pathlib import Path  # 面向对象的文件路径
from typing import Any  # 宽松类型标注

# 球场单位换算：meters_to_feet（米→英尺）、normalize_court_unit（归一化单位字符串）。
from app.vision.courtvision_calibration_engine.court_units import (
    meters_to_feet,
    normalize_court_unit,
)
# 二维点类型 Point2D（用于 court_xy 属性返回）。
from app.vision.pickleball_game_analysis.schemas import Point2D


@dataclass(frozen=True)
class VisualizationConfig:
    # 小地图与静态图的尺寸、网格、拖尾长度等配置（单位：像素；trail_length 为帧数；language 控制标签语言）。
    minimap_width: int = 220
    minimap_height: int = 420
    minimap_padding: int = 16
    image_width: int = 720
    image_height: int = 1280
    heatmap_rows: int = 22
    heatmap_cols: int = 10
    trail_length: int = 20
    language: str = "zh-CN"
    minimap_player_trail_seconds: float = 2.5


@dataclass(frozen=True)
class VisualizationPoint:
    # 一个"球场坐标点"：x_ft/y_ft 为英尺坐标；frame_index/timestamp_seconds 可选；label/source/confidence 为元数据。
    x_ft: float
    y_ft: float
    frame_index: int | None = None
    timestamp_seconds: float | None = None
    label: str | None = None
    source: str = "artifact"
    confidence: float | None = None
    # 投影状态（inside_court / outside_court_visible / outside_tracking_area / projection_failed）
    projection_status: str | None = None
    # 脚点估计方法（bbox_bottom_center / pose_ankle_midpoint / ...）
    footpoint_method: str | None = None
    # 投影可信度（0~1）
    projection_confidence: float | None = None
    # 渲染 segment ID（v2 artifact 中携带，用于 OverlayVideoWriter 断段检测）
    segment_id: str | None = None

    @property
    def court_xy(self) -> Point2D:
        # 以 (x, y) 元组形式暴露坐标，便于与需要 Point2D 的接口对接。
        return (self.x_ft, self.y_ft)


@dataclass(frozen=True)
class CourtVisualizationStyleProfile:
    version: str = "court-visual-theme.v1"
    players: dict[str, str] = field(default_factory=lambda: {
        "slot_1": "#22D3EE",
        "slot_2": "#FBBF24",
        "slot_3": "#A78BFA",
        "slot_4": "#F97316",
    })
    ball: str = "#67E8F9"
    bounce: str = "#FB923C"
    outside_player: str = "#94A3B8"
    player_trail_seconds: float = 2.5
    ball_trail_seconds: float = 1.0
    bounce_display_seconds: float = 0.8
    radius_min_px: float = 2.0
    radius_max_px: float = 6.0


@dataclass(frozen=True)
class CourtTrackSegmentationProfile:
    version: str = "court-track-segmentation.v1"
    jump_threshold_ft: float = 9.84
    max_visible_gap_seconds: float = 0.75


@dataclass(frozen=True)
class CourtTrackSegmentationProfile:
    version: str = "court-track-segmentation.v1"
    jump_threshold_ft: float = 9.84
    max_visible_gap_seconds: float = 0.75


def load_render_profiles() -> tuple[CourtVisualizationStyleProfile, CourtTrackSegmentationProfile]:
    """从 package resource 加载渲染 profile，不可用时使用内置默认值。"""
    try:
        from importlib.resources import files as resource_files
        profile_json = resource_files("app.resources").joinpath("court_render_profile.v1.json").read_text(encoding="utf-8")
        raw = json.loads(profile_json)
    except Exception:
        return CourtVisualizationStyleProfile(), CourtTrackSegmentationProfile()

    raw_style = raw.get("style_profile", {})
    style = CourtVisualizationStyleProfile(
        version=raw_style.get("version", "court-visual-theme.v1"),
        players=raw_style.get("players", {}),
        ball=raw_style.get("ball", "#67E8F9"),
        bounce=raw_style.get("bounce", "#FB923C"),
        outside_player=raw_style.get("outside_player", "#94A3B8"),
        player_trail_seconds=raw_style.get("player_trail_seconds", 2.5),
        ball_trail_seconds=raw_style.get("ball_trail_seconds", 1.0),
        bounce_display_seconds=raw_style.get("bounce_display_seconds", 0.8),
        radius_min_px=raw_style.get("radius_min_px", 2.0),
        radius_max_px=raw_style.get("radius_max_px", 6.0),
    )

    raw_seg = raw.get("segmentation_profile", {})
    seg = CourtTrackSegmentationProfile(
        version=raw_seg.get("version", "court-track-segmentation.v1"),
        jump_threshold_ft=raw_seg.get("jump_threshold_ft", 9.84),
        max_visible_gap_seconds=raw_seg.get("max_visible_gap_seconds", 0.75),
    )

    return style, seg


@dataclass(frozen=True)
class ManifestItem:
    # 可视化产物的“清单条目”：描述一张图/视频的元数据（id、种类、标题、文件路径、URL、尺寸、来源 artifact）。
    id: str
    kind: str
    label: str
    title: str
    description: str
    file_name: str
    file_path: str
    url: str
    artifact_url: str
    width: int
    height: int
    source_artifacts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VisualizationResult:
    # 一次可视化操作的统一结果：status（available/unavailable/failed/no_data）、detail 文案、path/url、item_count。
    status: str
    detail: str
    path: str | None = None
    url: str | None = None
    item_count: int = 0


# ── 结构化可视化数据（前端 SVG 渲染用） ──────────────────────────────


@dataclass(frozen=True)
class CourtGeometry:
    """球场物理尺寸（英尺）。"""
    court_width_ft: float = 20.0
    court_length_ft: float = 44.0


@dataclass(frozen=True)
class HeatmapCell:
    """热力图网格中的一个单元格。"""
    row: int
    col: int
    count: int


@dataclass(frozen=True)
class VisualGrid:
    """22×10 热力图网格，用于前端 SVG 渲染。"""
    rows: int = 22
    cols: int = 10
    max_count: int = 0
    cells: list[HeatmapCell] = field(default_factory=list)


@dataclass(frozen=True)
class ScatterPlayer:
    """散点图中的一个球员。"""
    id: str
    label: str
    color: str
    points: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class ScatterPlots:
    """散点图数据：球员 + 球 + 弹跳点。"""
    players: list[ScatterPlayer] = field(default_factory=list)
    ball: list[tuple[float, float]] = field(default_factory=list)
    bounces: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerTrajectory:
    """单个球员的轨迹路径。"""
    id: str
    label: str
    path: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredVisualizationData:
    """前端 SVG 渲染所需的全部结构化数据。

    由 PositionVisualizationDataBuilder 构建，
    写入 position_visualizations/structured/ 目录，
    通过 GET /visualization-data 端点暴露给前端。
    """
    court: CourtGeometry = field(default_factory=CourtGeometry)
    heatmaps: VisualGrid | None = None
    scatter_plots: ScatterPlots = field(default_factory=ScatterPlots)
    player_trajectories: list[PlayerTrajectory] = field(default_factory=list)
    outside_court_point_count: int = 0
    dropped_point_count: int = 0


# 多语言标签表：键为语言代码，值为 {标签键: 文案}。当前支持中文(zh-CN)与英文(en-US)。
LABELS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "player": "球员",
        "ball": "球",
        "bounce": "弹跳候选",
        "speed": "速度",
        "distance": "距离",
        "frame_time": "时间",
        "player_heatmap": "球员位置热力图",
        "player_scatter": "球员位置散点图",
        "ball_scatter": "球轨迹散点图",
        "bounce_scatter": "弹跳候选散点图",
        "no_data": "没有可用坐标点",
    },
    "en-US": {
        "player": "Player",
        "ball": "Ball",
        "bounce": "Bounce candidate",
        "speed": "Speed",
        "distance": "Distance",
        "frame_time": "Time",
        "player_heatmap": "Player position heatmap",
        "player_scatter": "Player position scatter plot",
        "ball_scatter": "Ball trajectory scatter plot",
        "bounce_scatter": "Bounce candidate scatter plot",
        "no_data": "No valid court points",
    },
}


def labels_for(language: str | None) -> dict[str, str]:
    # 按语言取标签表；语言为空或未知时回退到中文标签。
    return LABELS.get(language or "", LABELS["zh-CN"])


def jsonable(value: Any) -> Any:
    # 把任意数据结构递归转成可 JSON 序列化的形式：
    # dataclass→字典；Enum→其 value；dict→递归；tuple/list→列表；numpy 标量→标量；
    # 非有限浮点→None（避免 JSON 写出 NaN/Infinity 非法值）。
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return jsonable(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return value if isfinite(value) else None
    return value


def write_manifest(
    path: Path,
    *,
    schema_version: str,
    job_id: str,
    status: str,
    detail: str,
    items: list[ManifestItem],
) -> Path:
    # 把一组清单条目写出为带 schema 版本/任务号/状态的 JSON 清单文件。
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": schema_version,
        "job_id": job_id,
        "status": status,
        "detail": detail,
        "items": [jsonable(item) for item in items],
    }
    # ensure_ascii=False 保留中文；indent=2 美化格式。
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def safe_float(value: Any) -> float | None:
    # 安全地把值转成浮点：转换失败或非有限值都返回 None。
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def normalize_court_point(value: Any, unit: str | None = None) -> Point2D | None:
    """Return a point in feet, accepting common artifact point shapes."""

    # 把 artifact 里各种形状的“点”统一规范为英尺坐标 (x, y)。
    x: float | None = None
    y: float | None = None
    point_unit = unit
    if isinstance(value, dict):
        # dict 形式：优先 x/court_x、y/court_y，并读取 unit 字段。
        x = safe_float(value.get("x") if "x" in value else value.get("court_x"))
        y = safe_float(value.get("y") if "y" in value else value.get("court_y"))
        point_unit = value.get("unit") or value.get("court_unit") or point_unit
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        # 序列形式：[x, y, ...]
        x = safe_float(value[0])
        y = safe_float(value[1])
    if x is None or y is None:
        return None

    # 单位归一化；若为米则换算成英尺。
    normalized_unit = normalize_court_unit(point_unit) or "ft"
    if normalized_unit == "m":
        x = meters_to_feet(x)
        y = meters_to_feet(y)
    return (x, y)


def artifact_court_unit(payload: dict[str, Any], default: str | None = None) -> str | None:
    # 从 artifact 顶层结构推断球场坐标单位：依次看 court.unit / coordinate_system.court(court_unit/unit)。
    court = payload.get("court")
    if isinstance(court, dict):
        unit = court.get("court_unit") or court.get("unit")
        if unit:
            return str(unit)
    coordinate_system = payload.get("coordinate_system")
    if isinstance(coordinate_system, dict):
        unit = coordinate_system.get("court") or coordinate_system.get("court_unit") or coordinate_system.get("unit")
        if unit:
            return str(unit)
    return default


def player_points_from_artifact(payload: dict[str, Any]) -> list[VisualizationPoint]:
    # 从 players_trajectory artifact（{player_id: [采样...]}）解析出 VisualizationPoint 列表。
    points: list[VisualizationPoint] = []
    default_unit = artifact_court_unit(payload, "m")  # 球员轨迹默认按米理解
    players = payload.get("players")
    if not isinstance(players, dict):
        return points
    for player_id, samples in players.items():
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            unit = sample.get("court_unit") or default_unit
            # 优先用平滑后的坐标。
            x = sample.get("smoothed_court_x", sample.get("court_x"))
            y = sample.get("smoothed_court_y", sample.get("court_y"))
            point = normalize_court_point([x, y], unit)
            if point is None:
                continue
            points.append(
                VisualizationPoint(
                    x_ft=point[0],
                    y_ft=point[1],
                    frame_index=_safe_int(sample.get("frame_index")),
                    timestamp_seconds=safe_float(sample.get("timestamp_seconds")),
                    label=str(player_id),
                    source="players_trajectory",
                    confidence=safe_float(sample.get("confidence")),
                )
            )
    return points


def ball_points_from_artifact(payload: dict[str, Any], *, source: str = "cleaned_ball_trajectory") -> list[VisualizationPoint]:
    # 从球轨迹 artifact（{samples: [...]}）解析出 VisualizationPoint 列表。
    points: list[VisualizationPoint] = []
    default_unit = artifact_court_unit(payload, "ft")  # 球轨迹默认按英尺
    samples = payload.get("samples")
    if not isinstance(samples, list):
        return points
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        # 球点坐标在 court_xy 字段里。
        point = normalize_court_point(sample.get("court_xy"), default_unit)
        if point is None:
            continue
        points.append(
            VisualizationPoint(
                x_ft=point[0],
                y_ft=point[1],
                frame_index=_safe_int(sample.get("frame_index")),
                timestamp_seconds=safe_float(sample.get("timestamp_sec") or sample.get("timestamp_seconds")),
                label="ball",
                source=source,
                confidence=safe_float(sample.get("confidence")),
            )
        )
    return points


def bounce_points_from_artifact(payload: dict[str, Any]) -> list[VisualizationPoint]:
    # 从弹跳事件 artifact（{events: [...]}）解析出 VisualizationPoint 列表。
    points: list[VisualizationPoint] = []
    default_unit = artifact_court_unit(payload, "ft")
    events = payload.get("events")
    if not isinstance(events, list):
        return points
    for event in events:
        if not isinstance(event, dict):
            continue
        point = normalize_court_point(event.get("court_xy"), default_unit)
        if point is None:
            continue
        points.append(
            VisualizationPoint(
                x_ft=point[0],
                y_ft=point[1],
                frame_index=_safe_int(event.get("frame_index")),
                timestamp_seconds=safe_float(event.get("timestamp_sec") or event.get("timestamp_seconds")),
                label=str(event.get("event_id") or "bounce"),
                source="bounce_events",
                confidence=safe_float(event.get("confidence")),
            )
        )
    return points


def player_render_points_from_artifact(payload: dict[str, Any]) -> list[VisualizationPoint]:
    points: list[VisualizationPoint] = []
    players = payload.get("players")
    if not isinstance(players, dict):
        samples = payload.get("samples")
        if isinstance(samples, list):
            return _parse_render_samples(samples)
        return points
    for player_id, samples in players.items():
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            x = safe_float(sample.get("x_ft"))
            y = safe_float(sample.get("y_ft"))
            if x is None or y is None:
                continue
            points.append(VisualizationPoint(
                x_ft=x,
                y_ft=y,
                frame_index=_safe_int(sample.get("frame_index")),
                timestamp_seconds=safe_float(sample.get("timestamp_seconds")),
                label=str(player_id),
                source=sample.get("source", "render"),
                confidence=safe_float(sample.get("confidence")),
            ))
    return points


def _parse_render_samples(samples: list[dict[str, Any]]) -> list[VisualizationPoint]:
    points: list[VisualizationPoint] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        x = safe_float(sample.get("x_ft"))
        y = safe_float(sample.get("y_ft"))
        if x is None or y is None:
            continue
        player_id = str(sample.get("player_id", "unknown"))
        points.append(VisualizationPoint(
            x_ft=x,
            y_ft=y,
            frame_index=_safe_int(sample.get("frame_index")),
            timestamp_seconds=safe_float(sample.get("timestamp_seconds")),
            label=player_id,
            source=sample.get("source", "render"),
            confidence=safe_float(sample.get("confidence")),
            projection_status=sample.get("projection_status"),
            footpoint_method=sample.get("footpoint_method"),
            projection_confidence=safe_float(sample.get("projection_confidence")),
            segment_id=sample.get("segment_id"),
        ))
    return points


def serialize_render_trajectory_v2(
    result: dict[str, Any],
    style_profile: CourtVisualizationStyleProfile | None = None,
    segmentation_profile: CourtTrackSegmentationProfile | None = None,
) -> dict[str, Any]:
    from app.vision.pickleball_game_analysis.court_track_types import (
        RenderPlayerMetadata,
        RenderSegmentMetadata,
    )
    payload: dict[str, Any] = {
        "schema_version": "player-render-trajectory.v2",
        "players": [
            {
                "player_id": p.player_id if isinstance(p, RenderPlayerMetadata) else p.get("player_id", ""),
                "render_slot": p.render_slot if isinstance(p, RenderPlayerMetadata) else p.get("render_slot", ""),
                "initial_side": p.initial_side if isinstance(p, RenderPlayerMetadata) else p.get("initial_side", "unknown"),
                "dominant_side": p.dominant_side if isinstance(p, RenderPlayerMetadata) else p.get("dominant_side", "unknown"),
                "first_frame_index": p.first_frame_index if isinstance(p, RenderPlayerMetadata) else p.get("first_frame_index", 0),
                "source_track_ids": p.source_track_ids if isinstance(p, RenderPlayerMetadata) else p.get("source_track_ids", []),
            }
            for p in result.get("players", [])
        ],
        "segments": [
            {
                "segment_id": s.segment_id if isinstance(s, RenderSegmentMetadata) else s.get("segment_id", ""),
                "player_id": s.player_id if isinstance(s, RenderSegmentMetadata) else s.get("player_id", ""),
                "identity_epoch": s.identity_epoch if isinstance(s, RenderSegmentMetadata) else s.get("identity_epoch", 0),
                "start_frame_index": s.start_frame_index if isinstance(s, RenderSegmentMetadata) else s.get("start_frame_index", 0),
                "end_frame_index": s.end_frame_index if isinstance(s, RenderSegmentMetadata) else s.get("end_frame_index", 0),
                "start_timestamp_seconds": s.start_timestamp_seconds if isinstance(s, RenderSegmentMetadata) else s.get("start_timestamp_seconds", 0),
                "end_timestamp_seconds": s.end_timestamp_seconds if isinstance(s, RenderSegmentMetadata) else s.get("end_timestamp_seconds", 0),
                "break_before": s.break_before if isinstance(s, RenderSegmentMetadata) else s.get("break_before", "start"),
                "sample_count": s.sample_count if isinstance(s, RenderSegmentMetadata) else s.get("sample_count", 0),
            }
            for s in result.get("segments", [])
        ],
        "samples": [
            _sample_to_dict(s) for s in result.get("samples", [])
        ],
    }
    if style_profile is not None:
        payload["style_profile"] = {
            "version": style_profile.version,
            "players": style_profile.players,
            "ball": style_profile.ball,
            "bounce": style_profile.bounce,
            "outside_player": style_profile.outside_player,
            "player_trail_seconds": style_profile.player_trail_seconds,
            "ball_trail_seconds": style_profile.ball_trail_seconds,
            "bounce_display_seconds": style_profile.bounce_display_seconds,
            "radius_min_px": style_profile.radius_min_px,
            "radius_max_px": style_profile.radius_max_px,
        }
    if segmentation_profile is not None:
        payload["segmentation_profile"] = {
            "version": segmentation_profile.version,
            "jump_threshold_ft": segmentation_profile.jump_threshold_ft,
            "max_visible_gap_seconds": segmentation_profile.max_visible_gap_seconds,
        }
    return payload


def _sample_to_dict(sample: Any) -> dict[str, Any]:
    from app.vision.pickleball_game_analysis.court_track_types import RenderFrame
    if isinstance(sample, RenderFrame):
        return {
            "sequence_index": sample.sequence_index,
            "frame_index": sample.frame_index,
            "timestamp_seconds": sample.timestamp_seconds,
            "x_ft": sample.x_ft,
            "y_ft": sample.y_ft,
            "source": sample.source,
            "confidence": sample.confidence,
            "player_id": sample.player_id,
            "render_slot": sample.render_slot,
            "side": sample.side,
            "segment_id": sample.segment_id,
            "identity_epoch": sample.identity_epoch,
            "source_track_id": sample.source_track_id,
            "projection_status": sample.projection_status,
            "projection_confidence": sample.projection_confidence,
            "footpoint_method": sample.footpoint_method,
        }
    if isinstance(sample, dict):
        return {
            "sequence_index": sample.get("sequence_index", 0),
            "frame_index": sample.get("frame_index", 0),
            "timestamp_seconds": sample.get("timestamp_seconds", 0),
            "x_ft": sample.get("x_ft", 0),
            "y_ft": sample.get("y_ft", 0),
            "source": sample.get("source", ""),
            "confidence": sample.get("confidence"),
            "player_id": sample.get("player_id", ""),
            "render_slot": sample.get("render_slot", ""),
            "side": sample.get("side", "unknown"),
            "segment_id": sample.get("segment_id", ""),
            "identity_epoch": sample.get("identity_epoch", 0),
            "source_track_id": sample.get("source_track_id"),
            "projection_status": sample.get("projection_status"),
            "projection_confidence": sample.get("projection_confidence"),
            "footpoint_method": sample.get("footpoint_method"),
        }
    return sample


def canonical_player_id(value: str) -> str:
    if value.startswith("player_"):
        return "Player_" + value.removeprefix("player_")
    return value


def _safe_int(value: Any) -> int | None:
    # 安全地把值转成 int：失败返回 None。
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
