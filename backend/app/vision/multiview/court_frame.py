"""
多视角球场坐标系（court_frame）—— 两级球场坐标系、CourtOrientation 与 Canonical Court Frame 定义。

本模块定义多视角分析（Multi-view Player Trajectory Fusion）的坐标系契约：

1. **Legacy / Local Camera Court Frame**（现有单视角体系沿用）
   现有四角标定实际产生 `local y=0 = image-top / camera-far end`、
   `local y=44 = image-bottom / camera-near end`。历史单视角 artifact 与算法
   保持该行为，本模块不修改、不重解释。

2. **Canonical Physical Court Frame**（Fusion 层专用）
   端点使用物理命名：`end_a` @ canonical y=0、`end_b` @ canonical y=44；
   边线使用 `sideline_a` @ canonical x=0、`sideline_b` @ canonical x=20。
   canonical 帧不使用 `near/far` 作为端点名称。

`CourtOrientation` 表示某一路 view（CaptureTrack + Calibration）从
Local Camera Court Frame 到 Canonical Physical Court Frame 的仿射变换。
P0 仅支持 axis-preserving（保轴）标定视角：对向底线机位、底线类高位机位；
任意 sideline 朝向或 local x/y 轴交换的标定视为不支持。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import uuid4

# 标准球场尺寸（英尺），与 court_geometry.PickleballCourtGeometry 保持一致。
COURT_WIDTH_FT = 20.0
COURT_LENGTH_FT = 44.0

# CourtOrientation 的显式枚举：4 个保轴（axis-preserving）变换。
class CourtOrientation(StrEnum):
    """Local Camera Court Frame → Canonical Physical Court Frame 的保轴仿射变换。"""

    identity = "identity"  # (x, y) -> (x, y)
    rotate_180 = "rotate_180"  # (x, y) -> (20 - x, 44 - y)
    mirror_x = "mirror_x"  # (x, y) -> (20 - x, y)
    mirror_y = "mirror_y"  # (x, y) -> (x, 44 - y)


# 类型别名：P0 只接受这 4 个取值；未声明用 None，不引入第五种朝向。
CourtOrientationLiteral = Literal["identity", "rotate_180", "mirror_x", "mirror_y"]


def _rotate_180(x: float, y: float) -> tuple[float, float]:
    return (COURT_WIDTH_FT - x, COURT_LENGTH_FT - y)


def _mirror_x(x: float, y: float) -> tuple[float, float]:
    return (COURT_WIDTH_FT - x, y)


def _mirror_y(x: float, y: float) -> tuple[float, float]:
    return (x, COURT_LENGTH_FT - y)


def _identity(x: float, y: float) -> tuple[float, float]:
    return (x, y)


_ORIENTATION_TRANSFORMS: dict[CourtOrientation, object] = {
    CourtOrientation.identity: _identity,
    CourtOrientation.rotate_180: _rotate_180,
    CourtOrientation.mirror_x: _mirror_x,
    CourtOrientation.mirror_y: _mirror_y,
}


def local_to_canonical(
    x: float,
    y: float,
    orientation: CourtOrientation | None,
) -> tuple[float, float]:
    """把 Local Camera Court Frame 坐标变换为 Canonical Physical Court Frame 坐标。

    未声明朝向（None）时抛错：不知道 local 帧如何对齐 canonical，禁止投影式猜测。
    """
    if orientation is None:
        raise ValueError("court_orientation is None: cannot normalize local coordinates without a declared orientation")
    return _ORIENTATION_TRANSFORMS[orientation](float(x), float(y))


def canonical_to_local(
    x: float,
    y: float,
    orientation: CourtOrientation | None,
) -> tuple[float, float]:
    """把 Canonical Physical Court Frame 坐标变换回 Local Camera Court Frame 坐标。

    4 个变换均为对合（自逆），故反向变换与正向相同；此函数仅为语义清晰的别名。
    """
    return local_to_canonical(x, y, orientation)


# 两级球场坐标系的文档契约（供调试/报告引用）。
LOCAL_COURT_FRAME_SEMANTICS = {
    "name": "Legacy / Local Camera Court Frame",
    "y_0": "image-top / camera-far end",
    "y_44": "image-bottom / camera-near end",
    "note": "现有单视角体系沿用，不修改、不重解释历史 artifact",
}

CANONICAL_COURT_FRAME_SEMANTICS = {
    "name": "Canonical Physical Court Frame",
    "end_a": {"canonical_y": 0.0, "note": "不使用 near/far 作为端点名称"},
    "end_b": {"canonical_y": COURT_LENGTH_FT, "note": "不使用 near/far 作为端点名称"},
    "sideline_a": {"canonical_x": 0.0},
    "sideline_b": {"canonical_x": COURT_WIDTH_FT},
}

# P0 支持范围：axis-preserving（保轴）标定视角。
# 典型：对向底线机位（opposing baseline）、底线类高位机位（baseline-like elevated）。
AXIS_PRESERVING_VIEW_TYPES: tuple[str, ...] = ("baseline", "elevated_baseline")


def is_supported_orientation_scope(view_type: str | None) -> bool:
    """判断机位拍摄类型是否落在 P0 的 axis-preserving 支持范围内。

    未知类型返回 False：无法确认保轴，视为不支持（job-level fallback）。
    """
    if view_type is None:
        return False
    return view_type in AXIS_PRESERVING_VIEW_TYPES


@dataclass(frozen=True)
class CanonicalCourtFrameDefinition:
    """一次多视角分析所用的 canonical 球场帧定义（首次配置后持久化）。

    同一 take 的多次分析 MUST 引用同一 `frame_id`，禁止每次重跑重新选定端点，
    否则两次 artifact 会整体翻转却都自称 canonical，无法比较。
    """

    frame_id: str
    capture_take_id: str
    end_a_definition: str  # 物理端点 A 的描述（如"北端底线"）
    end_b_definition: str  # 物理端点 B 的描述
    created_at: str
    schema_version: str = "canonical_court_frame.v1"
    orientation_by_view: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        capture_take_id: str,
        end_a_definition: str,
        end_b_definition: str,
        *,
        created_at: str | None = None,
        orientation_by_view: dict[str, str] | None = None,
    ) -> CanonicalCourtFrameDefinition:
        return cls(
            frame_id=f"ccf_{uuid4().hex[:12]}",
            capture_take_id=capture_take_id,
            end_a_definition=end_a_definition,
            end_b_definition=end_b_definition,
            created_at=created_at or datetime.now(UTC).isoformat(),
            orientation_by_view=dict(orientation_by_view or {}),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> CanonicalCourtFrameDefinition:
        return cls(
            frame_id=str(payload["frame_id"]),
            capture_take_id=str(payload["capture_take_id"]),
            end_a_definition=str(payload["end_a_definition"]),
            end_b_definition=str(payload["end_b_definition"]),
            created_at=str(payload.get("created_at", "")),
            schema_version=str(payload.get("schema_version", "canonical_court_frame.v1")),
            orientation_by_view={
                str(key): str(value)
                for key, value in (payload.get("orientation_by_view") or {}).items()
            }
            if isinstance(payload.get("orientation_by_view"), dict)
            else {},
        )


def canonical_court_frame_path(take_dir: str | os.PathLike[str]) -> Path:
    """Canonical Court Frame Definition 的存储路径（take 的 metadata 目录下）。"""
    return Path(take_dir) / "metadata" / "canonical_court_frame.json"


def write_canonical_court_frame(
    take_dir: str | os.PathLike[str],
    definition: CanonicalCourtFrameDefinition,
) -> Path:
    """持久化 canonical 帧定义到 take 目录。

    若该 take 已存在定义，返回既有文件，不覆盖（保证同一 take 单一 frame_id）。
    """
    path = canonical_court_frame_path(take_dir)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(definition.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_canonical_court_frame(
    take_dir: str | os.PathLike[str],
) -> CanonicalCourtFrameDefinition | None:
    """读取 take 目录下已持久化的 canonical 帧定义；不存在返回 None。"""
    path = canonical_court_frame_path(take_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    return CanonicalCourtFrameDefinition.from_dict(payload)


def resolve_or_create_canonical_court_frame(
    take_dir: str | os.PathLike[str],
    capture_take_id: str,
    end_a_definition: str,
    end_b_definition: str,
    orientation_by_view: dict[str, str] | None = None,
) -> CanonicalCourtFrameDefinition:
    """读取既有定义；不存在则创建，并补全历史定义缺失的机位朝向。

    ``orientation_by_view`` 是对同一物理坐标系的逐机位投影声明。早期的
    场景标定可能只包含 A 机位；后来加入 B 机位不应生成新 frame 或被当成
    坐标系翻转。已存在的机位声明仍保持不可变，调用方须先完成兼容性校验。
    """
    existing = load_canonical_court_frame(take_dir)
    if existing is not None:
        additions = {
            view_id: orientation
            for view_id, orientation in (orientation_by_view or {}).items()
            if view_id not in existing.orientation_by_view
        }
        if not additions:
            return existing
        completed = CanonicalCourtFrameDefinition(
            frame_id=existing.frame_id,
            capture_take_id=existing.capture_take_id,
            end_a_definition=existing.end_a_definition,
            end_b_definition=existing.end_b_definition,
            created_at=existing.created_at,
            schema_version=existing.schema_version,
            orientation_by_view={**existing.orientation_by_view, **additions},
        )
        path = canonical_court_frame_path(take_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(completed.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return completed
    definition = CanonicalCourtFrameDefinition.create(
        capture_take_id=capture_take_id,
        end_a_definition=end_a_definition,
        end_b_definition=end_b_definition,
        orientation_by_view=orientation_by_view,
    )
    write_canonical_court_frame(take_dir, definition)
    return definition


def validate_canonical_court_frame_compatibility(
    existing: CanonicalCourtFrameDefinition | None,
    *,
    capture_take_id: str,
    end_a_definition: str,
    end_b_definition: str,
    orientation_by_view: dict[str, str] | None = None,
) -> str | None:
    """Validate a new request without changing the historical read-only resolver."""
    if existing is None:
        return None
    if existing.capture_take_id != capture_take_id:
        return "capture_take_id differs from the existing canonical frame"
    if existing.end_a_definition != end_a_definition or existing.end_b_definition != end_b_definition:
        return (
            "endpoint definition differs from the existing canonical frame "
            f"{existing.frame_id}"
        )
    if existing.orientation_by_view and orientation_by_view:
        # 允许历史 ccf_* 补上当时未参与标定的机位；只要已声明机位没有被
        # 改写，就仍是同一个 canonical court frame。
        mismatched_views = [
            view_id
            for view_id, orientation in existing.orientation_by_view.items()
            if view_id in orientation_by_view and orientation_by_view[view_id] != orientation
        ]
        if mismatched_views:
            return (
                "view orientation differs from the existing canonical frame "
                f"{existing.frame_id}: {', '.join(sorted(mismatched_views))}"
            )
    return None
