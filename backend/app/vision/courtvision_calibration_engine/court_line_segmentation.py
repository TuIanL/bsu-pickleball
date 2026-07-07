"""
球场线分割（court_line_segmentation）—— 用 Ultralytics YOLO 分割模型生成球场边线掩码。

自动标定的第一步：给一帧画面，用训练好的 YOLO 分割模型，输出"哪里是球场线"的掩码
（mask，一张和画面同尺寸的二值图：线所在处为 255，其余为 0）。

本文件只在"模型已配置好"时工作；没配模型或没装 ultralytics 库，会抛专门的不可用异常，
而不是崩溃。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# dataclass：数据类（详见 schemas.py 注释）。
from dataclasses import dataclass
# Path：路径对象。
from pathlib import Path
# Any：泛指模型对象等"任意类型"。
from typing import Any

# numpy：数值计算库。
import numpy as np


@dataclass(frozen=True)
class CourtLineSegmentationResult:
    """一次分割的结果：掩码 + 置信度 + 模型路径。"""
    mask: np.ndarray                  # 分割掩码（H×W 的 uint8，线处为 255）
    confidence: float                 # 平均置信度（0~1）
    model_path: str | None = None     # 用的哪个模型


class CourtLineSegmentationUnavailable(RuntimeError):
    """
    球场线分割"不可用"异常（继承自 RuntimeError，表示运行环境/资源缺失）。

    与 ValueError 不同：这里通常表示"模型没配 / 库没装"，属于运行前置条件不满足，
    而不是参数传错。
    """
    pass


class CourtLineSegmenter:
    """
    球场线分割器：对 YOLO 分割模型的"惰性适配"（lazy adapter）。

    "惰性"指：只有真正调用 segment() 时，才去加载模型（_load_model），
    避免一导入就占内存/加载权重。模型加载后会被缓存（self._model）。
    """

    def __init__(
        self,
        model_path: str | None,
        confidence: float = 0.35,
        device: str | None = None,
    ) -> None:
        self.model_path = model_path        # 模型权重路径（None 表示未配置）
        self.confidence = confidence        # 检测置信度阈值
        self.device = device                # 推理设备（"cpu"/"cuda:0"，None 用默认）
        self._model: Any | None = None      # 已加载的模型缓存（懒加载）

    @property
    def configured(self) -> bool:
        """是否已配置了模型路径（配置好了才可用）。"""
        return bool(self.model_path)

    def segment(self, frame: np.ndarray) -> CourtLineSegmentationResult:
        """
        对一帧画面做分割，返回球场线掩码。

        流程：检查模型路径 → 加载模型 → 预测 → 把预测结果整理成单张合并掩码 + 置信度。
        任何前置条件不满足都会抛 CourtLineSegmentationUnavailable。
        """
        if not self.model_path:
            raise CourtLineSegmentationUnavailable("Court-line model path is not configured")

        path = Path(self.model_path)
        if not path.exists():
            raise CourtLineSegmentationUnavailable(f"Court-line model not found: {self.model_path}")

        model = self._load_model()
        # 调用 YOLO 的 predict，得到检测结果（含 masks、boxes）
        results = model.predict(frame, conf=self.confidence, device=self.device, verbose=False)
        mask, confidence = _result_to_mask(results, frame.shape[:2])
        if mask is None:
            raise CourtLineSegmentationUnavailable("Court-line model produced no usable segmentation mask")
        return CourtLineSegmentationResult(mask=mask, confidence=confidence, model_path=str(path))

    def _load_model(self) -> Any:
        """
        加载（并缓存）YOLO 模型。

        若已加载过（self._model 非空）直接复用；否则按需导入 ultralytics 并加载权重。
        没装 ultralytics 则抛"不可用"异常，提示去装后端 vision 扩展。
        """
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise CourtLineSegmentationUnavailable(
                "ultralytics is not installed; install backend vision extras to run court-line segmentation"
            ) from exc

        self._model = YOLO(self.model_path)
        return self._model


def _result_to_mask(results: Any, shape: tuple[int, int]) -> tuple[np.ndarray | None, float]:
    """
    把 YOLO 的预测结果整理成"一张合并掩码 + 平均置信度"。

    - 遍历每张结果的 masks（分割掩码）和 boxes（检测框含置信度）；
    - 每张掩码 resize 到画面尺寸，二值化后用"逐像素取最大值"合并多张掩码；
    - 没有产生任何前景 → 返回 (None, 0.0)。
    """
    height, width = shape
    combined = np.zeros((height, width), dtype=np.uint8)   # 合并掩码，初始全黑
    confidences: list[float] = []

    for result in results or []:
        masks = getattr(result, "masks", None)
        boxes = getattr(result, "boxes", None)
        if masks is None or getattr(masks, "data", None) is None:
            continue

        mask_data = masks.data
        # masks.data 通常是 GPU 张量，要先转成 numpy（兼容没有 .cpu() 的情况）
        try:
            mask_arrays = mask_data.cpu().numpy()
        except AttributeError:
            mask_arrays = np.asarray(mask_data)

        # 收集每张掩码对应框的置信度
        box_conf = getattr(boxes, "conf", None)
        if box_conf is not None:
            try:
                confidences.extend(float(value) for value in box_conf.cpu().numpy())
            except AttributeError:
                confidences.extend(float(value) for value in np.asarray(box_conf))

        for mask in mask_arrays:
            resized = _resize_mask(np.asarray(mask, dtype=float), (height, width))
            # 二值化(>0.5)后乘 255，再和已有掩码取"或"（逐像素最大），合并重叠区域
            combined = np.maximum(combined, (resized > 0.5).astype(np.uint8) * 255)

    if not combined.any():
        return None, 0.0
    # 平均置信度；没有任何置信度信息时默认 1.0
    confidence = float(np.mean(confidences)) if confidences else 1.0
    return combined, confidence


def _resize_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """
    把单张掩码 resize 到目标尺寸 (height, width)。

    若尺寸已一致直接返回；否则优先用 OpenCV 线性插值，没有 OpenCV 就退回最近邻索引取样。
    """
    height, width = shape
    if mask.shape == (height, width):
        return mask
    try:
        import cv2  # type: ignore
    except ImportError:
        # 退化方案：用等间距索引采样（效果不如插值，但不需要 OpenCV）
        y_index = np.linspace(0, mask.shape[0] - 1, height).astype(int)
        x_index = np.linspace(0, mask.shape[1] - 1, width).astype(int)
        return mask[y_index][:, x_index]
    return cv2.resize(mask, (width, height), interpolation=cv2.INTER_LINEAR)
