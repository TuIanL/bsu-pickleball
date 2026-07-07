"""
动作分类预处理 —— 配置项（config）与产物清单（manifest）的数据结构定义。

本文件里用到的核心 Python 知识是 `dataclass`（数据类）：
- 普通 class 写起来要手写 __init__ 来赋值每个字段，很啰嗦；
- `@dataclass` 装饰器会自动帮你生成 __init__、__repr__ 等样板代码，
  你只需要在类里写"字段名: 类型 = 默认值"即可。
- `frozen=True` 表示这个数据类创建后就不能再修改字段（类似"只读"），
  可以避免在复杂流程里不小心改错配置。
- `field(default_factory=XXX)` 表示"这个字段的默认值，调用 XXX() 来生成"，
  常用于默认值需要是一个新对象（如新的 list、新的子配置）的场景，
  避免多个实例共享同一个可变对象。

另外用到了 `Literal["a", "b"]`：它表示"这个字段的值只能是列出的某几个字符串之一"，
在类型检查阶段就能发现拼写错误。
"""

# `from __future__ import annotations` 让"较新的类型写法"（如 `list[int]`、`X | Y`）
# 在老版本 Python 上也能正常当作注解使用，属于兼容性写法，照抄即可。
from __future__ import annotations

# asdict：把一个 dataclass 实例转成普通的 dict（方便写 JSON）。
# dataclass / field：上面讲过的装饰器和字段配置工具。
from dataclasses import asdict, dataclass, field
# Path：Python 标准库里表示"文件路径"的对象，比裸字符串更安全、好用。
from pathlib import Path
# Any：表示"任意类型"；Literal：上面讲过的"只能是固定几个值之一"。
from typing import Any, Literal


# 目标球员的选择策略：只能取下面这几个字符串之一。
# - largest：每帧都选"框最大（面积最大）"的那个人；
# - near-left：优先选"靠左且面积较大"的人；
# - near-right：优先选"靠右且面积较大"的人；
# - track-iou：用上一帧选中的框，和本帧各框算 IoU（交并比），选最像的那个（做跟踪）；
# - manual-initial-bbox：用户给一个初始框，之后用 IoU 跟踪。
SelectionStrategy = Literal["largest", "near-left", "near-right", "track-iou", "manual-initial-bbox"]

# 缺帧处理策略：目前只支持 "skip"（这一帧跳过、不写样本）。
MissingFramePolicy = Literal["skip"]


class ActionPreprocessingError(ValueError):
    """
    动作预处理过程中的自定义异常。

    继承自 Python 内置的 ValueError，意思是"传入的配置/数据不合法"。
    单独建一个类，是为了让调用方能精确地 `except ActionPreprocessingError` 捕获，
    而不至于把所有 ValueError 都误捕获。
    """


@dataclass(frozen=True)
class ROIConfig:
    """
    场地 ROI（Region Of Interest，感兴趣区域）配置。

    我们常常不需要整张画面，只关心球场那一块。ROI 用"比例"来定义，
    即相对于整张图宽/高的百分比（0~1 之间），这样不同分辨率的视频都能用同一套配置。
    """

    x1_ratio: float = 0.02  # 左上角 x 坐标占整图宽度的比例
    y1_ratio: float = 0.30  # 左上角 y 坐标占整图高度的比例
    x2_ratio: float = 0.98  # 右下角 x 坐标占整图宽度的比例
    y2_ratio: float = 0.98  # 右下角 y 坐标占整图高度的比例

    def __post_init__(self) -> None:
        """
        dataclass 自动生成的 __init__ 跑完之后，会紧接着调用 __post_init__。
        这里专门用来做"参数合法性校验"：保证比例是 0~1，且左上角在右下角左上方。
        """
        values = (self.x1_ratio, self.y1_ratio, self.x2_ratio, self.y2_ratio)
        if not all(0.0 <= value <= 1.0 for value in values):
            raise ActionPreprocessingError("ROI ratios must be between 0 and 1")
        if not self.x1_ratio < self.x2_ratio:
            raise ActionPreprocessingError("ROI x1_ratio must be less than x2_ratio")
        if not self.y1_ratio < self.y2_ratio:
            raise ActionPreprocessingError("ROI y1_ratio must be less than y2_ratio")


