from typing import Literal, Optional

from pydantic import BaseModel, Field

TrendDirection = Literal["up", "down", "steady"]
ReportType = Literal["landing", "movement", "rally", "diagnosis"]
InsightTone = Literal["advantage", "risk", "error", "training"]
AnalysisJobStatus = Literal["uploaded", "queued", "processing", "failed", "completed"]
AnalysisStageId = Literal[
    "upload",
    "queue",
    "frame-sampling",
    "detection",
    "pose",
    "tracking",
    "court-calibration",
    "event-analysis",
    "report",
]


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


class AnalysisStage(BaseModel):
    id: AnalysisStageId
    label: str
    status: Literal["pending", "active", "done", "failed"]
    detail: str


class AnalysisJobCreate(BaseModel):
    metadata: AnalysisUploadMetadata


class AnalysisJobSummary(BaseModel):
    id: str
    status: AnalysisJobStatus
    stage: AnalysisStageId
    progress: int = Field(ge=0, le=100)
    createdAt: str
    updatedAt: str
    metadata: AnalysisUploadMetadata
    stages: list[AnalysisStage]
    reportId: Optional[str] = None
    errorMessage: Optional[str] = None


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
    visualization: Literal["heat", "movement", "rally", "diagnosis"]
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
