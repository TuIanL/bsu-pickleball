from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

TrendDirection = Literal["up", "down", "steady"]
ReportType = Literal["movement", "diagnosis"]
InsightTone = Literal["advantage", "risk", "error", "training"]
AnalysisJobStatus = Literal["uploaded", "queued", "processing", "failed", "completed", "canceled"]
AnalysisCanonicalStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
AnalysisMode = Literal["demo", "real", "limited"]
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
AnalysisStageStatus = Literal["pending", "active", "done", "failed", "skipped", "canceled"]

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

ANALYSIS_ERROR_CODES: dict[str, str] = {
    "video_not_found": "ANALYSIS_VIDEO_NOT_FOUND",
    "stage_failed": "ANALYSIS_STAGE_FAILED",
    "job_canceled": "ANALYSIS_JOB_CANCELED",
    "stage_timeout": "ANALYSIS_STAGE_TIMEOUT",
    "internal_error": "ANALYSIS_INTERNAL_ERROR",
}


class AnalysisUploadMetadata(BaseModel):
    fileName: str
    fileSize: Optional[int] = None
    matchTitle: str
    venue: str
    matchDate: str
    matchFormat: Literal["singles", "doubles"]
    cameraAngle: Literal["baseline", "sideline", "elevated", "unknown"]
    athleteLabel: str
    level: str


class AnalysisPipelineOptions(BaseModel):
    videoId: Optional[str] = None
    calibrationId: Optional[str] = None
    frameStride: int = Field(default=1, ge=1)


class AnalysisStage(BaseModel):
    id: AnalysisStageId
    label: str
    status: AnalysisStageStatus
    detail: str
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    durationMs: Optional[int] = None
    progress: int = Field(default=0, ge=0, le=100)
    errorCode: Optional[str] = None
    publicMessage: Optional[str] = None
    internalMessage: Optional[str] = None
    retryCount: int = Field(default=0, ge=0)
    counters: dict[str, Any] = Field(default_factory=dict)


class AnalysisJobCreate(BaseModel):
    metadata: AnalysisUploadMetadata
    videoId: Optional[str] = None
    calibrationId: Optional[str] = None
    frameStride: int = Field(default=1, ge=1)
    priority: int = Field(default=0, ge=0, le=100)
    requestNewVersion: bool = False


class AnalysisJobSummary(BaseModel):
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
    attempt: int = Field(default=0, ge=0)
    inputSignature: Optional[str] = None
    configSignature: Optional[str] = None
    analysisVersion: int = Field(default=1, ge=1)
    previousJobId: Optional[str] = None
    frameStride: int = Field(default=1, ge=1)
    metadata: AnalysisUploadMetadata
    stages: list[AnalysisStage]
    reportId: Optional[str] = None
    errorMessage: Optional[str] = None
    errorCode: Optional[str] = None
    publicErrorMessage: Optional[str] = None
    internalErrorMessage: Optional[str] = None
    videoId: Optional[str] = None
    calibrationId: Optional[str] = None
    analysisMode: AnalysisMode = "demo"


AnalysisDeleteStatus = Literal["deleted", "blocked", "not_found", "failed"]


class AnalysisDeleteResult(BaseModel):
    job_id: str
    status: AnalysisDeleteStatus
    detail: str


class AnalysisDeleteRequest(BaseModel):
    job_ids: list[str] = Field(min_length=1)


class Metric(BaseModel):
    id: str
    icon: str
    label: str
    value: str
    detail: str
    trend: str
    direction: TrendDirection
    progress: int
    sparkline: list[float]


class CourtPoint(BaseModel):
    id: str
    x: float
    y: float
    intensity: float
    label: str


class CourtRoute(BaseModel):
    id: str
    from_: CourtPoint = Field(alias="from")
    to: CourtPoint
    label: str
    result: Literal["得分", "受迫回球", "失误", "相持"]


class MovementPoint(BaseModel):
    x: float
    y: float


class Rally(BaseModel):
    id: str
    title: str
    duration: str
    shots: int
    pattern: str
    result: str
    observation: str


class ReportSession(BaseModel):
    athlete: str
    venue: str
    date: str
    level: str
    reportId: str
    summary: str
    metrics: list[dict]
    landingPoints: list[CourtPoint]
    routes: list[CourtRoute]
    movementPath: list[MovementPoint]
    rallies: list[Rally]


class MatchSummary(BaseModel):
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
    id: str
    label: str
    team: Literal["near", "far"]
    x: float
    y: float
    color: str


class ShotTrajectory(BaseModel):
    id: str
    path: str
    color: str
    label: str


class VideoOverlayLabel(BaseModel):
    id: str
    label: str
    tone: InsightTone
    x: float
    y: float


class TimelineMarker(BaseModel):
    id: str
    time: str
    position: float
    label: str
    tone: InsightTone


class Highlight(BaseModel):
    id: str
    title: str
    time: str
    result: str
    tone: InsightTone
    description: str


class CoachNote(BaseModel):
    id: str
    tone: InsightTone
    title: str
    body: str


class Diagnosis(BaseModel):
    id: str
    issue: str
    severity: Literal["高", "中", "低"]
    evidence: str
    suggestion: str
    expectedOutcome: str
    priority: str


class ReportAction(BaseModel):
    type: ReportType
    title: str
    description: str
    path: str


class ReportDefinition(BaseModel):
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
    id: str
    issueId: str
    title: str
    learningContent: str
    practiceTask: str
    nextTarget: str
    progress: dict


class DrillRecommendation(BaseModel):
    id: str
    title: str
    goal: str
    duration: str
    evidence: str
    difficulty: Literal["基础", "进阶", "高级"]
    linkedReport: ReportType


class ShotRow(BaseModel):
    id: str
    time: str
    type: str
    player: str
    placement: str
    qualityScore: int
    qualityBand: Literal["high", "medium", "low"]
    result: str


class SkillRating(BaseModel):
    id: str
    label: str
    score: int
    note: str


class ProgressPoint(BaseModel):
    match: str
    performance: int
    errors: int
    thirdShot: int
    kitchen: int


class AnalysisReport(BaseModel):
    version: Literal["analysis-report-v1"]
    source: Literal["demo", "job"]
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
