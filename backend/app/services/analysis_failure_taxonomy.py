"""失败归因分类 —— 回答「为什么失败」，与「哪一步失败」的 `errorCode` 正交。

`ANALYSIS_ERROR_CODES` 表达失败发生在哪个步骤（例如 `ANALYSIS_STAGE_TIMEOUT`）；
本模块表达失败的原因类别，使用户第一眼能判断该往哪个方向查。

纯逻辑模块：不 import `cv2` / `ultralytics`，可独立单测。
未知输入一律归 `internal_defect`，且调用方必须保留原始 `exception_type` 与
`exception_message`，使事后可以重新归因。
"""

from __future__ import annotations

from typing import Final

from app.schemas.analysis import ANALYSIS_FAILURE_CLASSES

# 枚举的权威定义在 schemas（数据契约），这里只做本地别名，避免两份枚举漂移。
FAILURE_CLASSES: Final[tuple[str, ...]] = tuple(ANALYSIS_FAILURE_CLASSES)

DEFAULT_FAILURE_CLASS: Final[str] = "internal_defect"

FAILURE_CLASS_LABELS: Final[dict[str, str]] = {
    "input_media": "输入或媒体问题",
    "calibration": "标定或场地几何问题",
    "model_environment": "模型或运行环境问题",
    "resource_timeout": "资源不足或超时",
    "worker_lease": "Worker 租约或心跳问题",
    "orchestration": "任务编排问题",
    "internal_defect": "代码缺陷或未归类",
}

# 判据按「越具体越靠前」排列：先排除租约/超时/媒体这类有确定特征的，再落到关键词。
_LEASE_TYPES = ("workerleaselost", "lease")
_LEASE_CODE_HINTS = ("worker_heartbeat", "worker_lost", "lease")
_TIMEOUT_TYPES = ("stagetimouterror", "timeout", "timedout")
_TIMEOUT_CODE_HINTS = ("timeout", "timed_out")
_RESOURCE_TYPES = ("memoryerror", "resourceexhausted")
_RESOURCE_MESSAGE_HINTS = (
    "out of memory",
    "cannot allocate",
    "no space left",
    "disk full",
    "errno 28",
    "磁盘空间",
)

_MEDIA_TYPES = ("filenotfounderror", "videoioerror", "unicodedecodeerror")
_MEDIA_CODE_HINTS = ("video_not_found", "source_pts_invalid", "media", "video")
_MEDIA_MESSAGE_HINTS = (
    "ffmpeg",
    "ffprobe",
    "videocapture",
    "no frames",
    "cannot open",
    "could not open",
    "moov atom",
    "codec",
    "decode",
    "corrupt",
    "truncated",
    "invalid data found",
    "无法读取",
    "视频",
)

_CALIBRATION_MESSAGE_HINTS = (
    "calibration",
    "homography",
    "court projector",
    "court_projection",
    "court project",
    "metric court",
    "metric_court",
    "court frame",
    "reprojection",
    "net profile",
    "标定",
)

_MODEL_MESSAGE_HINTS = (
    "ultralytics",
    "rtmpose",
    "mmpose",
    "mmcv",
    "torch",
    "checkpoint",
    "onnx",
    "safetensors",
    "cuda",
    "device",
    "no module named",
    "模型",
)
_MODEL_TYPES = ("importerror", "modulenotfounderror", "attributeerror")

_ORCHESTRATION_MESSAGE_HINTS = (
    "orchestrat",
    "parentjob",
    "parent job",
    "child job",
    "waiting_sources",
    "fusion_ready",
    "fallback_ready",
    "joint_ready",
    "window plan",
    "windowplan",
    "segmentation window",
    "prerequisite",
)


def _contains(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


def classify_failure(
    *,
    exception_type: str | None = None,
    message: str | None = None,
    error_code: str | None = None,
) -> str:
    """把一次失败归入 `FAILURE_CLASSES` 之一。

    输入全部可选；全部为空时返回 `internal_defect`。
    """
    type_text = (exception_type or "").strip().lower()
    code_text = (error_code or "").strip().lower()
    message_text = (message or "").strip().lower()

    # 1. Worker 租约 / 心跳：由编排层自己抛出，特征最确定。
    if _contains(type_text, _LEASE_TYPES) or _contains(code_text, _LEASE_CODE_HINTS):
        return "worker_lease"

    # 2. 超时：阶段超时是确定性错误，优先于媒体/模型类关键词。
    if _contains(type_text, _TIMEOUT_TYPES) or _contains(code_text, _TIMEOUT_CODE_HINTS):
        return "resource_timeout"

    # 3. 资源耗尽：内存/磁盘，仍属资源而非输入。
    if _contains(type_text, _RESOURCE_TYPES) or _contains(message_text, _RESOURCE_MESSAGE_HINTS):
        return "resource_timeout"

    # 4. 输入 / 媒体。
    if (
        _contains(type_text, _MEDIA_TYPES)
        or _contains(code_text, _MEDIA_CODE_HINTS)
        or _contains(message_text, _MEDIA_MESSAGE_HINTS)
    ):
        return "input_media"

    # 5. 标定 / 场地几何。
    if _contains(message_text, _CALIBRATION_MESSAGE_HINTS):
        return "calibration"

    # 6. 模型 / 运行环境。
    if _contains(message_text, _MODEL_MESSAGE_HINTS) or _contains(type_text, _MODEL_TYPES):
        return "model_environment"

    # 7. 编排。
    if _contains(message_text, _ORCHESTRATION_MESSAGE_HINTS):
        return "orchestration"

    return DEFAULT_FAILURE_CLASS