@dataclass(frozen=True)
class CLAHEConfig:
    """
    CLAHE 图像增强配置。

    CLAHE（限制对比度自适应直方图均衡化）是一种让画面明暗更清晰的算法，
    在光照不好的比赛视频里很有用。它在 LAB 颜色空间的 L（亮度）通道上做。
    """

    enabled: bool = True          # 是否开启 CLAHE
    clip_limit: float = 2.0       # 对比度裁剪上限，越大对比越强
    tile_grid_size: int = 8       # 把图切成多少格来做局部均衡（8 表示 8x8 格）

    def __post_init__(self) -> None:
        if self.clip_limit <= 0:
            raise ActionPreprocessingError("CLAHE clip_limit must be greater than 0")
        if self.tile_grid_size <= 0:
            raise ActionPreprocessingError("CLAHE tile_grid_size must be greater than 0")


@dataclass(frozen=True)
class DenoiseConfig:
    """
    轻量去噪配置。

    用高斯模糊做简单去噪。默认关闭（enabled=False），因为去噪会稍微模糊细节。
    """

    enabled: bool = False   # 是否开启去噪
    kernel_size: int = 3    # 高斯核大小，必须是正奇数（如 3、5、7）
    sigma: float = 0.0      # 高斯核的标准差，0 表示由 kernel_size 自动推算

    def __post_init__(self) -> None:
        if self.kernel_size <= 0 or self.kernel_size % 2 == 0:
            raise ActionPreprocessingError("Denoise kernel_size must be a positive odd integer")
        if self.sigma < 0:
            raise ActionPreprocessingError("Denoise sigma must be greater than or equal to 0")


