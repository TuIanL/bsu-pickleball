import { z } from "zod";

export const capabilitySchema = z.object({
  capability_id: z.string(), status: z.enum(["planned", "implemented"]), implementations: z.array(z.string()),
});
export type AnalysisCapability = z.infer<typeof capabilitySchema>;
export const sourceSchema = z.object({
  source_id: z.string(), video_id: z.string().nullable(), view_id: z.string(), camera_id: z.string(),
  duration_ms: z.number().positive(), fps: z.number().positive(), width: z.number(), height: z.number(),
  timing_authority: z.enum(["source_pts", "legacy_nominal_fps"]),
});
export type ModuleSource = z.infer<typeof sourceSchema>;
export const sourceBindingSchema = z.object({ take_id: z.string(), sync_revision: z.number().int(), provenance_fingerprint: z.string() });
export const preparedSourcesSchema = z.object({
  source_ids: z.array(z.string()).min(1), sources: z.array(sourceSchema).min(1), reference_view_id: z.string(),
  sync: z.record(z.string(), z.unknown()).optional(), source_binding: sourceBindingSchema.optional(),
  recording_session_id: z.string().optional(),
});
export type PreparedModuleSources = z.infer<typeof preparedSourcesSchema>;
const windowSchema = z.object({ start_ms: z.number().int(), end_ms: z.number().int() });
export const modulePlanSchema = z.object({
  plan_id: z.string(), plan_hash: z.string(), targets: z.array(z.string()), requested_window: windowSchema,
  sampling: z.object({ stride: z.number(), phase: z.number() }), failure_policy: z.enum(["all_targets", "best_effort"]),
  nodes: z.array(z.object({
    node_key: z.string(), capability_id: z.string(),
    implementation: z.object({ implementation_id: z.string(), resources: z.array(z.string()) }),
    parameters: z.record(z.string(), z.unknown()), effective_window: windowSchema,
    compute_window: windowSchema, truncated: z.boolean(),
  })), cache_hints: z.record(z.string(), z.unknown()),
});
export type ModulePlan = z.infer<typeof modulePlanSchema>;
export interface ModuleRequest {
  source_ids: string[]; targets: string[]; window: { start_ms: number; end_ms: number };
  sampling: { stride: number }; failure_policy: "all_targets" | "best_effort";
  reference_view_id: string; sync?: Record<string, unknown>;
  source_binding?: z.infer<typeof sourceBindingSchema>; new_version: boolean;
}
export interface ModuleDraft {
  targets: string[]; start: number; end: number | null; stride: number;
  failurePolicy: ModuleRequest["failure_policy"]; newVersion: boolean;
}
