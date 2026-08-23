import type { AnalysisPipelineResult } from "../types/report";
import { getAnalysisResult } from "./analysisClient";
import { isPipelineResult } from "./pipelineReportAdapter";

const cache = new Map<string, Promise<AnalysisPipelineResult | null>>();

export function loadAnalysisResultManifest(jobId: string): Promise<AnalysisPipelineResult | null> {
  const existing = cache.get(jobId);
  if (existing) return existing;
  const request = getAnalysisResult(jobId)
    .then((value) => (isPipelineResult(value) ? value : null))
    .catch((error) => {
      cache.delete(jobId);
      throw error;
    });
  cache.set(jobId, request);
  return request;
}

export function clearAnalysisResultManifestCache(): void {
  cache.clear();
}
