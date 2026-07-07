"""球员跟踪相关的 Pydantic 数据模型 —— 检测框、轨迹、脚点投影、球员身份等。

这个模块定义了"球员跟踪（Tracking）"阶段用到的所有数据结构。
所谓"跟踪"，就是：先在视频的每一帧里找出"人在哪里"（检测），
再把不同帧里同一个人连成一条连续的"轨迹"（跟踪），
最后把人在画面上的位置换算成在球场上的真实坐标（投影）。

下面这些类会被后端的跟踪算法填充，并通过 API 返回给前端，
供前端在视频上叠加检测框、轨迹线、脚点等可视化效果。

如果你还不熟悉 Pydantic，可以把它理解成一个"带校验的字典"：
- 用 `class Xxx(BaseModel)` 定义一个数据结构；
- 每个字段写 `字段名: 类型 = Field(...)` 来表示它的类型和约束；
- Pydantic 会自动检查传入的数据是否符合约束，不符合就报错。
"""

from __future__ import annotations

from math import isfinite
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# 从 calibration 模块导入"图像坐标点"模型（x, y 的二维点）。
# 这里只导入类型定义，不会触发任何相机/标定的运行时逻辑。
from app.schemas.calibration import ImagePoint

# ---------------------------------------------------------------------------
# 下面是一组"字面量类型（Literal）"别名。
# Literal["a", "b"] 表示这个字段的取值只能是指定的某几个字符串之一，
# 写错一个字 Pydantic 都会直接报错，能帮我们尽早发现 bug。
# ---------------------------------------------------------------------------

# 脚点估计方法（即"如何判断一个人站在球场的哪个位置"）：
# - bbox_bottom_center：取检测框底部的中心点（最常用、最省算力）
# - pose_ankle_average：取姿态估计中两个脚踝的平均位置（更准但需要姿态模型）
# - segmentation_mask_bottom：取人体分割掩码的最底部（最准但最慢）
FootpointMethod = Literal["bbox_bottom_center", "pose_ankle_average", "segmentation_mask_bottom"]

# 某个坐标/位置是否有效（valid=有效，invalid=无效，例如被判定为异常抖动）
PositionValidity = Literal["valid", "invalid"]

# 球场坐标使用的长度单位：米（m）或英尺（ft）
CourtUnit = Literal["m", "ft"]

# 球员在某帧中的跟踪状态：
# - detected：本帧被成功检测到
# - interpolated：本帧没检测到，用前后帧"补"出来的位置
# - lost：跟丢了（连续多帧找不到）
# - inactive：该球员已不再参与（例如已下场）
# - unmatched：检测到了人，但没能对应到任何已有球员身份
PlayerTrackingStatus = Literal["detected", "interpolated", "lost", "inactive", "unmatched"]

# 球员身份（把某条轨迹判定为"目标球员"）所使用的方法：
# - rule：基于规则（例如谁离目标半场最近）
# - attention：基于注意力模型（神经网络判断谁最值得关注）
# - fallback：前面都不靠谱时，退而求其次的兜底策略
PlayerSelectionMode = Literal["rule", "attention", "fallback"]

# 候选轨迹的"身份标签"：
# - target_player：目标球员
# - neighbor_court_player：隔壁球场的人（干扰项）
# - spectator：观众（干扰项）
# - uncertain：无法确定
PlayerCandidateLabel = Literal["target_player", "neighbor_court_player", "spectator", "uncertain"]


