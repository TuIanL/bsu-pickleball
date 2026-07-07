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


@dataclass(frozen=True)
class VisualizationPoint:
    # 一个“球场坐标点”：x_ft/y_ft 为英尺坐标；frame_index/timestamp_seconds 可选；label/source/confidence 为元数据。
    x_ft: float
    y_ft: float
    frame_index: int | None = None
    timestamp_seconds: float | None = None
    label: str | None = None
    source: str = "artifact"
    confidence: float | None = None

    @property
    def court_xy(self) -> Point2D:
        # 以 (x, y) 元组形式暴露坐标，便于与需要 Point2D 的接口对接。
        return (self.x_ft, self.y_ft)


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


def _safe_int(value: Any) -> int | None:
    # 安全地把值转成 int：失败返回 None。
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
