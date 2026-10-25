import { z } from "zod";
import { requestJson, normalizeAnalysisJobSummary, rememberAnalysisJob, isAnalysisApiError } from "./analysisClient";
import { analysisJobSummarySchema } from "./analysisClientSchemas";
import { capabilitySchema, sourceSchema, preparedSourcesSchema, modulePlanSchema } from "../types/analysisModules";
import type { ModuleRequest, PreparedModuleSources } from "../types/analysisModules";
import type { AnalysisJobSummary, AnalysisUploadMetadata } from "../types/report";

const post = (path: string, body: unknown = {}) => requestJson<unknown>(`/api/analysis/${path}`, { method: "POST", body: JSON.stringify(body) });
export async function loadModuleCatalog() {
  const [catalog, status] = await Promise.all([
    requestJson<unknown>("/api/analysis/capabilities"), requestJson<unknown>("/api/analysis/runtime-status"),
  ]);
  return { capabilities: z.array(capabilitySchema).parse(catalog), enabled: z.object({ modular_submission_enabled: z.boolean() }).parse(status).modular_submission_enabled };
}
export async function prepareModuleVideo(videoId: string, viewId = "cam_1"): Promise<PreparedModuleSources> {
  const source = sourceSchema.parse(await post("sources/prepare", { video_id: videoId, view_id: viewId }));
  return { sources: [source], source_ids: [source.source_id], reference_view_id: source.view_id };
}
export async function prepareModuleTake(takeId: string) {
  return preparedSourcesSchema.parse(await post(`takes/${encodeURIComponent(takeId)}/sources/prepare`));
}
export async function prepareModuleModels() {
  return z.record(z.string(), z.object({ status: z.string(), missing: z.array(z.string()).optional() })).parse(await post("models/prepare"));
}
export async function previewModulePlan(request: ModuleRequest) {
  return modulePlanSchema.parse(await post("plans/preview", request));
}
export async function createModuleJob(request: ModuleRequest, metadata: AnalysisUploadMetadata, expectedPlanHash: string) {
  const value = await post("jobs", { analysisEngine: "modular_v1", modularRequest: request, metadata, expectedPlanHash });
  const job = normalizeAnalysisJobSummary(analysisJobSummarySchema.parse(value) as AnalysisJobSummary);
  rememberAnalysisJob(job);
  return job;
}
export function moduleError(error: unknown): { code?: string; message: string; uncertain: boolean } {
  if (isAnalysisApiError(error)) {
    let detail: { code?: string; details?: { implementation_id?: string } } = {};
    try { detail = JSON.parse(error.backendDetail ?? "{}"); } catch { /* Non-JSON transport error. */ }
    const messages: Record<string, string> = {
      preparation_required: `所需来源或模型尚未准备${detail.details?.implementation_id ? `：${detail.details.implementation_id}` : ""}，请检查模型环境后重新准备。`,
      authoritative_sync_required: "双摄需要有效同步确认，请前往同步工作台。",
      source_binding_stale: "来源或同步已变化，请重新准备并预览。", plan_preview_stale: "执行计划已变化，请重新准备并预览。",
      modular_submission_disabled: "当前服务已关闭专项分析创建。", capability_not_implemented: "当前服务尚未实现所选能力。",
    };
    return { code: detail.code, message: messages[detail.code ?? ""] ?? error.backendDetail ?? "连接分析服务失败，请重试。", uncertain: error.isNetworkError || (error.status ?? 0) >= 500 };
  }
  return { message: error instanceof Error ? error.message : "请求失败，请重试。", uncertain: false };
}