def _validate_point(values: list[float], label: str) -> list[float]:
    """校验一个二维点（[x, y]）是否合法。

    参数：
        values：原始的列表，应当恰好包含 2 个数字。
        label：这个点的名字，仅用于报错时给出更清楚的提示。
    返回：
        转换后的 [float, float] 列表。

    为什么需要它：Pydantic 的 `Field(min_length=2, max_length=2)` 只能保证
    "列表长度是 2"，但保证不了"里面真的是数字、且没有无穷大/NaN"。
    所以这个函数做了更严格的检查。
    """
    # 长度必须是 2，否则报错
    if len(values) != 2:
        raise ValueError(f"{label} must contain exactly 2 numeric values")
    # 把每个元素强制转成 float（例如整数 3 变 3.0）；如果转不了会抛异常
    point = [float(value) for value in values]
    # isfinite 排除无穷大（inf）和 NaN（not a number），这些在数学上没有意义
    if not all(isfinite(value) for value in point):
        raise ValueError(f"{label} must contain only finite numeric values")
    return point


def _validate_bbox(values: list[float]) -> list[float]:
    """校验一个检测框（[x1, y1, x2, y2]）是否合法。

    与 `_validate_point` 类似，但这里要求恰好 4 个数字，
    因为检测框用左上角 (x1, y1) 和右下角 (x2, y2) 两个点表示。
    """
    if len(values) != 4:
        raise ValueError("bbox must contain exactly 4 numeric values")
    bbox = [float(value) for value in values]
    if not all(isfinite(value) for value in bbox):
        raise ValueError("bbox must contain only finite numeric values")
    return bbox


class Detection(BaseModel):
    """单帧里检测到的"一个人"。

    这是检测算法最底层的输出：在某帧画面中，框出了某个人，
    并给出这个框的置信度。
    """

    # 检测框：[x1, y1, x2, y2]，min_length/max_length=4 保证恰好 4 个数字
    bbox: list[float] = Field(min_length=4, max_length=4)
    # 置信度：模型认为"这里确实有人"的概率，范围 0~1
    confidence: float = Field(ge=0, le=1)
    # 类别名：这里系统只关心"人"，所以固定为 "person"
    class_name: Literal["person"] = "person"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        """用上面的 `_validate_bbox` 对 bbox 做严格校验。"""
        return _validate_bbox(value)


class Track(BaseModel):
    """一条被持续跟踪的轨迹（跨多帧的同一个人）。

    与 Detection 的区别：Detection 是"某一帧里的一个框"，
    Track 是"把很多帧里同一个人连起来后，这条轨迹当前这一帧的状态"。
    """

    # 轨迹 ID：从 1 开始的正整数（ge=1 表示 >=1）
    track_id: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    # 这条轨迹是否处于"跟丢"状态（True 表示暂时丢失）
    lost: bool = False

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)


class SourceFrameSize(BaseModel):
    """原始视频帧的宽高（像素）。"""

    # 宽度，至少 1 像素
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class FrameDetection(BaseModel):
    """带时间信息的单帧检测（Detection + 帧序号 + 时间戳）。

    相比 Detection，它额外记录了"这是第几帧、当时是第几秒"，
    以及这条检测是否已经被关联到某个 track_id / player_id。
    """

    # 帧序号，从 0 开始
    frame_index: int = Field(ge=0)
    # 该帧对应的视频时间（秒），从 0 开始
    timestamp_seconds: float = Field(ge=0)
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    class_name: Literal["person"] = "person"
    # 跟踪算法给这条检测分配的轨迹 ID（还没关联时为 None）
    track_id: Optional[str] = None
    # 这条检测对应到的最终"球员身份"ID（还没判定时为 None）
    player_id: Optional[str] = None
    # 额外的文字标签（例如 "target"），可选
    label: Optional[str] = None
    # 该帧的原始宽度/高度，用于把坐标换算回原图比例
    source_width: int = Field(ge=1)
    source_height: int = Field(ge=1)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)


class DetectionOverlayFrame(BaseModel):
    """一帧的"检测叠加"数据：某一帧里所有检测的集合。

    前端拿到它后，可以在这一帧画上所有检测框。
    """

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    # 这一帧里所有的检测结果；default_factory=list 表示默认是空列表
    detections: list[FrameDetection] = Field(default_factory=list)


