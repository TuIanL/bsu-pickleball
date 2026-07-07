"""多目标检测器 —— 支持球员、场地元素等多类别目标的统一检测与归一化。

相比 `base.py` 里的单目标 `Detection`，这里面向"一帧里有多个不同类别"
（球员、球、网、球场线等）的场景，统一成 `MultiTargetDetection` 结构，
并提供把原始模型输出"归一化"成标准格式的辅助函数。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.schemas.multitarget import MultiTargetDetection, TargetClassName
from app.schemas.tracking import Detection as PlayerDetection


class MultiTargetDetector(Protocol):
    """多目标检测器协议 —— 规定 `detect_frame` 这一个方法签名。

    满足协议的实现必须接收"已解码的视频帧"（以及帧序号、时间戳、宽高），
    返回该帧的 `MultiTargetDetection` 列表。
    """

    def detect_frame(
        self,
        frame: object,
        frame_index: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[MultiTargetDetection]:
        """Return normalized detections for one decoded video frame.

        参数：
        - frame：已解码的一帧图像（具体类型由实现决定，这里用 object 笼统表示）。
        - frame_index：帧序号（从 0 开始）。
        - timestamp_seconds：该帧对应的视频时间（秒）。
        - frame_width / frame_height：帧的像素宽高。
        返回：
        - 该帧里所有检测到的多类别目标。
        """


class EmptyMultiTargetDetector:
    """"空"多目标检测器：什么都不检测，直接返回空列表。

    用途：当系统没有配置真正的检测器时，用这个占位实现，
    让上层流程可以无差异地调用 `detect_frame` 而不报错。
    """

    # 给调用方看的说明文字
    detail = "多目标检测未配置，跳过可选球员检测"

    def detect_frame(
        self,
        frame: object,
        frame_index: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[MultiTargetDetection]:
        # 不检测任何东西，返回空列表
        return []


class FixtureMultiTargetDetector:
    """"固定夹具"多目标检测器：用预先准备好的检测结果喂给上层。

    用途：测试或演示时，不需要真的跑模型，而是把事先写好的
    `detections_by_frame`（帧序号 -> 该帧的检测列表）直接返回。
    """

    def __init__(
        self,
        detections_by_frame: Mapping[int, Sequence[MultiTargetDetection | Mapping[str, Any]]],
    ) -> None:
        # 保存"帧序号 -> 检测结果"的映射，作为固定的检测数据源
        self.detections_by_frame = detections_by_frame

    def detect_frame(
        self,
        frame: object,
        frame_index: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[MultiTargetDetection]:
        # 取出该帧预先准备好的检测（没有就空列表）
        detections = self.detections_by_frame.get(frame_index, [])
        normalized: list[MultiTargetDetection] = []
        for detection in detections:
            if isinstance(detection, MultiTargetDetection):
                # 已经是标准结构，直接收下
                normalized.append(detection)
            else:
                # 否则当成原始 dict，补上帧/时间/尺寸等上下文后，用 Pydantic 校验成标准结构
                payload = {
                    "frame_index": frame_index,
                    "timestamp_seconds": timestamp_seconds,
                    "source_width": max(1, int(frame_width)),
                    "source_height": max(1, int(frame_height)),
                    **dict(detection),
                }
                normalized.append(MultiTargetDetection.model_validate(payload))
        return normalized


def normalize_raw_multitarget_detections(
    raw_detections: Sequence[Mapping[str, Any]],
    *,
    frame_index: int,
    timestamp_seconds: float,
    frame_width: int,
    frame_height: int,
    class_map: Mapping[str | int, TargetClassName],
    confidence_thresholds: Mapping[TargetClassName, float],
) -> list[MultiTargetDetection]:
    """把"原始模型输出"归一化成标准 MultiTargetDetection 列表。

    原始输出往往字段命名不统一、坐标格式各异，这里统一做：
    1. 类别映射：把模型给的 class_id / label 映射到我们约定的 TargetClassName。
    2. 置信度过滤：低于该类别阈值的检测结果丢弃。
    3. 补齐上下文：帧序号、时间戳、源尺寸等。
    4. 构造标准对象（用 Pydantic 模型校验字段合法性）。

    参数（带 * 的 kwargs 为仅关键字参数，必须按名字传）：
    - raw_detections：原始检测列表（每个是 dict）。
    - frame_index / timestamp_seconds / frame_width / frame_height：帧上下文。
    - class_map：原始类别 -> 标准 TargetClassName 的映射表。
    - confidence_thresholds：每个标准类别对应的最低置信度阈值。
    """
    normalized: list[MultiTargetDetection] = []
    for raw in raw_detections:
        # 先从多种可能的字段名里取"原始类别"
        raw_class = raw.get("class_name", raw.get("label", raw.get("class_id")))
        # 用映射表把原始类别翻译成标准类别名
        class_name = class_map.get(raw_class)
        if class_name is None and raw_class is not None:
            # 再试一次：把原始类别转成字符串再查（兼容 int/str 混用）
            class_name = class_map.get(str(raw_class))
        if class_name is None:
            # 映射不到任何标准类别，跳过这个检测
            continue

        # 取置信度，缺失时按 0 处理
        confidence = float(raw.get("confidence", 0.0))
        if confidence < confidence_thresholds.get(class_name, 0.0):
            # 低于该类别阈值，视为不可靠，丢弃
            continue

        try:
            # 组装成标准 MultiTargetDetection 对象（Pydantic 会校验字段）。
            # player 使用 bbox，ball 使用 point；部分模型只给 ball bbox 时用中心点降级。
            payload: dict[str, Any] = {
                "frame_index": int(raw.get("frame_index", frame_index)),
                "timestamp_seconds": float(raw.get("timestamp_seconds", timestamp_seconds)),
                "class_name": class_name,
                "confidence": confidence,
                "source_width": max(1, int(raw.get("source_width", frame_width))),
                "source_height": max(1, int(raw.get("source_height", frame_height))),
                "track_id": str(raw["track_id"]) if raw.get("track_id") is not None else None,
            }
            if class_name == "ball":
                point = raw.get("point", raw.get("image_xy", raw.get("center")))
                if point is None and raw.get("bbox") is not None:
                    x1, y1, x2, y2 = (float(value) for value in raw["bbox"])
                    point = [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
                payload["point"] = [float(value) for value in point]
            else:
                payload["bbox"] = [float(value) for value in raw["bbox"]]
            detection = MultiTargetDetection(**payload)
        except (KeyError, TypeError, ValueError):
            # 字段缺失或类型不对，跳过这个不合法的结果
            continue
        normalized.append(detection)
    return normalized


def player_detections_from_multitarget(detections: Sequence[MultiTargetDetection]) -> list[PlayerDetection]:
    """从多目标检测结果中，只挑出"类别为 player（球员）"的目标，
    转成 tracking 流水线用的 PlayerDetection（person 类别）列表。

    用途：多目标检测可能包含球、网等多种类别，但跟踪模块只关心人，
    所以用这个函数过滤 + 转换。
    """
    return [
        PlayerDetection(
            bbox=detection.bbox,
            confidence=detection.confidence,
            class_name="person",
        )
        for detection in detections
        if detection.class_name == "player"
    ]
