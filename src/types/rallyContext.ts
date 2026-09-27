/**
 * 分析名册与分析回合上下文的前端类型契约。
 *
 * 与后端 `backend/app/schemas/rally_context.py` 一一对应。关键语义约束：
 * - `RallyScoringSnapshotPayload` 是**纯计分事实**，不含 P1–P4、队伍或端位。
 * - 正式 Team A/B 只能来自 `AnalysisRallyContextRally`；`initial_side` 只是物理半场诊断。
 * - 拿不到上下文时必须显式 unavailable，不得推断。
 */

/** 场地端位：产品语义（A 端 / B 端），不是 near/far 物理半场。 */
export type CourtEnd = "end_a" | "end_b";
export type RosterTeamId = "A" | "B";
export type RosterSnapshotStatus = "available" | "skipped" | "insufficient_candidates" | "unavailable";
export type BootstrapBindingMethod =
  | "anchor_simultaneous_match"
  | "anchor_simultaneous_multiview"
  | "anchor_reacquire"
  | "partial_reacquire"
  | "temporal_fallback"
  | "unavailable";
export type ContextBindingMethod =
  | "direct_segment_link"
  | "direct_start_event_link"
  | "unique_temporal_match"
  | "unavailable";

export interface PlayerBootstrapCandidate {
  canonical_player_id: string;
  display_name?: string | null;
  anchor_timestamp_ms: number;
  anchor_bbox?: number[] | null;
  anchor_court_xy?: number[] | null;
  confidence?: number | null;
}

/* ── bootstrap v2：自动候选预检契约 ──
 *
 * v1 的 `canonical_player_id` 把「预检候选身份」与「正式 Player_N」混在一起。
 * v2 显式拆开三层：`candidate_id`（预检运行内稳定）／P 槽位（用户确认的展示位）／
 * 正式身份（只由后端绑定审计产出）。
 */
export interface PlayerBootstrapCandidateEvidence {
  target_court_membership?: number | null;
  target_court_occupancy?: number | null;
  mean_target_court_distance_ft?: number | null;
  continuity?: number | null;
  coverage_ratio?: number | null;
  sampled_hits: number;
  sampled_frames: number;
  body_crop_quality?: number | null;
  appearance_quality?: number | null;
  appearance_margin?: number | null;
  multiview_agreement?: number | null;
}

export interface PlayerBootstrapCandidateV2 {
  candidate_id: string;
  suggested_slot?: number | null;
  view_id: string;
  timestamp_ms: number;
  bbox: number[];
  frame_url?: string | null;
  crop_url?: string | null;
  court_xy?: number[] | null;
  confidence?: number | null;
  score?: number | null;
  source_views: string[];
  evidence: PlayerBootstrapCandidateEvidence;
}

export interface PlayerBootstrapReferenceFrame {
  view_id: string;
  timestamp_ms: number;
  frame_url?: string | null;
  candidate_ids: string[];
  /** candidate_id → 该帧**实际观测到**的框；不同时刻的框绝不混画在同一帧上。 */
  observed_bboxes: Record<string, number[]>;
}

export interface PlayerBootstrapResultV2 {
  schema_version: "player-bootstrap.v2";
  status: "available" | "insufficient_candidates" | "unavailable";
  unavailable_reason?: string | null;
  owner_key: string;
  capture_take_id?: string | null;
  video_id?: string | null;
  video_id_b?: string | null;
  match_format?: string | null;
  expected_player_count: number;
  clip_start_ms: number;
  clip_end_ms?: number | null;
  bootstrap_run_id?: string | null;
  bootstrap_model_version?: string | null;
  bootstrap_cache_key?: string | null;
  views: string[];
  multiview_used: boolean;
  sampled_frame_count: number;
  reference_frame?: PlayerBootstrapReferenceFrame | null;
  candidates: PlayerBootstrapCandidateV2[];
  diagnostics: PlayerBootstrapQualityDiagnostic[];
  skippable: boolean;
  consumers_enabled?: boolean;
}

/** 预检响应：新版确认页消费 v2，遇到旧后端时降级读取 v1。 */
export type PlayerBootstrapResponse = PlayerBootstrapResultV2 | PlayerBootstrapResult;

export function isBootstrapV2(
  result: PlayerBootstrapResponse | null | undefined,
): result is PlayerBootstrapResultV2 {
  return !!result && result.schema_version === "player-bootstrap.v2";
}

