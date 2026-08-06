"""
分析任务相关的 Pydantic 数据模型 —— 任务创建、状态追踪、报告结构等。

本文件是整个"分析任务"业务的核心数据契约：
- 任务的生命周期（创建→排队→处理→完成/失败/取消）与阶段（stages）
- 任务摘要（Summary）返回给前端轮询进度
- 最终给用户的"分析报告"（Report）及其中各类可视化/诊断/训练建议结构
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# 比赛制式
MatchFormat = Literal["singles", "doubles"]

# 趋势方向：上升 / 下降 / 持平
TrendDirection = Literal["up", "down", "steady"]
# 报告类型：运动表现 / 诊断
ReportType = Literal["movement", "diagnosis"]
# 洞察语气：优势 / 风险 / 错误 / 训练
InsightTone = Literal["advantage", "risk", "error", "training"]
# 任务业务状态
AnalysisJobStatus = Literal["uploaded", "queued", "processing", "failed", "completed", "canceled"]
# 任务规范化状态（前端统一展示用）
AnalysisCanonicalStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
# 分析模式：演示 / 真实 / 受限
AnalysisMode = Literal["demo", "real", "limited"]
# 流水线阶段 id（稳定集合，外加 str 兼容未来扩展）
AnalysisStageId = Literal[
    "upload",
    "queue",
    "calibration",
    "video-read",
    "frame-sampling",
    "detection",
    "pose",
    "tracking",
    "projection",
    "metrics",
    "visualization",
    "report",
] | str
# 阶段状态：待执行 / 进行中 / 完成 / 失败 / 跳过 / 取消
AnalysisStageStatus = Literal["pending", "active", "done", "failed", "skipped", "canceled"]

# 稳定的阶段 id 列表（用于校验/排序）
STABLE_ANALYSIS_STAGE_IDS: tuple[str, ...] = (
    "upload",
    "queue",
    "calibration",
    "video-read",
    "frame-sampling",
    "detection",
    "pose",
    "tracking",
    "projection",
    "metrics",
    "visualization",
    "report",
)

# 错误码 → 对外错误标识 的映射表
ANALYSIS_ERROR_CODES: dict[str, str] = {
    "video_not_found": "ANALYSIS_VIDEO_NOT_FOUND",
    "stage_failed": "ANALYSIS_STAGE_FAILED",
    "job_canceled": "ANALYSIS_JOB_CANCELED",
    "stage_timeout": "ANALYSIS_STAGE_TIMEOUT",
    "internal_error": "ANALYSIS_INTERNAL_ERROR",
}


class AnalysisUploadMetadata(BaseModel):
    """上传分析时附带的比赛元信息（前端填写/自动生成）。"""
    fileName: str
    fileSize: Optional[int] = None
    sourceFps: Optional[float] = Field(default=None, gt=0, le=240)
    matchTitle: str                 # 比赛标题
    venue: str                      # 场馆
    matchDate: str                  # 比赛日期
    matchFormat: MatchFormat        # 单打/双打
    cameraAngle: Literal["baseline", "sideline", "elevated", "unknown"]  # 机位角度
    athleteLabel: str               # 运动员标签
    level: str                      # 水平/级别
    camera_id: Optional[str] = None
    recording_session_id: Optional[str] = None
    capture_take_id: Optional[str] = None
    session_dir: Optional[str] = None
    camera_slot: Optional[Literal["cam_1", "cam_2"]] = None  # 双摄机位标识


class AnalysisPipelineOptions(BaseModel):
    """分析流水线的选项（视频/标定 id、抽帧步长、门控阈值覆盖）。"""
    videoId: Optional[str] = None
    calibrationId: Optional[str] = None
    frameStride: int = Field(default=1, ge=1)  # 每隔几帧处理一帧（≥1）
    sourceFps: Optional[float] = Field(default=None, gt=0, le=240)
    courtViewMatchThreshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)  # 覆盖场地视角门控匹配阈值


class AnalysisStage(BaseModel):
    """单个任务阶段的信息（前端进度条用）。"""
    id: AnalysisStageId
    label: str
    status: AnalysisStageStatus
    detail: str
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    durationMs: Optional[int] = None     # 耗时（毫秒）
    progress: int = Field(default=0, ge=0, le=100)  # 进度百分比
    errorCode: Optional[str] = None
    publicMessage: Optional[str] = None  # 给用户看的信息
    internalMessage: Optional[str] = None  # 内部调试信息
    retryCount: int = Field(default=0, ge=0)
    counters: dict[str, Any] = Field(default_factory=dict)


class AnalysisJobCreate(BaseModel):
    """创建分析任务的请求。"""
    metadata: AnalysisUploadMetadata
    videoId: Optional[str] = None
    calibrationId: Optional[str] = None
    frameStride: int = Field(default=1, ge=1)
    sourceFps: Optional[float] = Field(default=None, gt=0, le=240)
    priority: int = Field(default=0, ge=0, le=100)
    requestNewVersion: bool = False
    courtViewMatchThreshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    clipStartMs: Optional[int] = Field(default=None, ge=0)
    clipEndMs: Optional[int] = Field(default=None, ge=0)
    captureSegmentId: Optional[str] = None
    segmentVersion: Optional[int] = None
    recording_session_id: Optional[str] = None
    camera_slot: Optional[Literal["cam_1", "cam_2"]] = None
    # 任务级推理开关：None 表示沿用后端全局配置（enable_model_inference / enable_pose_inference）
    enableModelInference: Optional[bool] = None
    enablePoseInference: Optional[bool] = None


class AnalysisJobSummary(BaseModel):
    """任务摘要：前端轮询进度时返回的核心信息。"""
    id: str
    status: AnalysisJobStatus
    canonicalStatus: AnalysisCanonicalStatus = "queued"
    displayStatus: Optional[AnalysisJobStatus] = None
    stage: AnalysisStageId
    progress: int = Field(ge=0, le=100)
    createdAt: str
    updatedAt: str
    queuedAt: Optional[str] = None
    startedAt: Optional[str] = None
    finishedAt: Optional[str] = None
    cancelRequestedAt: Optional[str] = None
    canceledAt: Optional[str] = None
    workerId: Optional[str] = None
    priority: int = Field(default=0, ge=0, le=100)
    attempt: int = Field(default=0, ge=0)            # 当前尝试次数
    inputSignature: Optional[str] = None             # 输入签名（用于幂等/去重）
    configSignature: Optional[str] = None            # 配置签名
    analysisVersion: int = Field(default=1, ge=1)
    previousJobId: Optional[str] = None
    frameStride: int = Field(default=1, ge=1)
    sourceFps: Optional[float] = Field(default=None, gt=0, le=240)
    metadata: AnalysisUploadMetadata
    stages: list[AnalysisStage]                      # 各阶段详情
    reportId: Optional[str] = None
    errorMessage: Optional[str] = None
    errorCode: Optional[str] = None
    publicErrorMessage: Optional[str] = None
    internalErrorMessage: Optional[str] = None
    videoId: Optional[str] = None
    calibrationId: Optional[str] = None
    analysisMode: AnalysisMode = "demo"
    clipStartMs: Optional[int] = None
    clipEndMs: Optional[int] = None
    captureSegmentId: Optional[str] = None
    segmentVersion: Optional[int] = None
    recordingSessionId: Optional[str] = None
    cameraSlot: Optional[Literal["cam_1", "cam_2"]] = None
    # 任务实际使用的推理开关（创建时由 payload 或全局配置解析后固化；旧任务缺失时为 None）
    enableModelInference: Optional[bool] = None
    enablePoseInference: Optional[bool] = None


# 删除任务的状态
AnalysisDeleteStatus = Literal["deleted", "blocked", "not_found", "failed"]


class AnalysisDeleteResult(BaseModel):
    """单个任务删除结果。"""
    job_id: str
    status: AnalysisDeleteStatus
    detail: str


class AnalysisDeleteRequest(BaseModel):
    """批量删除请求：一组 job_id。"""
    job_ids: list[str] = Field(min_length=1)


class Metric(BaseModel):
    """看板上的一个指标卡片（数值 + 趋势 + 迷你折线）。"""
    id: str
    icon: str
    label: str
    value: str
    detail: str
    trend: str
    direction: TrendDirection       # 趋势方向
    progress: int
    sparkline: list[float]          # 迷你折线数据


class CourtPoint(BaseModel):
    """球场上的一个坐标点（用于落点/路线可视化）。"""
    id: str
    x: float
    y: float
    intensity: float                # 强度（热力用）
    label: str


class CourtRoute(BaseModel):
    """球场上的一条路线（如某次击球的移动路径）。"""
    id: str
    from_: CourtPoint = Field(alias="from")  # 起点（字段名别名 from，避免与 Python 关键字冲突）
    to: CourtPoint                            # 终点
    label: str
    result: Literal["得分", "受迫回球", "失误", "相持"]


class MovementPoint(BaseModel):
    """移动轨迹上的一个点。"""
    x: float
    y: float


class Rally(BaseModel):
    """一个回合（多拍来回）。"""
    id: str
    title: str
    duration: str
    shots: int                  # 拍数
    pattern: str                # 回合模式
    result: str
    observation: str            # 观察点评


class ReportSession(BaseModel):
    """报告里的"会话"信息：运动员、场馆、各项可视化数据集合。"""
    athlete: str
    venue: str
    date: str
    level: str
    reportId: str
    summary: str
    metrics: list[dict]
    landingPoints: list[CourtPoint]          # 落点
    routes: list[CourtRoute]                  # 路线
    movementPath: list[MovementPoint]         # 移动路径
    rallies: list[Rally]


class MatchSummary(BaseModel):
    """报告里的比赛概览信息。"""
    title: str
    subtitle: str
    date: str
    venue: str
    teams: str
    score: str
    currentRally: str
    currentTime: str
    duration: str


class PlayerMarker(BaseModel):
    """视频叠加层上的球员标记。"""
    id: str
    label: str
    team: Literal["near", "far"]     # 近/远侧队伍
    x: float
    y: float
    color: str


class ShotTrajectory(BaseModel):
    """击球轨迹（叠加层用）。"""
    id: str
    path: str
    color: str
    label: str


class VideoOverlayLabel(BaseModel):
    """视频叠加层上的文字标签（带语气色）。"""
    id: str
    label: str
    tone: InsightTone
    x: float
    y: float


class TimelineMarker(BaseModel):
    """时间轴上的标记点。"""
    id: str
    time: str
    position: float
    label: str
    tone: InsightTone


class Highlight(BaseModel):
    """高光时刻。"""
    id: str
    title: str
    time: str
    result: str
    tone: InsightTone
    description: str


class CoachNote(BaseModel):
    """教练点评/建议。"""
    id: str
    tone: InsightTone
    title: str
    body: str


class Diagnosis(BaseModel):
    """诊断问题（发现问题 + 建议）。"""
    id: str
    issue: str
    severity: Literal["高", "中", "低"]   # 严重程度
    evidence: str                        # 证据
    suggestion: str                      # 建议
    expectedOutcome: str                 # 预期效果
    priority: str


class ReportAction(BaseModel):
    """报告里的一个可点击动作（跳转到某页）。"""
    type: ReportType
    title: str
    description: str
    path: str


class ReportDefinition(BaseModel):
    """一个报告区块（如"移动表现"或"诊断"）的定义与内容。"""
    type: ReportType
    title: str
    eyebrow: str
    summary: str
    heroMetric: str
    heroMetricLabel: str
    visualization: Literal["movement", "diagnosis"]
    metrics: list[Metric]
    insights: list[CoachNote]
    trainingLink: str


class TrainingRecommendation(BaseModel):
    """训练建议（关联到某个诊断问题）。"""
    id: str
    issueId: str
    title: str
    learningContent: str     # 学习内容
    practiceTask: str        # 练习任务
    nextTarget: str          # 下一步目标
    progress: dict


class DrillRecommendation(BaseModel):
    """训练小项（ drill）推荐。"""
    id: str
    title: str
    goal: str
    duration: str
    evidence: str
    difficulty: Literal["基础", "进阶", "高级"]
    linkedReport: ReportType


class ShotRow(BaseModel):
    """击球明细表中的一行。"""
    id: str
    time: str
    type: str
    player: str
    placement: str
    qualityScore: int
    qualityBand: Literal["high", "medium", "low"]
    result: str


class SkillRating(BaseModel):
    """技能评分项。"""
    id: str
    label: str
    score: int
    note: str


class ProgressPoint(BaseModel):
    """进度追踪中的一个数据点（按比赛）。"""
    match: str
    performance: int
    errors: int
    thirdShot: int      # 第三拍质量
    kitchen: int        # 网前表现


class MatchAnalysisContext(BaseModel):
    """比赛制式驱动的分析上下文——只包含稳定的比赛领域事实，不含算法内部配置。"""
    schema_version: Literal["match-analysis-context.v1"] = "match-analysis-context.v1"
    match_format: MatchFormat
    expected_player_count: Literal[2, 4]
    players_per_side: Literal[1, 2]
    near_side_quota: Literal[1, 2]
    far_side_quota: Literal[1, 2]
    enable_doubles_spacing: bool


class PlayerGroupProfile(BaseModel):
    """球员分组期望配置——由 MatchAnalysisContext 派生，评分算法内部使用。"""
    expected_same_side_others: int
    expected_opposite_players: int


SINGLES_PROFILE = PlayerGroupProfile(expected_same_side_others=0, expected_opposite_players=1)
DOUBLES_PROFILE = PlayerGroupProfile(expected_same_side_others=1, expected_opposite_players=2)


def build_match_context(match_format: MatchFormat | None) -> MatchAnalysisContext:
    if match_format is None or match_format == "doubles":
        return MatchAnalysisContext(
            match_format="doubles",
            expected_player_count=4,
            players_per_side=2,
            near_side_quota=2,
            far_side_quota=2,
            enable_doubles_spacing=True,
        )
    return MatchAnalysisContext(
        match_format="singles",
        expected_player_count=2,
        players_per_side=1,
        near_side_quota=1,
        far_side_quota=1,
        enable_doubles_spacing=False,
    )


def build_player_group_profile(ctx: MatchAnalysisContext) -> PlayerGroupProfile:
    return SINGLES_PROFILE if ctx.match_format == "singles" else DOUBLES_PROFILE


def _count_match_score(actual: int, expected: int) -> float:
    return 1.0 - min(1.0, abs(actual - expected) / max(1, expected))


class AnalysisReport(BaseModel):
    """完整分析报告：前端报告页渲染所需的全部结构化数据。"""
    version: Literal["analysis-report-v1"]
    source: Literal["demo", "job"]    # 数据来源（演示/真实任务）
    jobId: Optional[str] = None
    reportId: str
    generatedAt: str
    metadata: AnalysisUploadMetadata
    match: MatchSummary
    session: ReportSession
    dashboardMetrics: list[Metric]
    reportDefinitions: list[ReportDefinition]
    reportActions: list[ReportAction]
    playerMarkers: list[PlayerMarker]
    shotTrajectories: list[ShotTrajectory]
    videoOverlayLabels: list[VideoOverlayLabel]
    timelineMarkers: list[TimelineMarker]
    highlights: list[Highlight]
    coachNotes: list[CoachNote]
    diagnoses: list[Diagnosis]
    trainingRecommendations: list[TrainingRecommendation]
    drillRecommendations: list[DrillRecommendation]
    shotRows: list[ShotRow]
    skillRatings: list[SkillRating]
    progressPoints: list[ProgressPoint]
