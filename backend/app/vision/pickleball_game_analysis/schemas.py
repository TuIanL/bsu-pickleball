"""球轨迹、清洗轨迹和弹跳事件的数据结构（schemas）。

本文件定义了球分析流水线在各个环节之间传递的"数据形状"（dataclass），
以及几个把数据转成 JSON 安全格式、或在图像坐标/球场坐标之间做清洗的辅助函数。

坐标约定（见 coordinate_system_metadata）：
  - image（图像）：以像素为单位，原点在画面左上角；
  - court（球场）：以英尺（feet）为单位，原点在球场一角。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from math import isfinite
from typing import Any

# Point2D：二维点，统一用 (x, y) 元组表示（图像坐标或球场坐标都套这个类型）
Point2D = tuple[float, float]


class BallTrackState(Enum):
    """球轨迹锁定状态机四状态。"""

    SEARCHING = "searching"
    TENTATIVE = "tentative"
    LOCKED = "locked"
    LOST = "lost"


@dataclass(frozen=True)
class BallCandidate:
    """
    单个"球候选框"（某一帧里模型认为可能是球的一个检测框）。

    来自底层的球检测器（实现 BallDetectorProtocol 的对象）。
    每个候选带一个置信度 confidence，以及可选的框尺寸信息（用于后续过滤）。
    """

    image_x: float  # 候选框中心 x（像素）
    image_y: float  # 候选框中心 y（像素）
    confidence: float  # 置信度（0~1），越高越可能是真球
    width: float | None = None  # 框宽（像素），可空
    height: float | None = None  # 框高（像素），可空
    area_ratio: float | None = None  # 框面积占整帧面积的比例，可空（后续可计算）
    aspect_ratio: float | None = None  # 宽高比，可空（后续可计算）
    diagnostics: dict[str, Any] = field(default_factory=dict)  # 调试信息（如原始 bbox）

    @property
    def image_xy(self) -> Point2D:
        """方便属性：把 x / y 打包成 (x, y) 元组，供距离计算等使用。"""
        return (float(self.image_x), float(self.image_y))


@dataclass(frozen=True)
class BallCandidateDebug:
    """单个候选球的调试决策信息。"""

    candidate_id: str
    bbox: tuple[float, float, float, float] | None
    raw_confidence: float
    final_score: float
    distance_to_prediction: float | None
    jump_distance: float | None
    passed_physics_gate: bool
    rejection_reason: str | None
    score_components: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BallFrameDebug:
    """单帧球追踪的完整调试信息（存入 BallFrameSample.diagnostics）。"""

    track_state: str
    predicted_position: Point2D | None
    candidates: list = field(default_factory=list)
    accepted_candidate_id: str | None = None
    overall_decision: str = ""


@dataclass(frozen=True)
class BallFrameSample:
    """
    某一帧的"球采样结果"：经过 BallTracker 处理后，这一帧关于球的结论。

    关键字段：
      - accepted：该候选是否被接受为真实球位置；
      - visible：这一帧是否出现过候选（哪怕没被接受）；
      - reject_reason：若被拒，记录拒绝原因（如 box_too_large / jump_distance）；
      - court_xy：若提供了单应矩阵（homography），还会把图像坐标投影到球场坐标。
    """

    frame_index: int  # 帧序号
    timestamp_sec: float  # 该帧时间（秒）
    image_xy: Point2D | None  # 图像坐标（被拒/缺失时为 None）
    court_xy: Point2D | None  # 球场坐标（英尺），未投影时为 None
    confidence: float | None  # 置信度
    visible: bool  # 该帧是否出现过候选框
    accepted: bool  # 该候选是否被接受为真实球
    interpolated: bool = False  # 是否由插值得到（本类默认 False）
    candidate_count: int = 0  # 该帧过滤后剩下的候选数量
    reject_reason: str | None = None  # 拒绝原因（accepted=False 时有意义）
    source: str = "detector"  # 数据来源标签
    in_bounds: bool | None = None  # 投影后的球场坐标是否在界内（可空）
    track_state: str | None = None  # 当前帧轨迹锁定状态
    predicted_position: Point2D | None = None  # 预测位置（LOCKED/LOST 缺失时输出）
    overall_decision: str | None = None  # 最终决策标签
    diagnostics: dict[str, Any] = field(default_factory=dict)  # 调试信息


@dataclass(frozen=True)
class TrajectoryPoint:
    """
    轨迹上的一个点（清洗后的球轨迹基本单元）。

    与 BallFrameSample 类似，但表示"已清洗轨迹"里的一个点：
      - 可能来自被接受的检测（source="cleaned"）；
      - 也可能在清洗阶段被标记为异常点（image_xy=None）或由插值补全（interpolated=True）。
    """

    frame_index: int  # 帧序号
    timestamp_sec: float  # 该帧时间（秒）
    image_xy: Point2D | None  # 图像坐标（异常点/缺失时为 None）
    court_xy: Point2D | None  # 球场坐标（英尺）
    confidence: float | None = None  # 置信度
    interpolated: bool = False  # 是否由插值得到
    source: str = "cleaned"  # 数据来源标签
    in_bounds: bool | None = None  # 是否在界内
    diagnostics: dict[str, Any] = field(default_factory=dict)  # 调试信息

    @classmethod
    def from_sample(cls, sample: BallFrameSample) -> TrajectoryPoint:
        """
        从一帧采样结果 BallFrameSample 转换成轨迹点。

        注意：只有当 sample.accepted 为 True 时，才保留其 image_xy / court_xy / confidence；
        否则这些字段设为 None（表示该点不可信，后续清洗/插值会处理）。
        """
        return cls(
            frame_index=sample.frame_index,
            timestamp_sec=sample.timestamp_sec,
            image_xy=sample.image_xy if sample.accepted else None,
            court_xy=sample.court_xy if sample.accepted else None,
            confidence=sample.confidence if sample.accepted else None,
            interpolated=sample.interpolated,
            source=sample.source,
            in_bounds=sample.in_bounds,
            diagnostics=dict(sample.diagnostics),
        )


@dataclass(frozen=True)
class BounceEvent:
    """
    一个"弹跳事件"候选（球落地反弹那一刻）。

    由 BounceDetector 基于清洗后的轨迹生成。
    记录发生帧/时间、图像与球场坐标、置信度、检测方法，以及归属的回合 id（rally_id）。
    """

    event_id: str  # 事件唯一 ID（如 bounce-001）
    frame_index: int  # 发生帧序号
    timestamp_sec: float  # 发生时间（秒）
    image_xy: Point2D  # 图像坐标（弹跳点）
    court_xy: Point2D | None  # 球场坐标（英尺），可空
    confidence: float  # 置信度
    detection_method: str  # 检测方法标签（如 trajectory_lag20）
    diagnostics: dict[str, Any] = field(default_factory=dict)  # 调试信息
    rally_id: str | None = None  # 所属回合 ID（可空，用于后续回合分割）


def coordinate_system_metadata(court_width: float = 20.0, court_length: float = 44.0) -> dict[str, Any]:
    """
    返回坐标系统说明：图像用像素、球场用英尺，并带上球场宽长（默认标准匹克球场 20×44 英尺）。

    这个值会写进各 JSON 产物，方便前端/下游理解坐标单位。
    """
    return {
        "image": "pixels",
        "court": "feet",
        "court_width": float(court_width),
        "court_length": float(court_length),
    }


def clean_point(point: Any) -> Point2D | None:
    """
    把任意"像 (x, y) 的东西"清洗成可靠的 (float, float) 点。

    处理：
      - None → 直接返回 None；
      - 无法解包成两个数 / 转换失败 → 返回 None；
      - 含非有限值（inf / nan）→ 返回 None。
    用于防御脏数据（模型有时返回 nan 坐标）。
    """
    if point is None:
        return None
    try:
        x, y = point
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None
    if not isfinite(x) or not isfinite(y):
        return None
    return (x, y)


def to_jsonable(value: Any) -> Any:
    """把各种 Python / numpy 对象递归转成 JSON 安全的值（dataclass / Enum / numpy 标量 / 元组等）。"""

    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_jsonable(item) for item in value]
    # numpy 标量（如 np.float32）通常有 .item() 方法，可转成原生 Python 数值
    if hasattr(value, "item"):
        try:
            return to_jsonable(value.item())
        except (TypeError, ValueError):
            pass
    # numpy 数组等有 .tolist()
    if hasattr(value, "tolist"):
        try:
            return to_jsonable(value.tolist())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return value if isfinite(value) else None
    return value


def sample_to_payload(sample: BallFrameSample | TrajectoryPoint) -> dict[str, Any]:
    """把一个采样/轨迹点转成 JSON 安全的字典（供写入轨迹产物）。"""
    return to_jsonable(sample)


def event_to_payload(event: BounceEvent) -> dict[str, Any]:
    """把一个弹跳事件转成 JSON 安全的字典（供写入弹跳产物）。"""
    return to_jsonable(event)