class TrackingOverlayArtifact(BaseModel):
    """"检测叠加"这个产物的完整描述（多帧 + 元信息）。

    Artifact（产物）指的是分析流程跑完后留下的一团结果数据。
    这里是把所有帧的检测叠加数据汇总起来，并附带视频的元信息。
    """

    # 任务 ID（analysis 任务的唯一标识）
    job_id: str
    video_id: Optional[str] = None
    # 产物状态：available=可用 / no_detections=没检测到人 / unavailable=不可用
    status: Literal["available", "no_detections", "unavailable"] = "unavailable"
    # 对状态的人类可读说明（例如"未找到任何检测框"）
    detail: str
    # 原始视频帧尺寸
    source: SourceFrameSize
    # 视频帧率（fps），默认 0.0
    fps: float = Field(default=0.0, ge=0)
    # 视频总帧数
    frame_count: int = Field(default=0, ge=0)
    # 实际处理过的帧数（可能小于总帧数，例如跳帧处理）
    processed_frame_count: int = Field(default=0, ge=0)
    # 帧步长：每隔几帧处理一次（1 表示逐帧处理）
    frame_stride: int = Field(default=1, ge=1)
    # 每一帧的检测叠加数据
    frames: list[DetectionOverlayFrame] = Field(default_factory=list)


class FootpointEstimate(BaseModel):
    """估计出的"脚点"——即一个人站在画面上的哪个像素位置。

    脚点（footpoint）是人和球场接触的点，通常是检测框底部中心，
    用来代表"这个人当前的位置"。
    """

    # 图像上的脚点坐标 [x, y]
    image_footpoint: list[float] = Field(min_length=2, max_length=2)
    # 用哪种方法估计的脚点（见顶部 FootpointMethod 说明）
    method: FootpointMethod = "bbox_bottom_center"

    @field_validator("image_footpoint")
    @classmethod
    def validate_image_footpoint(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "image_footpoint")


class PlayerFramePosition(BaseModel):
    """某球员在某一帧的"完整位置信息"。

    这是跟踪结果里最核心的一行数据：既包含画面上的脚点，
    也包含换算后"在球场坐标系里的真实位置"，以及质量标记。
    """

    frame_index: int = Field(ge=0)
    # 该帧时间戳（秒）
    timestamp: float = Field(ge=0)
    # 对应轨迹 ID
    track_id: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    # 画面上的脚点 [x, y]
    image_footpoint: list[float] = Field(min_length=2, max_length=2)
    # 球场坐标系中的位置 [x, y]（可能还没换算出来，所以可为 None）
    court_position: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    # 球场坐标的单位（米或英尺）
    court_unit: CourtUnit = "ft"
    confidence: float = Field(ge=0, le=1)
    # 这个位置是否"有效"（布尔版，方便程序判断）
    valid: bool = True
    # 位置有效性（枚举版，与 valid 配合，信息更明确）
    validity: PositionValidity = "valid"
    # 脚点估计方法
    footpoint_method: FootpointMethod = "bbox_bottom_center"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)

    @field_validator("image_footpoint")
    @classmethod
    def validate_image_footpoint(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "image_footpoint")

    @field_validator("court_position")
    @classmethod
    def validate_court_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        # 球场位置可能为 None（还没投影出来），这时直接放行
        if value is None:
            return None
        return _validate_point(value, "court_position")


class TrackingResult(BaseModel):
    """一次完整跟踪任务的汇总结果。

    把检测、轨迹、逐帧位置等所有产物集中在一起返回。
    """

    video_id: Optional[str] = None
    # 本次跟踪使用的标定（相机标定）ID；没做标定时为 None
    calibration_id: Optional[str] = None
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    frame_width: int = Field(default=0, ge=0)
    frame_height: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    # 所有原始检测
    detections: list[Detection] = Field(default_factory=list)
    # 所有帧的检测叠加数据
    overlay_frames: list[DetectionOverlayFrame] = Field(default_factory=list)
    # 所有轨迹
    tracks: list[Track] = Field(default_factory=list)
    # 每个球员在每一帧的位置
    positions: list[PlayerFramePosition] = Field(default_factory=list)


