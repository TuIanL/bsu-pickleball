import { z } from "zod";

export const analysisJobSummarySchema = z.object({
  id: z.string().min(1),
  status: z.enum(["uploaded", "queued", "processing", "failed", "completed", "canceled", "interrupted"]),
  stage: z.string(),
  progress: z.number().finite().min(0).max(100),
  createdAt: z.string(),
  updatedAt: z.string(),
  metadata: z.object({
    fileName: z.string(),
    matchTitle: z.string(),
    venue: z.string(),
    matchDate: z.string(),
    matchFormat: z.enum(["singles", "doubles"]),
    cameraAngle: z.string(),
    athleteLabel: z.string(),
    level: z.string(),
  }).passthrough(),
  stages: z.array(z.object({
    id: z.string(),
    label: z.string(),
    status: z.enum(["pending", "active", "done", "partial", "failed", "skipped", "unavailable", "canceled"]),
    detail: z.string(),
  }).passthrough()),
}).passthrough();

const pipelineResultSchema = z.object({
  job_id: z.string().min(1),
  status: z.enum(["completed", "failed"]),
  tracks: z.array(z.object({ track_id: z.string() }).passthrough()),
  metrics: z.object({
    distances: z.array(z.object({ track_id: z.string(), distance_ft: z.number().finite() }).passthrough()),
    speeds: z.array(z.object({
      track_id: z.string(),
      average_speed_ft_per_s: z.number().finite(),
      max_speed_ft_per_s: z.number().finite(),
    }).passthrough()),
    kitchen_dwell: z.array(z.object({
      track_id: z.string(),
      kitchen_frames: z.number().finite(),
      kitchen_seconds: z.number().finite(),
    }).passthrough()),
  }).passthrough(),
  artifacts: z.record(z.string(), z.unknown()),
}).passthrough();

export const analysisJobListSchema = z.array(analysisJobSummarySchema);
export const analysisResultSchema = z.union([analysisJobSummarySchema, pipelineResultSchema]);

export const captureTakeSummarySchema = z.object({
  id: z.string().min(1),
  field_session_id: z.string(),
  capture_mode: z.string(),
  source_session_type: z.string(),
  source_session_id: z.string(),
  status: z.string(),
  started_at: z.string(),
  ended_at: z.string().nullable().optional(),
  duration_ms: z.number().finite().nullable().optional(),
  revision: z.number().int().nonnegative(),
  video_ids: z.array(z.string()).optional(),
}).passthrough();

export class AnalysisPayloadValidationError extends Error {
  constructor(endpoint: string, issues: Array<{ path: PropertyKey[]; message: string }>) {
    const summary = issues.slice(0, 3).map((issue) => {
      const path = issue.path.map(String).join(".") || "<root>";
      return `${path}: ${issue.message}`;
    }).join("; ");
    super(`Invalid ${endpoint} payload: ${summary}`);
    this.name = "AnalysisPayloadValidationError";
  }
}

export function validateAnalysisPayload<T>(schema: z.ZodType, payload: unknown, endpoint: string): T {
  const result = schema.safeParse(payload);
  if (!result.success) {
    throw new AnalysisPayloadValidationError(endpoint, result.error.issues);
  }
  return payload as T;
}
