export type LandingStatus =
  | "available"
  | "no_bounce_before_next_contact"
  | "bounce_without_court_coordinate"
  | "ambiguous_bounce"
  | "unavailable";

export interface LandingProfileSnapshot {
  profile_id: string;
  parameters: Record<string, unknown>;
}

export interface ShotLanding {
  landing_id: string;
  shot_id: string;
  rally_id?: string | null;
  ordinal_in_rally?: number | null;
  bounce_event_id?: string | null;
  timestamp_ms?: number | null;
  hitter_player_id?: string | null;
  shot_stage?: string | null;
  landing_status: LandingStatus;
  landing_x_ft?: number | null;
  landing_y_ft?: number | null;
  court_location: "inside_court" | "outside_court" | "unknown";
  target_relation: "target_half" | "own_half" | "unknown";
  orientation_transform: "identity" | "rotate_180" | "unavailable";
  target_x_ft?: number | null;
  target_y_ft?: number | null;
  landing_u?: number | null;
  landing_v?: number | null;
  zone_12_id?: number | null;
  zone_12?: string | null;
  zone_6?: string | null;
  bounce_confidence?: number | null;
  geometry_quality?: number | null;
  canonicalization_basis: "hitter_position_at_contact" | "trajectory_direction" | "unavailable";
  source_segment_id?: string | null;
  source_event_id?: string | null;
  source_artifacts: string[];
  diagnostics: string[];
}

export interface ShotLandingSummary {
  shot_count: number;
  available_landing_count: number;
  formal_bounce_shot_count: number;
  spatially_measurable_count: number;
  no_bounce_before_next_contact_count: number;
  zone_eligible_count: number;
  spatial_measurability_numerator: number;
  spatial_measurability_denominator: number;
  spatial_measurability_rate?: number | null;
  zone_12_counts: Record<string, number>;
}

export interface ShotLandingsArtifact {
  schema_version: "shot-landings.v1";
  job_id: string;
  video_id?: string | null;
  status: "available" | "partial" | "unavailable" | "skipped" | "failed" | "insufficient_evidence" | "not_applicable";
  detail: string;
  generated_at: string;
  normalization_profile: LandingProfileSnapshot;
  zone_profiles: { paper_6?: LandingProfileSnapshot | null; project_12?: LandingProfileSnapshot | null };
  landings: ShotLanding[];
  summary: ShotLandingSummary;
  diagnostics?: { warnings?: string[]; missing_segment_ids?: string[]; missing_event_ids?: string[] };
  source_artifacts?: string[];
}

export function isShotLandingsArtifact(value: unknown): value is ShotLandingsArtifact {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ShotLandingsArtifact>;
  return item.schema_version === "shot-landings.v1"
    && typeof item.job_id === "string"
    && typeof item.status === "string"
    && Array.isArray(item.landings)
    && Boolean(item.summary && typeof item.summary === "object")
    && item.landings.every((landing) => Boolean(
      landing && typeof landing.shot_id === "string" && typeof landing.landing_status === "string",
    ));
}