class PlayerTrackletFeature(BaseModel):
    """一条"轨迹片段（tracklet）"的聚合特征。

    跟踪算法会把一条轨迹在时间上切成小段，并对每段提取统计特征，
    用来判断"这段轨迹更像目标球员、还是隔壁球场的干扰项"。
    """

    track_id: int = Field(ge=1)
    # 这段轨迹起始/结束的帧序号
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    # 起始/结束时间（秒）
    first_timestamp_seconds: float = Field(ge=0)
    last_timestamp_seconds: float = Field(ge=0)
    # 这段轨迹共出现了多少次（被检测到的帧数）
    appearances: int = Field(ge=1)
    # 其中"有效位置"的帧数
    valid_positions: int = Field(default=0, ge=0)
    # 平均置信度 / 最近一次置信度
    mean_confidence: float = Field(default=0.0, ge=0, le=1)
    latest_confidence: float = Field(default=0.0, ge=0, le=1)
    # 平均检测框面积占整个画面的比例（越大说明人离镜头越近）
    mean_bbox_area_ratio: float = Field(default=0.0, ge=0)
    # 该片段在球场上的位置（均值 / 平均均值），可为 None
    court_position: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    mean_court_position: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    court_unit: CourtUnit = "ft"
    # 该片段在"目标半场"的占用比例（0~1），用于判断是否目标球员
    target_court_occupancy: float = Field(default=0.0, ge=0, le=1)
    # 到目标半场中心的平均/最大距离（米或英尺）
    mean_target_court_distance: float = Field(default=0.0, ge=0)
    max_target_court_distance: float = Field(default=0.0, ge=0)
    # 平均速度
    mean_speed: float = Field(default=0.0, ge=0)
    # 连续性（0~1）：轨迹是否连贯、有没有频繁断裂
    continuity: float = Field(default=0.0, ge=0, le=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    image_footpoint: list[float] = Field(min_length=2, max_length=2)

    @field_validator("bbox")
    @classmethod
    def validate_tracklet_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)

    @field_validator("image_footpoint")
    @classmethod
    def validate_tracklet_image_footpoint(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "image_footpoint")

    @field_validator("court_position", "mean_court_position")
    @classmethod
    def validate_tracklet_court_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        # 两个球场位置字段都可能为 None
        if value is None:
            return None
        return _validate_point(value, "court_position")


class PlayerSelectionDiagnostic(BaseModel):
    """"球员身份判定"对某条轨迹的决策诊断。

    当系统要从一堆轨迹里挑出"谁是我们的目标球员"时，
    会为每条轨迹算一个综合分数（final_score），并给出理由。
    这个模型就是把"为什么选/不选它"记录下来，方便调试和解释。
    """

    track_id: int = Field(ge=1)
    # 最终是否被选中为目标球员
    selected: bool
    # 判定时使用的方法（rule / attention / fallback）
    selection_mode: PlayerSelectionMode = "rule"
    # 如果走了兜底策略，这里说明原因
    fallback_reason: Optional[str] = None
    # 各项评分（都是 0~1 的小数）：
    target_court_score: float = Field(default=0.0, ge=0, le=1)  # 在目标半场的活动程度
    tracklet_quality_score: float = Field(default=0.0, ge=0, le=1)  # 轨迹质量
    group_consistency_score: float = Field(default=0.0, ge=0, le=1)  # 与同组其他人的一致程度
    # 注意力模型给出的"是/不是目标"的概率（可选）
    attention_target_probability: Optional[float] = Field(default=None, ge=0, le=1)
    attention_non_target_probability: Optional[float] = Field(default=None, ge=0, le=1)
    # 综合最终得分（0~1）
    final_score: float = Field(default=0.0, ge=0, le=1)
    # 给这条轨迹贴的身份标签
    candidate_label: PlayerCandidateLabel = "uncertain"
    # 人类可读的判断理由
    reason: str
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    # 其他附加的评分组成部分（开放字典，灵活存放额外信息）
    components: dict[str, Any] = Field(default_factory=dict)


