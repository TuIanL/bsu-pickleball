export type ScoringCalibrationPackageStatus = "draft" | "reviewed" | "locked";
export type AnnotationSource = "manual" | "algorithm";
export type AnnotationDecision = "accepted" | "corrected" | "rejected" | "unreviewed";
export type ShotStage = "serve" | "return" | "other" | "unknown";
export type OpportunityStatus = "eligible" | "not_applicable" | "unobservable";
export type ShotOutcome = "in_play" | "net" | "out" | "unknown";
export type LandingStatus = "measured" | "not_applicable" | "unobservable";
export type LandingZone = "short" | "middle" | "deep" | "unknown";

export interface AnnotationValidationIssue {
  code: string;
  message: string;
  annotation_id?: string | null;
  severity: "error" | "warning" | string;
}

export interface AnnotationQualitySummary {
  total_count: number;
  confirmed_count: number;
  unknown_or_unobservable_count: number;
  unmatched_candidate_count: number;
  conflict_count: number;
  evidence_complete_rate: number;
  blocking_error_count: number;
  warning_count: number;
}

export interface ScoringCalibrationAnnotation {
  id: string;
  package_revision_id: string;
  source: AnnotationSource;
  candidate_id?: string | null;
  event_ms: number;
  evidence_start_ms: number;
  evidence_end_ms: number;
  video_id?: string | null;
  rally_segment_id?: string | null;
  player_id?: string | null;
  stage?: ShotStage | null;
  opportunity_status?: OpportunityStatus | null;
  outcome?: ShotOutcome | null;
  landing_status?: LandingStatus | null;
  landing_zone?: LandingZone | null;
  confidence?: number | null;
  note?: string | null;
  decision: AnnotationDecision;
  revoked: boolean;
  created_at: string;
  updated_at: string;
}

export interface ScoringCalibrationCandidate {
  candidate_id: string;
  candidate_type: string;
  source: string;
  source_job_id?: string | null;
  timestamp_ms: number;
  start_ms?: number | null;
  end_ms?: number | null;
  player_id?: string | null;
  rally_id?: string | null;
  confidence?: number | null;
  payload: Record<string, unknown>;
  artifact_name?: string | null;
  detector_version?: string | null;
  coverage_warning?: string | null;
  coverage?: Record<string, unknown>;
  decision: AnnotationDecision;
  annotation_id?: string | null;
}

export interface ScoringCalibrationPackage {
  id: string;
  package_id: string;
  capture_take_id: string;
  revision: number;
  schema_version: string;
  status: ScoringCalibrationPackageStatus;
  annotator?: string | null;
  note?: string | null;
  source_job_id?: string | null;
  supersedes_id?: string | null;
  quality: AnnotationQualitySummary;
  validation_issues: AnnotationValidationIssue[];
  annotations: ScoringCalibrationAnnotation[];
  candidates: ScoringCalibrationCandidate[];
  candidate_status?: "available" | "empty" | "unavailable";
  candidate_message?: string | null;
  candidate_coverage_warning?: string | null;
  created_at: string;
  updated_at: string;
  locked_at?: string | null;
}

export interface AnnotationPackageCreateRequest {
  annotator?: string;
  note?: string;
  source_job_id?: string;
}

export interface AnnotationPackageRevisionRequest {
  annotator?: string;
  note?: string;
}

export interface AnnotationUpsertRequest {
  event_ms: number;
  evidence_start_ms: number;
  evidence_end_ms: number;
  video_id?: string;
  rally_segment_id?: string;
  player_id?: string;
  stage?: ShotStage;
  opportunity_status?: OpportunityStatus;
  outcome?: ShotOutcome;
  landing_status?: LandingStatus;
  landing_zone?: LandingZone;
  confidence?: number;
  note?: string;
  candidate_id?: string;
  decision: AnnotationDecision;
}

export interface AnnotationUpdateRequest extends Partial<AnnotationUpsertRequest> {
  decision?: AnnotationDecision;
}

export interface CandidateDecisionRequest {
  decision: AnnotationDecision;
  annotation_id?: string;
}

export interface GoldSetResponse {
  schema_version: string;
  package_id: string;
  revision: number;
  capture_take_id: string;
  status: "locked";
  provenance: Record<string, unknown>;
  annotations: ScoringCalibrationAnnotation[];
  quality: AnnotationQualitySummary;
}
