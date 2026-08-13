export type SyncAnchorState = "not_required" | "required" | "draft" | "confirmed" | "auto_degraded" | "invalidated";
export type SyncAnchorSource = "manual_anchors" | "auto_degraded_from_recording_timing" | "legacy" | "none";

export interface SyncAnchor {
  id: string;
  label: string;
  note: string;
  frame_by_camera: Record<string, number>;
  pts_by_camera: Record<string, number>;
  created_at?: string | null;
}

export interface SyncAnchorQualitySummary {
  anchor_count: number;
  coverage_ratio: number;
  residual_rms_ms?: number | null;
  quality: "good" | "degraded" | "unknown";
  valid_start_seconds?: number | null;
  valid_end_seconds?: number | null;
  reason?: string | null;
}

export interface SyncAnchorProvenance {
  capture_take_id: string;
  slot: string;
  camera_id: string;
  registered_video_id: string;
  media_identity: Record<string, unknown>;
  timing_sidecar_identity: Record<string, unknown>;
  timing_authority: string;
  frame_count?: number | null;
  first_pts_seconds?: number | null;
  last_pts_seconds?: number | null;
}

export interface SyncAnchorValidationIssue {
  code: string;
  message: string;
  field?: string | null;
  anchor_index?: number | null;
  camera_id?: string | null;
}

export interface SyncAnchorDraft {
  reference_camera: string;
  cameras: string[];
  anchors: SyncAnchor[];
  expected_revision: number;
}

export interface SyncAnchorStatus {
  capture_take_id: string;
  state: SyncAnchorState;
  analysis_allowed: boolean;
  reason_codes: string[];
  source: SyncAnchorSource;
  revision: number;
  quality?: SyncAnchorQualitySummary | null;
  provenance: SyncAnchorProvenance[];
  provenance_fingerprint?: string | null;
  invalidation_reasons: string[];
  confirmed_at?: string | null;
  draft?: SyncAnchorDraft | null;
}

export interface SyncAnchorDraftResponse {
  capture_take_id: string;
  revision: number;
  draft: SyncAnchorDraft;
  status: SyncAnchorStatus;
}

export interface SyncAnchorConfirmResponse {
  status: SyncAnchorStatus;
  calibration: Record<string, unknown>;
  anchors: {
    reference_camera: string;
    cameras: string[];
    anchors: Array<Record<string, number>>;
  };
}