class PlayerSelectionArtifact(BaseModel):
    """"球员身份判定"产物的完整描述。"""

    job_id: str
    video_id: Optional[str] = None
    status: Literal["available", "unavailable"] = "available"
    detail: str
    selection_mode: PlayerSelectionMode = "rule"
    fallback_reason: Optional[str] = None
    # 最多判定几名"参与者"（双打通常最多 4 人）
    participant_limit: int = Field(default=4, ge=1)
    # 每条轨迹的诊断信息
    diagnostics: list[PlayerSelectionDiagnostic] = Field(default_factory=list)
    # 用于训练注意力模型的轨迹特征样本
    training_samples: list[PlayerTrackletFeature] = Field(default_factory=list)


class CourtDimensions(BaseModel):
    """球场尺寸（宽、长、单位）。"""

    # 宽度 / 长度，必须 > 0（gt=0）
    width: float = Field(gt=0)
    length: float = Field(gt=0)
    unit: CourtUnit


class CourtCoordinateMetadata(BaseModel):
    """球场坐标系的元数据：标准尺寸 + 单位换算关系。

    系统内部以"米"为规范单位（canonical），同时也保存一份
    英制（英尺）的参考值，方便不同习惯的用户/前端使用。
    """

    # 规范单位（内部统一使用的长度单位）
    court_unit: CourtUnit = "m"
    # 标准球场尺寸（米）：单打宽 6.10m，长 13.41m
    canonical: CourtDimensions = Field(
        default_factory=lambda: CourtDimensions(width=6.10, length=13.41, unit="m")
    )
    # 英制参考尺寸（英尺）：宽 20ft，长 44ft
    imperial_reference: CourtDimensions = Field(
        default_factory=lambda: CourtDimensions(width=20.0, length=44.0, unit="ft")
    )
    # 英尺到米的换算系数：1 英尺 = 0.3048 米
    feet_to_meters: float = Field(default=0.3048, gt=0)


class PlayerTrajectorySample(BaseModel):
    """球员轨迹中的一个采样点（某一帧的位置快照）。

    与 PlayerFramePosition 类似，但更偏向"轨迹"语义：
    它记录的是某个 player_id 在某帧的球场坐标（court_x, court_y），
    并区分这个点是"真实检测到的"还是"插值补出来的"。
    """

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    # 球员身份 ID（字符串）
    player_id: str
    # 对应的轨迹 ID（可选）
    track_id: Optional[int] = None
    # 原始检测框（可选，因为插值点可能没有框）
    bbox: Optional[list[float]] = Field(default=None, min_length=4, max_length=4)
    # 画面脚点（可选）
    image_footpoint: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    # 球场坐标 x / y（必填）
    court_x: float
    court_y: float
    # 平滑（降噪）后的坐标，可选
    smoothed_court_x: Optional[float] = None
    smoothed_court_y: Optional[float] = None
    court_unit: CourtUnit = "m"
    confidence: float = Field(default=0.0, ge=0, le=1)
    # 跟踪状态（见顶部 PlayerTrackingStatus 说明）
    tracking_status: PlayerTrackingStatus = "detected"
    # 是否为插值点（True 表示是补出来的，不是真实检测）
    is_interpolated: bool = False
    # 数据来源：detector=检测器 / interpolation=插值
    source: Literal["detector", "interpolation"] = "detector"

    @field_validator("bbox")
    @classmethod
    def validate_optional_bbox(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_bbox(value)

    @field_validator("image_footpoint")
    @classmethod
    def validate_optional_image_footpoint(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "image_footpoint")


class PlayerTrajectoryState(BaseModel):
    """某个球员轨迹的"运行状态"（跨帧持续维护的上下文）。

    跟踪算法会为每位球员维护一个状态对象，记录它现在是否活跃、
    历史上用过哪些轨迹 ID、最后一帧出现在哪、最后的速度是多少。
    """

    player_id: str
    # 当前状态：active=活跃 / lost=丢失 / inactive=不活跃
    status: Literal["active", "lost", "inactive"] = "inactive"
    # 当前正在使用的轨迹 ID 列表
    active_track_ids: list[int] = Field(default_factory=list)
    # 历史上用过的轨迹 ID 列表
    history_track_ids: list[int] = Field(default_factory=list)
    # 最后一次被看到时的帧序号（-1 表示还没出现过）
    last_seen_frame: int = -1
    # 最后已知位置（米），可选
    last_position_m: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    # 最后已知速度（米/秒），默认 [0.0, 0.0]
    last_velocity_mps: list[float] = Field(default_factory=lambda: [0.0, 0.0], min_length=2, max_length=2)
    confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("last_position_m")
    @classmethod
    def validate_last_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "last_position_m")

    @field_validator("last_velocity_mps")
    @classmethod
    def validate_last_velocity(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "last_velocity_mps")


