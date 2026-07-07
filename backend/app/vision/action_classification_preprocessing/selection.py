"""
目标球员选择策略（target player selection）。

一帧里可能检测到好几个人（Detection）。但我们做动作分类，通常只关心某一个特定球员
（比如总是发球那个人）。这个模块就是：给定一帧里的所有人，按某种策略挑出"目标球员"。

策略在 schemas.py 的 SelectionStrategy 里定义：largest / near-left / near-right / track-iou / manual-initial-bbox。

Detection 是一个数据类（来自 app.schemas.tracking），至少带有：
- .bbox：检测框 [x1, y1, x2, y2]（像素坐标）；
- .confidence：检测置信度。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# 检测框数据结构（来自 tracking schemas）。
from app.schemas.tracking import Detection


def select_target_detection(
    detections: list[Detection],
    *,
    strategy: str,
    frame_shape: tuple[int, ...],
    previous_bbox: list[float] | None = None,
    manual_initial_bbox: list[float] | None = None,
) -> Detection | None:
    """
    从一帧的多个检测里，挑出目标球员。

    参数：
    - detections：本帧所有人体检测结果；
    - strategy：选择策略字符串（见上）；
    - frame_shape：整图尺寸 (高, 宽)，用于 near-left/near-right 判断"左/右"；
    - previous_bbox：上一帧选中的框（track 类策略需要，做跟踪）；
    - manual_initial_bbox：用户给的初始框（manual 策略用）。

    返回：被选中的那个 Detection；若本帧没有任何人，返回 None。

    实现思路：对每种策略，用 Python 内置 `max(..., key=评分函数)` 找到"得分最高"的检测。
    """
    if not detections:
        return None
    if strategy == "largest":
        # 选框面积最大的那个人（通常离镜头最近、最显眼）
        return max(detections, key=lambda detection: _area(detection.bbox))
    if strategy == "near-left":
        # 选"偏左且面积较大"的人
        return max(detections, key=lambda detection: _near_score(detection.bbox, frame_shape, prefer_left=True))
    if strategy == "near-right":
        # 选"偏右且面积较大"的人
        return max(detections, key=lambda detection: _near_score(detection.bbox, frame_shape, prefer_left=False))
    if strategy == "track-iou":
        # 跟踪策略：若已有上一帧的框，就选和上一帧框 IoU 最大的（最像同一个人）；
        # 否则（第一帧）退化成选面积最大的。
        if previous_bbox is None:
            return max(detections, key=lambda detection: _area(detection.bbox))
        return max(detections, key=lambda detection: _iou(detection.bbox, previous_bbox))
    if strategy == "manual-initial-bbox":
        # 手动初始框策略：优先用上一帧框，没有就用用户给的初始框；
        # 同样用 IoU 找"最像"的那个人；若都没有参考框，退化成面积最大。
        reference = previous_bbox or manual_initial_bbox
        if reference is None:
            return max(detections, key=lambda detection: _area(detection.bbox))
        return max(detections, key=lambda detection: _iou(detection.bbox, reference))
    raise ValueError(f"Unknown target selection strategy: {strategy}")


def _area(box: list[float]) -> float:
    """
    计算框的面积 = 宽 × 高（负数会归零，避免脏数据导致负面积）。
    框格式：[x1, y1, x2, y2]。
    """
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _near_score(box: list[float], frame_shape: tuple[int, ...], *, prefer_left: bool) -> float:
    """
    给一个框打"靠近某侧 + 面积大"的综合分，用于 near-left / near-right 策略。

    分数构成（都是启发式权重，可按需调）：
    - area：面积越大越好；
    - horizontal：prefer_left=True 时取"到右边框的距离"（越靠左越大），反之取"中心 x"（越靠右越大）；
    - lower：框底部 y2 越大（越靠近画面下方/越靠前）略微加分。
    """
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0          # 框中心 x
    area = _area(box)
    horizontal = (width - cx) if prefer_left else cx   # 偏左/偏右的距离度量
    lower = y2                    # 框底部位置
    return area + horizontal * height * 0.25 + lower * height * 0.001


def _iou(a: list[float], b: list[float]) -> float:
    """
    计算两个框的 IoU（Intersection over Union，交并比），范围 0~1。

    IoU = 交集面积 / 并集面积。
    - 交集：两框重叠的那块矩形（取各自坐标的 max/min 围成）；
    - 并集 = A 面积 + B 面积 - 交集；
    - IoU 越接近 1，说明两框越重合，越可能是同一个人。
    """
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)   # 交集宽（为负则无交集，归零）
    inter_h = max(0.0, inter_y2 - inter_y1)   # 交集高
    intersection = inter_w * inter_h
    union = _area(a) + _area(b) - intersection
    if union <= 0:
        return 0.0
    return intersection / union
