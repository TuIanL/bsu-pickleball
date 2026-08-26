export type MetricDirection =
  | "higher_better"
  | "lower_better"
  | "target_range"
  | "context_dependent"
  | "descriptive_only";

export type ReferenceMode = "expert_threshold" | "target_range" | "empirical_percentile";

export type ScoreEligibility =
  | "eligible"
  | "display_only"
  | "insufficient_evidence"
  | "not_applicable"
  | "unsupported"
  | "failed";

export type MatchFormat = "singles" | "doubles";
export type MetricScope = "match" | "team" | "player";

export interface MetricDefinition {
  metric_key: string;
  unit: string;
  source_metric_key: string;
  scopes: MetricScope[];
  match_formats: MatchFormat[];
  metric_direction: MetricDirection;
  descriptive_only: boolean;
  required_semantic_level: "descriptive" | "derived" | "confirmed" | "candidate";
  min_sample_count: number;
  min_denominator?: number | null;
  context_keys: string[];
  definition_detail?: string | null;
}

export interface MetricDefinitionProfile {
  schema_version: "metric-definition-profile.v1";
  profile_version: string;
  metrics: MetricDefinition[];
}

export interface SufficiencyRule {
  min_sample_count: number;
  min_denominator?: number | null;
  min_coverage?: number | null;
  zero_denominator_status: "not_applicable" | "insufficient_evidence";
}

export interface EvidenceSufficiencyProfile {
  schema_version: "evidence-sufficiency-profile.v1";
  profile_version: string;
  default_rule: SufficiencyRule;
  rules: Record<string, SufficiencyRule>;
}

export interface MetricReference {
  metric_key: string;
  reference_mode: ReferenceMode;
  metric_direction: MetricDirection;
  reference_source: string;
  reference_detail: string;
  lower_bound?: number | null;
  upper_bound?: number | null;
  target_min?: number | null;
  target_max?: number | null;
  context_selector: Record<string, string>;
  population?: string | null;
  cohort?: string | null;
  population_sample_count?: number | null;
  reference_distribution: number[];
  fallback: "none" | "display_only" | "unsupported";
}

export interface ScoringReferenceProfile {
  schema_version: "scoring-reference-profile.v1";
  reference_version: string;
  reference_mode: ReferenceMode;
  reference_source: string;
  reference_detail: string;
  metrics: MetricReference[];
  generated_at?: string | null;
}

export interface NormalizedMetricEntry {
  metric_id: string;
  source_metric_id: string;
  metric_key: string;
  scope: MetricScope;
  subject_id: string;
  source_status: string;
  raw_value: number | null;
  canonical_value: number | null;
  unit: string;
  metric_direction: MetricDirection;
  reference_mode?: ReferenceMode | null;
  utility_score?: number | null;
  percentile?: number | null;
  numerator?: number | null;
  denominator?: number | null;
  sample_count: number;
  confidence?: number | null;
  score_eligibility: ScoreEligibility;
  eligibility_reasons: string[];
  provenance: string;
  source_artifact: "metric-snapshot.v1";
  evidence_ids: string[];
  definition_version: string;
  evidence_sufficiency_version: string;
  reference_version?: string | null;
  calculation_version: "metric-normalization.v1";
}

export interface NormalizedMetricCoverage {
  metric_count: number;
  eligible_metric_count: number;
  display_only_metric_count: number;
  insufficient_metric_count: number;
  not_applicable_metric_count: number;
  unsupported_metric_count: number;
  failed_metric_count: number;
  eligible_metric_keys: string[];
  missing_metric_keys: string[];
}

export interface NormalizedMetricArtifact {
  schema_version: "normalized-metric-snapshot.v1";
  job_id: string;
  video_id?: string | null;
  status: string;
  detail: string;
  generated_at: string;
  input_artifact: "metric-snapshot.v1";
  metric_definition_version: string;
  evidence_sufficiency_version: string;
  scoring_reference_version?: string | null;
  scoring_reference_hash?: string | null;
  metrics: NormalizedMetricEntry[];
  score_coverage: NormalizedMetricCoverage;
  diagnostics: string[];
}