export interface PlayerBootstrapQualityDiagnostic {
  code: string;
  detail?: string;
  severity: "info" | "warning" | "blocking";
}

export interface PlayerBootstrapResult {
  schema_version: "player-bootstrap.v1";
  status: "available" | "insufficient_candidates" | "unavailable";
  unavailable_reason?: string | null;
  owner_key: string;
  capture_take_id?: string | null;
  video_id?: string | null;
  bootstrap_run_id?: string | null;
  bootstrap_model_version?: string | null;
  reference_timestamp_ms: number;
  reference_frame_url?: string | null;
  candidates: PlayerBootstrapCandidate[];
  diagnostics: PlayerBootstrapQualityDiagnostic[];
  /** 始终为 true：跳过确认不影响普通分析创建。 */
  skippable: boolean;
  /**
   * 后端 `rally_context_enabled` 的镜像。部署级关闭时提交名册/端位不会冻结任何上下文，
   * 前端据此把本步骤降级为"仅提示"，避免用户误以为已经冻结名册。
   */
  consumers_enabled?: boolean;
}

export interface AnalysisRosterConfirmationEntry {
  /** 用户确认的 P 槽位（`Player_1`..`Player_4`），不是正式追踪身份。 */
  canonical_player_id: string;
  /** 该槽位对应的预检候选；手工框选时为 null。 */
  candidate_id?: string | null;
  slot_index?: number | null;
  display_name?: string | null;
  team_id?: RosterTeamId | null;
  source_view_id?: string | null;
  anchor_timestamp_ms: number;
  anchor_bbox?: number[] | null;
  anchor_court_xy?: number[] | null;
  bootstrap_run_id?: string | null;
  bootstrap_model_version?: string | null;
  bootstrap_confidence?: number | null;
}

/** 前端在创建 Job 时提交的名册/端位确认（可为跳过）。 */
export interface RosterConfirmationRequest {
  skipped: boolean;
  initial_team_a_end?: CourtEnd | null;
  entries: AnalysisRosterConfirmationEntry[];
  bootstrap_run_id?: string | null;
  bootstrap_model_version?: string | null;
}

export interface ContextBinding {
  method: ContextBindingMethod;
  source_segment_id?: string | null;
  source_start_event_id?: string | null;
  candidate_count: number;
  diagnostics: string[];
}

export interface AnalysisRallyContextRally {
  rally_id: string;
  ordinal: number;
  start_ms: number;
  end_ms?: number | null;
  status: "available" | "partial" | "unavailable";
  unavailable_reason?: string | null;
  scoring_snapshot_id?: string | null;
  scoring_hash?: string | null;
  start_event_id?: string | null;
  server_team?: RosterTeamId | null;
  score_a_before?: number | null;
  score_b_before?: number | null;
  team_a_end?: CourtEnd | null;
  team_b_end?: CourtEnd | null;
  team_a_players: string[];
  team_b_players: string[];
  binding: ContextBinding;
  context_hash?: string | null;
}

export interface BootstrapBindingEvidence {
  view_id?: string | null;
  time_delta_ms?: number | null;
  bbox_iou?: number | null;
  bbox_center_distance_px?: number | null;
  court_distance_ft?: number | null;
  appearance_distance?: number | null;
  multiview_corroborated?: boolean | null;
  competing_formal_players: number;
  competing_slots: number;
}

export interface BootstrapBindingAuditEntry {
  /** 用户确认的 P 槽位。 */
  canonical_player_id: string;
  slot_index?: number | null;
  candidate_id?: string | null;
  bootstrap_run_id?: string | null;
  source_view_id?: string | null;
  anchor_timestamp_ms: number;
  anchor_bbox?: number[] | null;
  anchor_court_xy?: number[] | null;
  /** 经同时刻证据唯一匹配到的正式球员；未确认时为 null。 */
  formal_canonical_player_id?: string | null;
  method: BootstrapBindingMethod;
  confidence?: number | null;
  confirmed: boolean;
  reason?: string | null;
  evidence?: BootstrapBindingEvidence;
}

export interface BootstrapBindingAudit {
  schema_version: "bootstrap-binding-audit.v1";
  job_id: string;
  roster_hash: string;
  status: "available" | "partial" | "unavailable";
  unavailable_reason?: string | null;
  entries: BootstrapBindingAuditEntry[];
}
