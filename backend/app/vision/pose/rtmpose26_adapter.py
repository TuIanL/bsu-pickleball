"""RTMPose26 姿态估计适配器 —— 按需加载 mmpose 依赖，对检测到的人体框进行 26 点关键点识别。"""

"""Optional RTMPose adapter with lazy heavyweight imports."""

from math import isfinite
from pathlib import Path
from typing import Any, Sequence

from app.schemas.pose import (
    RTMPOSE26_KEYPOINT_NAMES,
    PoseKeypoint,
    PoseOverlayFrame,
    PoseSubject,
)
from app.schemas.tracking import FrameDetection


SUPPORTED_KEYPOINT_SCHEMA = "rtmpose26"  # 本适配器只支持 rtmpose26 这一种关键点编号体系
EXPECTED_KEYPOINT_COUNT = len(RTMPOSE26_KEYPOINT_NAMES)  # 期望输出的关键点数量（26）


class RTMPose26Adapter:
    # 构造函数：保存配置，模型推迟到首次推理时再加载（懒加载，避免无谓的启动开销）。
    def __init__(
        self,
        config_path: str | None,
        checkpoint_path: str | None,
        device: str | None = None,
        conf_threshold: float = 0.3,
        keypoint_schema: str = "rtmpose26",
        conf_exit_threshold: float = 0.20,
    ) -> None:
        self.config_path = config_path  # MMPose 模型配置文件路径（.py）
        self.checkpoint_path = checkpoint_path  # MMPose 权重文件路径（.pth）
        self.device = device or "cpu"  # 推理设备，默认 CPU
        self.conf_threshold = conf_threshold  # 关键点可见性阈值（进入），置信度 >= 此值标记为可见
        self.conf_exit_threshold = conf_exit_threshold  # 关键点可见性阈值（退出），置信度 < 此值才退出可见
        self.keypoint_schema = keypoint_schema  # 关键点编号体系名称
        self._model: Any | None = None  # 模型缓存，首次推理后填充，后续复用
        # Hysteresis 状态：按 (track_id, keypoint_name) 索引，记录跨帧可见性
        self._visible_states: dict[str, dict[str, bool]] = {}

    # 对单帧进行姿态估计，返回带关键点的叠加帧结果（PoseOverlayFrame）。
    def estimate_frame(
        self,
        frame: object,
        subjects: Sequence[FrameDetection],
        frame_index: int,
        timestamp_seconds: float,
    ) -> PoseOverlayFrame:
        # 仅保留边界框可用的主体，避免对无效框做推理。
        usable_subjects = [subject for subject in subjects if self._has_usable_bbox(subject.bbox)]
        # 没有任何可用主体时，直接返回空结果（仍保留帧索引与时间戳）。
        if not usable_subjects:
            return PoseOverlayFrame(frame_index=frame_index, timestamp_seconds=timestamp_seconds)
        self._validate_schema()  # 校验关键点体系是否为本适配器支持的类型

        model = self._load_model()  # 懒加载（必要时初始化）模型
        inference_topdown = self._inference_topdown()  # 获取 mmpose 的 top-down 推理函数

        try:
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise RuntimeError("numpy is required to run RTMPose inference") from exc

        # 把所有可用主体的边界框堆叠成一个 numpy 数组，供模型批量推理。
        boxes = np.array([subject.bbox for subject in usable_subjects], dtype=float)
        # 兼容不同 mmpose 版本的接口：新版本接受 bbox_format 关键字，旧版本只接受位置参数。
        try:
            pose_results = inference_topdown(model, frame, bboxes=boxes, bbox_format="xyxy")
        except TypeError:
            pose_results = inference_topdown(model, frame, boxes)
        pose_results = self._as_result_list(pose_results)  # 统一转成列表，便于按索引取用

        rendered_subjects: list[PoseSubject] = []
        for index, subject in enumerate(usable_subjects):
            # 取出本主体对应的模型输出（防止索引越界）。
            sample = pose_results[index] if index < len(pose_results) else None
            keypoints, scores = self._extract_keypoints(sample)  # 解析关键点坐标与分数
            if not keypoints:
                continue  # 解析不到关键点则跳过该主体
            track_id = subject.track_id or f"subject-{index + 1}"
            rendered_subjects.append(
                PoseSubject(
                    track_id=track_id,  # 优先用跟踪 id，缺失时回退生成
                    bbox=subject.bbox,
                    confidence=subject.confidence,
                    keypoints=self._normalize_keypoints(keypoints, scores, track_id),  # 归一化并附名称/可见性（含 hysteresis）
                )
            )

        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=rendered_subjects,
        )

    # 加载（或复用已缓存的）RTMPose 模型，包含路径校验与 mmpose 可用性检查。
    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model  # 已加载则直接复用，避免重复初始化
        if not self.config_path or not self.checkpoint_path:
            raise RuntimeError("RTMPose config/checkpoint paths are not configured")
        if not Path(self.config_path).exists():
            raise RuntimeError(f"RTMPose config not found: {self.config_path}")
        if not Path(self.checkpoint_path).exists():
            raise RuntimeError(f"RTMPose checkpoint not found: {self.checkpoint_path}")

        try:
            from mmpose.apis import init_model  # type: ignore
        except ImportError as exc:
            raise RuntimeError("mmpose is not installed; install RTMPose runtime dependencies") from exc

        try:
            from mmpose.utils import register_all_modules  # type: ignore

            register_all_modules()
        except ImportError:
            pass  # 若该版本 mmpose 不需要手动注册模块，则忽略

        self._model = init_model(self.config_path, self.checkpoint_path, device=self.device)
        return self._model

    # 返回 mmpose 的 top-down 推理函数，仅在使用时导入（懒导入，减少无关依赖）。
    @staticmethod
    def _inference_topdown() -> Any:
        try:
            from mmpose.apis import inference_topdown  # type: ignore
        except ImportError as exc:
            raise RuntimeError("mmpose inference_topdown is unavailable") from exc
        return inference_topdown

    # 从模型输出样本中提取关键点坐标与对应分数，兼容「对象属性」与「字典」两种返回格式。
    @staticmethod
    def _extract_keypoints(sample: Any) -> tuple[list[list[float]], list[float]]:
        if sample is None:
            return ([], [])
        pred_instances = getattr(sample, "pred_instances", None)
        if pred_instances is None and isinstance(sample, dict):
            pred_instances = sample.get("pred_instances")
        if pred_instances is None:
            return ([], [])

        keypoints = getattr(pred_instances, "keypoints", None)
        scores = getattr(pred_instances, "keypoint_scores", None)
        if isinstance(pred_instances, dict):
            keypoints = pred_instances.get("keypoints", keypoints)
            scores = pred_instances.get("keypoint_scores", scores)
        if keypoints is None:
            return ([], [])

        keypoint_rows = RTMPose26Adapter._first_prediction_rows(keypoints)
        score_rows = RTMPose26Adapter._first_score_rows(scores) if scores is not None else None
        # 把坐标转成普通 float 列表，丢掉 numpy 张量的包装。
        normalized_keypoints = [[float(point[0]), float(point[1])] for point in keypoint_rows]
        # 若没有分数，则用 1.0 占位（表示全部视为满分）。
        normalized_scores = (
            [float(score) for score in score_rows] if score_rows is not None else [1.0] * len(normalized_keypoints)
        )
        return (normalized_keypoints, normalized_scores)

    # 把原始坐标/分数转换成带名称、可见性标记的 PoseKeypoint 列表，并校验数量。
    def _normalize_keypoints(self, keypoints: list[list[float]], scores: list[float], track_id: str = "") -> list[PoseKeypoint]:
        self._validate_schema()
        if keypoints and len(keypoints) != EXPECTED_KEYPOINT_COUNT:
            raise RuntimeError(
                f"RTMPose output has {len(keypoints)} keypoints; expected {EXPECTED_KEYPOINT_COUNT} for rtmpose26"
            )
        names = RTMPOSE26_KEYPOINT_NAMES
        # 初始化该 track_id 的 hysteresis 状态（若首次出现）
        if track_id and track_id not in self._visible_states:
            self._visible_states[track_id] = {name: False for name in names}
        states = self._visible_states.get(track_id, {})
        normalized: list[PoseKeypoint] = []
        enter = self.conf_threshold          # 进入阈值（默认 0.30）
        exit_t = self.conf_exit_threshold     # 退出阈值（默认 0.20）
        for index, point in enumerate(keypoints):
            # 把置信度裁剪到 [0, 1]，防止模型给出越界值。
            confidence = min(max(scores[index] if index < len(scores) else 0.0, 0.0), 1.0)
            name = names[index] if index < len(names) else f"keypoint_{index}"
            # Hysteresis 可见性判定
            prev_visible = states.get(name, False)
            if confidence >= enter:
                visible = True
            elif confidence < exit_t:
                visible = False
            else:
                # 在 [exit_t, enter) 区间，保持上一帧的状态（防抖）
                visible = prev_visible
            # 更新状态
            if track_id:
                self._visible_states[track_id][name] = visible
            normalized.append(
                PoseKeypoint(
                    name=name,
                    x=point[0],
                    y=point[1],
                    confidence=confidence,
                    visible=visible,
                )
            )
        return normalized

    # 校验当前指定的关键点体系是否被本适配器支持。
    def _validate_schema(self) -> None:
        if self.keypoint_schema != SUPPORTED_KEYPOINT_SCHEMA:
            raise RuntimeError(f"Unsupported RTMPose keypoint schema: {self.keypoint_schema}")

    # 判断一个边界框是否有效：长度必须为 4，且坐标有限、宽高为正。
    @staticmethod
    def _has_usable_bbox(bbox: Sequence[float]) -> bool:
        if len(bbox) != 4:
            return False
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return all(isfinite(value) for value in (x1, y1, x2, y2)) and x2 > x1 and y2 > y1

    # 把模型输出统一转换为列表（兼容 None / list / tuple / 单对象 等多种形态）。
    @staticmethod
    def _as_result_list(pose_results: Any) -> list[Any]:
        if pose_results is None:
            return []
        if isinstance(pose_results, list):
            return pose_results
        if isinstance(pose_results, tuple):
            return list(pose_results)
        return [pose_results]

    # 从关键点数组中取出「第一个样本」的关键点行，并兼容 numpy 张量（先 tolist）。
    @staticmethod
    def _first_prediction_rows(value: Any) -> list[Any]:
        if hasattr(value, "tolist"):
            value = value.tolist()
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            return []
        if len(value) == 0:
            return []
        first = value[0]
        if isinstance(first, (list, tuple)) and first and isinstance(first[0], (list, tuple)):
            return list(first)
        return list(value)

    # 从分数数组中取出「第一个样本」的分数行，逻辑与上面类似但处理单元素包装。
    @staticmethod
    def _first_score_rows(value: Any) -> list[Any]:
        if hasattr(value, "tolist"):
            value = value.tolist()
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            return []
        if len(value) == 0:
            return []
        first = value[0]
        if isinstance(first, (list, tuple)) and len(value) == 1:
            return list(first)
        return list(value)