@dataclass(frozen=True)
class ActionPreprocessingConfig:
    """
    动作分类预处理的总配置。

    这是导出数据集时唯一的"入口参数对象"：几乎所有行为都由这里面的字段控制。
    下面每个字段都标注了含义与默认值。
    """

    input_path: Path | str                       # 输入：单个视频文件，或一个装着多个视频的文件夹
    output_root: Path | str                      # 输出根目录：导出的图片和 manifest 都写在这里面
    label: str                                   # 这个数据集的类别标签（如 "serve"、"forehand"），会作为子文件夹名
    target_fps: float = 20.0                     # 目标采样帧率：从原视频里按这个帧率抽帧
    roi: ROIConfig = field(default_factory=ROIConfig)             # 场地 ROI 配置（默认全屏略裁剪）
    clahe: CLAHEConfig = field(default_factory=CLAHEConfig)       # CLAHE 增强配置
    detect_on_enhanced: bool = False             # 是否在"增强后"的画面上做人检测（默认在原始 ROI 上检测）
    denoise: DenoiseConfig = field(default_factory=DenoiseConfig) # 去噪配置
    detector_model_path: str = "yolo11n.pt"      # 人检测模型权重路径（YOLO11 nano）
    detector_confidence: float = 0.5             # 检测置信度阈值，低于此分数的框不要
    detector_device: str | None = None           # 推理设备（如 "cpu" / "cuda:0"），None 表示用默认
    selection_strategy: SelectionStrategy = "largest"  # 目标球员选择策略（见 SelectionStrategy）
    manual_initial_bbox: list[float] | None = None     # 当策略为 manual-initial-bbox 时，必须给的初始框 [x1,y1,x2,y2]
    missing_frame_policy: MissingFramePolicy = "skip"  # 缺帧处理策略（目前仅 "skip"）
    bbox_expand_scale: float = 1.4               # 裁剪球员时，把检测框放大多少倍（留点余量）
    output_size: int = 224                       # 每张裁剪出的球员图，最终 resize 成多少像素（正方形）
    clip_length: int = 16                        # 一个 clip（动作片段）由多少连续帧组成
    clip_stride: int = 16                        # 相邻 clip 之间跳多少帧（=clip_length 表示不重叠）
    jpeg_quality: int = 95                       # 导出 JPEG 的质量（1~100，越大越清晰、文件越大）
    overwrite: bool = False                      # 输出已存在时，是否覆盖（False 则报错）
    start_seconds: float = 0.0                   # 只处理从这一秒开始的画面
    end_seconds: float | None = None             # 处理到这一秒结束（None 表示到视频末尾）
    manifest_name: str = "manifest.json"         # 清单文件名

    def __post_init__(self) -> None:
        """
        配置校验 + 字段规范化。dataclass 的 __init__ 结束后自动调用。

        注意：本类是 frozen（只读）的，不能直接 `self.input_path = ...` 赋值，
        所以这里用 `object.__setattr__` 来"绕过只读限制"做规范化
        （把路径字符串转成 Path 对象、去掉 label 两端空格等）。
        """
        object.__setattr__(self, "input_path", Path(self.input_path).expanduser())
        object.__setattr__(self, "output_root", Path(self.output_root).expanduser())
        object.__setattr__(self, "label", self.label.strip())
        if not self.label:
            raise ActionPreprocessingError("label must not be empty")
        if self.target_fps <= 0:
            raise ActionPreprocessingError("target_fps must be greater than 0")
        if not 0.0 <= self.detector_confidence <= 1.0:
            raise ActionPreprocessingError("detector_confidence must be between 0 and 1")
        if self.selection_strategy not in {"largest", "near-left", "near-right", "track-iou", "manual-initial-bbox"}:
            raise ActionPreprocessingError(f"Unknown selection_strategy: {self.selection_strategy}")
        if self.selection_strategy == "manual-initial-bbox" and self.manual_initial_bbox is None:
            raise ActionPreprocessingError("manual_initial_bbox is required for manual-initial-bbox strategy")
        if self.manual_initial_bbox is not None:
            _validate_bbox(self.manual_initial_bbox, "manual_initial_bbox")
        if self.missing_frame_policy != "skip":
            raise ActionPreprocessingError(f"Unknown missing_frame_policy: {self.missing_frame_policy}")
        if self.bbox_expand_scale <= 0:
            raise ActionPreprocessingError("bbox_expand_scale must be greater than 0")
        if self.output_size <= 0:
            raise ActionPreprocessingError("output_size must be greater than 0")
        if self.clip_length <= 0:
            raise ActionPreprocessingError("clip_length must be greater than 0")
        if self.clip_stride <= 0:
            raise ActionPreprocessingError("clip_stride must be greater than 0")
        if not 1 <= self.jpeg_quality <= 100:
            raise ActionPreprocessingError("jpeg_quality must be between 1 and 100")
        if self.start_seconds < 0:
            raise ActionPreprocessingError("start_seconds must be greater than or equal to 0")
        if self.end_seconds is not None and self.end_seconds < self.start_seconds:
            raise ActionPreprocessingError("end_seconds must be greater than or equal to start_seconds")
        if not self.manifest_name.endswith(".json"):
            raise ActionPreprocessingError("manifest_name must end with .json")

    def to_manifest_dict(self) -> dict[str, Any]:
        """
        把配置转成 dict，供写入 manifest.json 时作为 "settings" 字段。

        asdict 会把嵌套的子配置（ROI/CLAHE/Denoise）也一并转成 dict；
        但 Path 对象需要手动转成字符串，否则 JSON 无法序列化。
        """
        payload = asdict(self)
        payload["input_path"] = str(self.input_path)
        payload["output_root"] = str(self.output_root)
        return payload


@dataclass(frozen=True)
class ROIRecord:
    """单次裁剪场地 ROI 的记录：存下比例、像素框、原图尺寸，方便后续追溯。"""

    ratios: dict[str, float]   # 用到的四个比例（x1_ratio 等）
    bbox: list[int]            # 实际裁剪的像素框 [x1, y1, x2, y2]
    source_width: int          # 原图宽度（像素）
    source_height: int         # 原图高度（像素）

    @property
    def offset(self) -> list[int]:
        """
        @property 让这个方法可以像"只读属性"一样访问（不用加括号）：
        `record.offset` 即可。这里返回 ROI 左上角在原图中的偏移 [x1, y1]，
        因为之后要把"相对 ROI 的框"换算回"相对整张原图"的框。
        """
        return [self.bbox[0], self.bbox[1]]


