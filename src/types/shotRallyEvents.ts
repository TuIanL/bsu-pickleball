export type CanonicalArtifactStatus =
  | "available"
  | "skipped"
  | "insufficient_evidence"
  | "not_applicable"
  | "unavailable"
  | "failed";

export type OwnershipStatus = "confirmed" | "ambiguous" | "unassigned" | "not_applicable";

export interface CanonicalEvidenceWindow {
  id: string;
  start_ms: number;
  end_ms: number;
  source_artifact: string;
  detail?: string | null;
}

export interface CanonicalPlayer {
  player_id: string;
  render_slot?: string | null;
  initial_side?: "near" | "far" | "unknown" | null;
}

export interface CanonicalShotEvent {
  shot_id: string;
  rally_id?: string | null;
  ordinal_in_rally?: number | null;
  start_ms: number;
  end_ms: number;
  contact_ms?: number | null;
  hitter_player_id?: string | null;
  team_id?: string | null;
  ownership_status: OwnershipStatus;
  ownership_confidence?: number | null;
  ownership_source?: string | null;
  stage?: "serve" | "return" | "third" | "rally_shot" | null;
  shot_type?: string | null;
  stroke_type?: string | null;
  is_volley?: boolean | null;
  result?: string | null;
  error_type?: string | null;
  quality: {
    score?: number | null;
    band: "high" | "medium" | "low" | "none";
    reasons: string[];
  };
  trajectory: {
    available: boolean;
    source?: string | null;
    segment_ids: string[];
    sample_count: number;
    path_distance_ft?: number | null;
  };
  spatial?: {
    coordinate_system: "court_ft" | "image_px";
    start_xy?: number[] | null;
    end_xy?: number[] | null;
  } | null;
  evidence_windows: CanonicalEvidenceWindow[];
  source_event_id?: string | null;
  source_artifacts: string[];
  provenance: Record<string, unknown>;
  diagnostics: string[];
}

export interface CanonicalRallyEvent {
  rally_id: string;
  ordinal: number;
  start_ms: number;
  end_ms: number;
  shot_ids: string[];
  source_artifacts: string[];
  provenance: string;
  confidence?: number | null;
  evidence_windows: CanonicalEvidenceWindow[];
}

export interface ShotRallyEventsArtifact {
  schema_version: "shot-rally-events.v1";
  job_id: string;
  video_id?: string | null;
  status: CanonicalArtifactStatus;
  detail: string;
  generated_at: string;
  time_unit: "ms";
  coordinate_system: Record<string, string>;
  players: CanonicalPlayer[];
  rallies: CanonicalRallyEvent[];
  shots: CanonicalShotEvent[];
  diagnostics: {
    duplicate_shot_ids: string[];
    missing_shot_ids: string[];
    unassigned_shot_count: number;
    ambiguous_shot_count: number;
    rally_boundary_status: "available" | "unavailable";
    warnings: string[];
  };
  source_artifacts: string[];
  provenance: Record<string, unknown>;
}

export interface MetricSnapshotEntry {
  metric_id: string;
  metric_key: string;
  scope: "match" | "team" | "player";
  subject_id: string;
  value: number | null;
  unit: string;
  numerator?: number | null;
  denominator?: number | null;
  sample_count: number;
  status: CanonicalArtifactStatus;
  reason?: string | null;
  confidence?: number | null;
  provenance: string;
  evidence_ids: string[];
  calculation_version: "product_reference_v1";
}

export interface MetricSnapshotArtifact {
  schema_version: "metric-snapshot.v1";
  job_id: string;
  video_id?: string | null;
  status: CanonicalArtifactStatus;
  detail: string;
  generated_at: string;
  product_reference_version: "product_reference_v1";
  thresholds: Record<string, number>;
  metrics: MetricSnapshotEntry[];
  source_artifact: "shot-rally-events.v1";
}
