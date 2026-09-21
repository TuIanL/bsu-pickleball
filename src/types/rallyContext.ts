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
  canonical_player_id: string;
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

export interface BootstrapBindingAuditEntry {
  canonical_player_id: string;
  bootstrap_run_id?: string | null;
  source_view_id?: string | null;
  anchor_timestamp_ms: number;
  anchor_court_xy?: number[] | null;
  formal_canonical_player_id?: string | null;
  method: BootstrapBindingMethod;
  confidence?: number | null;
  confirmed: boolean;
  reason?: string | null;
}

export interface BootstrapBindingAudit {
  schema_version: "bootstrap-binding-audit.v1";
  job_id: string;
  roster_hash: string;
  status: "available" | "partial" | "unavailable";
  unavailable_reason?: string | null;
  entries: BootstrapBindingAuditEntry[];
}