class PlayerIdentityDiagnostic(BaseModel):
    """球员身份管理过程中的事件诊断。

    当系统"创建/分配/重连/丢失"某个球员身份时，会记录一条事件，
    方便排查"为什么这个人一会儿叫 A 一会儿叫 B"之类的问题。
    """

    frame_index: int = Field(ge=0)
    # 事件类型：created=新建 / assigned=分配 / reconnected=重连 /
    #           lost=丢失 / inactive=停用 / unmatched=未匹配 / filtered=被过滤
    event: Literal["created", "assigned", "reconnected", "lost", "inactive", "unmatched", "filtered"]
    player_id: Optional[str] = None
    track_id: Optional[int] = None
    # 该事件的评分（可选）
    score: Optional[float] = None
    # 人类可读的原因说明
    reason: str
    # 事件发生时球场坐标（米），可选
    court_position_m: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)

    @field_validator("court_position_m")
    @classmethod
    def validate_diagnostic_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "court_position_m")


class PlayerTrajectoryCoverage(BaseModel):
    """单个球员轨迹的"覆盖率"统计。

    用来回答："这位球员的轨迹被我们完整记录了多少？"
    多少帧是检测到的、多少帧是插值补的、时间跨度多大。
    """

    player_id: str
    # 采样点总数 / 检测到数 / 插值数
    sample_count: int = Field(default=0, ge=0)
    detected_count: int = Field(default=0, ge=0)
    interpolated_count: int = Field(default=0, ge=0)
    # 首/尾出现的时间（秒），可选
    first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    # 首/尾出现的帧序号，可选
    first_frame_index: Optional[int] = Field(default=None, ge=0)
    last_frame_index: Optional[int] = Field(default=None, ge=0)
    # 各状态出现的次数统计（例如 {"detected": 120, "lost": 5}）
    status_counts: dict[str, int] = Field(default_factory=dict)
    # 该球员用过的轨迹 ID 历史
    history_track_ids: list[int] = Field(default_factory=list)


class PlayerTrajectoryCoverageDiagnostics(BaseModel):
    """所有球员轨迹覆盖率的汇总诊断。"""

    # 原始视频时长（秒），可选
    source_duration_seconds: Optional[float] = Field(default=None, ge=0)
    # 跟踪结束时间 / 轨迹开始时间 / 轨迹结束时间（秒），均可选
    tracking_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    trajectory_first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    trajectory_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    # 整体覆盖率（0~1）：轨迹覆盖的时间 / 视频总时长
    coverage_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    # 每位球员的覆盖率明细
    players: list[PlayerTrajectoryCoverage] = Field(default_factory=list)
    # 各类身份事件的总次数
    diagnostic_event_counts: dict[str, int] = Field(default_factory=dict)
    # 给前端的警告信息列表（例如"某球员覆盖率过低"）
    warnings: list[str] = Field(default_factory=list)


