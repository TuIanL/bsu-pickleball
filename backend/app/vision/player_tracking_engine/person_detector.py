"""人体检测器 —— 基于 YOLO 的人员检测，支持懒加载 ultralytics 依赖。"""

from __future__ import annotations

from typing import Any  # 宽松类型（模型对象等）

# Detection：单条检测结果的数据模型。
from app.schemas.tracking import Detection


class PersonDetector:
    """YOLO-backed person detector with lazy optional dependency loading."""

    # COCO 数据集中“人(person)”的类 ID 为 0，只保留该类的检测框。
    PERSON_CLASS_ID = 0

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.25,
        device: str | None = None,
    ) -> None:
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        # 设备缺省时自动选择（cuda 优先，否则 cpu）。
        self.device = device or self._auto_device()
        self._model: Any | None = None  # 模型懒加载缓存

    def detect(self, frame: object) -> list[Detection]:
        # 核心检测入口：返回当前帧中过滤后的人员检测框列表。
        model = self._load_model()
        # 部分 ultralytics 版本不支持 device 参数，做兼容尝试。
        try:
            results = model(frame, verbose=False, conf=self.conf_threshold, device=self.device)
        except TypeError:
            results = model(frame, verbose=False, conf=self.conf_threshold)

        detections: list[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                # 只保留类别为 person 的框。
                class_id = int(self._first_value(getattr(box, "cls", 0)))
                if class_id != self.PERSON_CLASS_ID:
                    continue
                confidence = float(self._first_value(getattr(box, "conf", 0.0)))
                if confidence < self.conf_threshold:
                    continue
                x1, y1, x2, y2 = [float(value) for value in self._xyxy(box)]
                detections.append(
                    Detection(
                        bbox=[x1, y1, x2, y2],
                        confidence=confidence,
                        class_name="person",
                    )
                )
        return detections

    # detect_frame 与 detect 等价，保留以便与需要“带帧序号”签名的调用方兼容。
    def detect_frame(self, frame: object, frame_index: int | None = None) -> list[Detection]:
        return self.detect(frame)

    def _load_model(self) -> Any:
        # 懒加载 YOLO 模型：首次调用时导入 ultralytics 并加载权重，之后复用。
        if self._model is None:
            try:
                from ultralytics import YOLO  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "ultralytics is not installed; install backend vision extras to run YOLO person detection"
                ) from exc
            self._model = YOLO(self.model_path)
        return self._model

    @staticmethod
    def _auto_device() -> str:
        # 自动选择推理设备：有可用 cuda 用 cuda，否则 cpu；torch 缺失也回退 cpu。
        try:
            import torch  # type: ignore
        except ImportError:
            return "cpu"
        try:
            return "cuda" if bool(torch.cuda.is_available()) else "cpu"
        except Exception:
            return "cpu"

    @staticmethod
    def _first_value(value: Any) -> float:
        # 兼容“单元素张量/数组”与“标量”两种形态，取第一个值并转 float。
        try:
            return float(value[0])
        except (TypeError, IndexError, KeyError):
            return float(value)

    @staticmethod
    def _xyxy(box: Any) -> list[float]:
        # 从 YOLO 的 box 对象中取出 [x1,y1,x2,y2] 坐标（优先用 .xyxy 属性）。
        xyxy = getattr(box, "xyxy", None)
        if xyxy is None:
            raise ValueError("YOLO box is missing xyxy coordinates")
        row = xyxy[0] if hasattr(xyxy, "__getitem__") else xyxy
        return [float(value) for value in row]


class EmptyPersonDetector:
    """Model-free detector used by tests and fallback smoke runs."""

    # 不加载任何模型，始终返回空检测结果（测试/兜底用）。
    def detect(self, frame: object) -> list[Detection]:
        return []

    def detect_frame(self, frame: object, frame_index: int | None = None) -> list[Detection]:
        return []


# 别名：UltralyticsPersonDetector 等价于 PersonDetector（兼容命名）。
UltralyticsPersonDetector = PersonDetector