@dataclass
class FrameSample:
    """单帧样本的记录：一张裁剪好的球员图 + 它的各种坐标/元信息。"""

    source_path: str          # 来源视频路径
    frame_index: int          # 在原视频中的帧序号
    timestamp_seconds: float  # 该帧对应的时间戳（秒）
    output_path: str          # 导出后的图片路径（写出前可能为空字符串占位）
    file_name: str            # 导出的文件名
    roi: dict[str, Any]       # 该帧的 ROI 记录（dict 形式）
    detection_count: int      # 这一帧共检测到几个人
    selection_strategy: str   # 用的是哪种目标选择策略
    confidence: float         # 选中目标的检测置信度
    bbox_roi: list[float]     # 选中目标在"ROI 画面"里的框 [x1,y1,x2,y2]
    bbox_source: list[float]  # 选中目标在"整张原图"里的框
    crop_bbox_roi: list[int]  # 实际裁剪框（已放大）在 ROI 画面里的坐标
    crop_bbox_source: list[int]  # 实际裁剪框在整张原图里的坐标


@dataclass
class ClipRecord:
    """一个 clip（动作片段）的记录：由若干连续帧组成，属于某个 label。"""

    label: str              # 类别标签
    video_stem: str         # 来源视频名（不含扩展名）
    clip_index: int         # 该视频内第几个 clip
    output_dir: str         # 这个 clip 的输出目录
    frames: list[FrameSample]  # 组成这个 clip 的帧样本列表


@dataclass
class VideoManifest:
    """单个视频的导出清单（manifest）：汇总统计信息 + 所有 clip。"""

    source_path: str        # 来源视频路径
    source_name: str        # 来源视频文件名
    output_stem: str        # 输出名（不含扩展名，可能带去重后缀）
    fps: float | None = None            # 视频帧率
    frame_count: int | None = None      # 视频总帧数
    duration_seconds: float | None = None  # 视频时长（秒）
    width: int | None = None            # 视频宽
    height: int | None = None           # 视频高
    processed_frame_count: int = 0      # 实际读取处理过的帧数
    selected_frame_count: int = 0       # 成功选中目标并保留的帧数
    skipped_frame_count: int = 0        # 因读不出/无目标而跳过的帧数
    clips_written: int = 0              # 成功写出的 clip 数
    frames_written: int = 0             # 成功写出的帧图片数
    clips: list[ClipRecord] = field(default_factory=list)   # 所有 clip 记录
    errors: list[dict[str, Any]] = field(default_factory=list)  # 处理过程中的错误记录


def dataclass_to_dict(value: Any) -> Any:
    """
    把任意 dataclass（可能还嵌套了 Path、list、dict）递归转成"可 JSON 序列化"的 dict。

    为什么不直接用 asdict？因为 asdict 对 Path 对象处理不好，而且这里统一把 Path 转字符串。
    逻辑：
    - Path → 字符串；
    - dataclass → 对每个字段递归调用本函数；
    - list / dict → 对每个元素递归调用本函数；
    - 其它（int/float/str/bool 等）→ 原样返回。
    """
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: dataclass_to_dict(item) for key, item in value.items()}
    return value


def _validate_bbox(values: list[float], label: str) -> None:
    """
    校验一个 bbox 是否合法：必须是 4 个数 [x1, y1, x2, y2]，且 x1<x2、y1<y2。

    `label` 用于报错时指出"是哪个框"不合法，方便定位。
    以 `_` 开头的函数名是约定（私有/内部使用），表示"外面一般不要直接调用"。
    """
    if len(values) != 4:
        raise ActionPreprocessingError(f"{label} must contain exactly four numbers")
    x1, y1, x2, y2 = [float(value) for value in values]
    if not x1 < x2 or not y1 < y2:
        raise ActionPreprocessingError(f"{label} must be [x1, y1, x2, y2] with positive width and height")
