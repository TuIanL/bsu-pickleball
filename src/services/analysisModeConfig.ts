import type { ModuleDraft, ModuleRequest, PreparedModuleSources } from "../types/analysisModules";

export const analysisModes = [
  { id: "full", label: "完整比赛分析", description: "场地标定、球员追踪与比赛报告" },
  { id: "player", label: "球员检测", description: "检测画面中的人员，不确认持续身份" },
  { id: "ball", label: "球检测", description: "逐机位二维球观测，不生成三维球路" },
  { id: "pose", label: "姿态分析", description: "自动加入球员检测，分析人体姿态" },
  { id: "custom", label: "自定义组合", description: "组合已开放能力，按依赖执行" },
] as const;
export type AnalysisCreationMode = typeof analysisModes[number]["id"];
export const capabilityNames: Record<string, string> = { "player.detect": "球员检测", "ball.detect": "球检测", "pose.sequence": "姿态分析" };
export const capabilityName = (id: string) => capabilityNames[id] ?? id;
export function readAnalysisMode(): AnalysisCreationMode {
  const value = new URLSearchParams(window.location.search).get("analysisMode");
  return analysisModes.find((mode) => mode.id === value)?.id ?? "full";
}
export function modeTargets(mode: AnalysisCreationMode, custom: string[]): string[] {
  return mode === "custom" ? [...new Set(custom)].sort() : mode === "full" ? [] : [{ player: "player.detect", ball: "ball.detect", pose: "pose.sequence" }[mode]];
}
export function initialModuleDraft(): ModuleDraft {
  const params = new URLSearchParams(window.location.search);
  const finite = (key: string, fallback: number) => params.has(key) && Number.isFinite(Number(params.get(key))) ? Number(params.get(key)) : fallback;
  return { targets: (params.get("targets")?.split(",") ?? ["ball.detect"]).filter((id) => id in capabilityNames),
    start: finite("start", 0), end: params.has("end") ? finite("end", 30) : null,
    stride: finite("stride", 2), failurePolicy: "all_targets", newVersion: false };
}
export function moduleRequest(mode: AnalysisCreationMode, draft: ModuleDraft, prepared: PreparedModuleSources): ModuleRequest {
  const reference = prepared.sources.find((s) => s.view_id === prepared.reference_view_id);
  if (!reference) throw new Error("参考视频不可用，请重新准备。");
  const start_ms = Math.round(draft.start * 1000);
  const end_ms = draft.end === null ? Math.min(30000, reference.duration_ms) : Math.round(draft.end * 1000);
  if (!Number.isFinite(start_ms) || !Number.isFinite(end_ms) || start_ms < 0 || end_ms <= start_ms || end_ms > reference.duration_ms) {
    throw new Error("请选择有效片段：开始时间不得小于 0，结束时间须大于开始时间且不超过视频时长。");
  }
  if (!Number.isInteger(draft.stride) || draft.stride < 1) throw new Error("采样步长必须为正整数。");
  const targets = modeTargets(mode, draft.targets);
  if (!targets.length || targets.some((id) => !(id in capabilityNames))) throw new Error("请至少选择一项已开放能力。");
  return { source_ids: prepared.source_ids, targets, window: { start_ms, end_ms }, sampling: { stride: draft.stride },
    failure_policy: draft.failurePolicy, reference_view_id: prepared.reference_view_id, sync: prepared.sync,
    source_binding: prepared.source_binding, new_version: draft.newVersion };
}
export function moduleDraftReturn(mode: AnalysisCreationMode, draft: ModuleDraft): string {
  const url = new URL(window.location.href);
  url.searchParams.set("analysisMode", mode);
  url.searchParams.set("targets", draft.targets.join(","));
  url.searchParams.set("start", String(draft.start));
  if (draft.end !== null) url.searchParams.set("end", String(draft.end));
  else url.searchParams.delete("end");
  url.searchParams.set("stride", String(draft.stride));
  return url.pathname + url.search;
}
