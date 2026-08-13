export type ObservabilityAvailability = "available" | "partial" | "unavailable" | "not_applicable";

export type RecoveryOutcome =
  | "guided_recovery_success"
  | "base_recovered"
  | "guidance_failed"
  | "pre_gate_rejected"
  | "lock_rejected"
  | "global_mismatch";

export interface ObservabilitySection<T = unknown> {
  availability: ObservabilityAvailability;
  status: string;
  reason_code?: string;
  data?: T;
}

export interface SyncObservabilityData {
  reference_view?: string | null;
  per_view_authority?: Record<string, string> | null;
  timing_provenance?: Record<string, unknown> | null;
  sync_quality?: string | null;
  execution_mode?: string | null;
  authoritative_joint_eligible?: boolean | null;
  authority_reason?: string | null;
  authority_reason_codes?: string[] | null;
  selection_error?: unknown;
  frame_selection_status?: unknown;
}

export interface FusionObservabilityData {
  status_counts?: Record<string, number> | null;
  sample_count?: number | null;
  metric_eligible_count?: number | null;
  view_disagreement?: Record<string, number | null> | null;
  effective_multiview_ratio?: number | null;
}

export interface RecoveryFunnel {
  [key: string]: number | undefined;
}

export interface RecoveryObservabilityData {
  funnel?: RecoveryFunnel | null;
  episode_availability?: ObservabilityAvailability;
  episode_reason?: { code: string; message: string } | null;
}

export interface RefinementObservabilityData {
  execution_status?: string;
  candidate_f1?: { available: boolean; artifact?: string | null };
  publication_decision?: string;
  safety_gate?: { reason?: string | null; metrics?: Record<string, unknown> };
  final_source?: "refined_f1" | "first_pass_f0" | null;
}

export interface DebugObservabilityData {
  debug_trace_enabled?: boolean;
  video_available?: boolean;
  video_filename?: string;
  summary?: Record<string, unknown> | null;
}

export interface MultiviewObservabilitySummary {
  schema_version: "multiview_observability_summary.v1" | string;
  job_id: string;
  run_id?: string | null;
  analysis_kind: string;
  requested_mode?: string | null;
  execution_mode?: string | null;
  effective_mode?: string | null;
  sections: {
    sync: ObservabilitySection<SyncObservabilityData>;
    fusion: ObservabilitySection<FusionObservabilityData>;
    recovery: ObservabilitySection<RecoveryObservabilityData>;
    refinement: ObservabilitySection<RefinementObservabilityData>;
    debug: ObservabilitySection<DebugObservabilityData>;
  };
}

export interface RecoveryEpisode {
  recovery_episode_id: string;
  start_ms: number;
  end_ms: number;
  global_player_id?: string | null;
  donor_view?: string | null;
  target_view?: string | null;
  outcome: RecoveryOutcome;
  guidance_attempts: number;
  pre_gate_rejections: number;
  lock_rejections: number;
  debug_video_seek_ms?: number | null;
}

export interface RecoveryEpisodePage {
  items: RecoveryEpisode[];
  next_cursor?: string | null;
  total_estimate: number;
  availability?: ObservabilityAvailability;
  reason?: { code: string; message: string };
}

export interface MultiviewStructuredError {
  error?: { code?: string; message?: string; job_id?: string };
}
