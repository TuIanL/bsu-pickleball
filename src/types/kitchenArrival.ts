export type KitchenArrivalStatus =
  | "available"
  | "skipped"
  | "insufficient_evidence"
  | "not_applicable"
  | "unavailable"
  | "failed";

export interface KitchenArrivalReference {
  schema_version: "kitchen-arrival-reference.v1";
  arrival_band_m: number;
  stable_ms: number;
  arrival_min_detected_support_ms: number;
  not_arrived_min_coverage_ratio: number;
  not_arrived_max_gap_ms: number;
  min_sample_count: number;
  calibration_status?: "locked_reference" | "requires_calibration";
  provenance?: Record<string, unknown>;
}

export interface KitchenArrivalPlayerResult {
  player_id: string;
  display_name?: string | null;
  team_id: "A" | "B";
  arrived_count: number;
  eligible_count: number;
  sample_count: number;
  excluded_count: number;
  arrival_rate: number | null;
  status: KitchenArrivalStatus;
  reason?: string | null;
  rally_ids: string[];
}

export interface KitchenArrivalRallyResult {
  rally_id: string;
  ordinal: number;
  player_id: string;
  display_name?: string | null;
  team_id: "A" | "B";
  server_team: "A" | "B";
  state: "already_present" | "arrived" | "not_arrived" | "excluded";
  eligible: boolean;
  already_present: boolean;
  arrived: boolean;
  arrival_time_ms?: number | null;
  coverage_ratio?: number | null;
  max_gap_ms?: number | null;
  detected_support_ms: number;
  excluded_reason?: string | null;
  evidence_ids: string[];
  provenance: Record<string, unknown>;
}

export interface KitchenArrivalArtifact {
  schema_version: "kitchen-arrival.v1";
  job_id: string;
  video_id?: string | null;
  status: KitchenArrivalStatus;
  detail: string;
  generated_at: string;
  aggregation_scope: "match" | "formal_rally_batch";
  reference: KitchenArrivalReference;
  players: KitchenArrivalPlayerResult[];
  rallies: KitchenArrivalRallyResult[];
  diagnostics: {
    total_rallies: number;
    eligible_samples: number;
    excluded_samples: number;
    excluded_reasons: Record<string, number>;
    coverage_ratios: Record<string, number>;
    max_gaps_ms: Record<string, number>;
    warnings: string[];
  };
  source_artifacts: string[];
  provenance: Record<string, unknown>;
}