class PlayerTrajectoryArtifact(BaseModel):
    """"球员轨迹"产物的完整描述。"""

    job_id: str
    video_id: Optional[str] = None
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    # 球场坐标元数据（标准尺寸、单位换算），默认按规范初始化
    court: CourtCoordinateMetadata = Field(default_factory=CourtCoordinateMetadata)
    # 每个球员的轨迹采样点列表，键是 player_id
    players: dict[str, list[PlayerTrajectorySample]] = Field(default_factory=dict)
    # 每个球员的运行状态，键是 player_id
    states: dict[str, PlayerTrajectoryState] = Field(default_factory=dict)
    # 身份管理事件诊断列表
    diagnostics: list[PlayerIdentityDiagnostic] = Field(default_factory=list)
    # 覆盖率诊断（可选，可能还没计算）
    coverage: Optional[PlayerTrajectoryCoverageDiagnostics] = None


class BoundingBox(BaseModel):
    """用四个角点表示的检测框（与 list[float] 版相比，字段更直观）。

    有些代码更喜欢用命名字段 x1,y1,x2,y2 而非 [x1,y1,x2,y2] 列表，
    这个模型就是为此准备的。
    """

    x1: float
    y1: float
    x2: float
    y2: float


class PersonDetection(BaseModel):
    """带框的"人"检测（使用命名字段版的 BoundingBox）。"""

    frame_index: int = Field(ge=0)
    label: Literal["person"] = "person"
    confidence: float = Field(ge=0, le=1)
    # 使用上面的 BoundingBox 而不是 list[float]
    bbox: BoundingBox
    # 提示这个检测应归属到哪条轨迹（可选，仅做提示，不强制）
    track_hint: Optional[str] = None


class ImageTrackPoint(BaseModel):
    """图像空间里、某条轨迹在某一帧的点。

    与 PlayerTrajectorySample 的区别：这里专门表示"在原始画面上"
    的轨迹点（ImagePoint），并标注这个点在球场的"近侧/远侧"。
    """

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    # 轨迹 ID（字符串）
    track_id: str
    # 图像坐标点（来自 calibration 模块的 ImagePoint）
    image_point: ImagePoint
    confidence: float = Field(ge=0, le=1)
    # 这个点在球场的哪一侧：near=近侧 / far=远侧 / unknown=未知
    side: Literal["near", "far", "unknown"] = "unknown"


class ProjectedCourtPoint2D(BaseModel):
    """观测到的"球场坐标系投影点"；可能落在标准球场范围之外。

    把图像上的点通过标定矩阵（homography）投影到球场平面后，
    得到的坐标可能不在标准球场内（例如人在界外），所以这里不做范围限制，
    只保证坐标是有限数字。
    """

    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def validate_coordinate(cls, value: float) -> float:
        coordinate = float(value)
        if not isfinite(coordinate):
            raise ValueError("projected court coordinate must be finite")
        return coordinate


class ProjectedTrackPoint(ImageTrackPoint):
    """在 ImageTrackPoint 基础上，额外带一个"投影后的球场坐标点"。

    也就是说：这个点既知道它在画面上的位置（image_point），
    也知道它被换算到球场后的位置（court_point）。
    """

    court_point: ProjectedCourtPoint2D


class PlayerTrack(BaseModel):
    """一条完整的球员轨迹：包含多个投影点，并标注所在球场侧。

    这是"轨迹"这层数据的最终形态，前端可以把它连成一条线画出来。
    """

    # 轨迹 ID
    track_id: str
    # 该轨迹主要在球场的哪一侧
    side: Literal["near", "far", "unknown"] = "unknown"
    # 这条轨迹上的所有投影点（用 typing.List 写法，和上面一致）
    points: List[ProjectedTrackPoint]
