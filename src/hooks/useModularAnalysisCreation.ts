import { useEffect, useRef, useState } from "react";
import type { AnalysisJobSummary, AnalysisUploadMetadata } from "../types/report";
import type { ModuleDraft, ModulePlan, ModuleRequest, PreparedModuleSources } from "../types/analysisModules";
import { initialModuleDraft, moduleRequest, type AnalysisCreationMode } from "../services/analysisModeConfig";
import { createModuleJob, loadModuleCatalog, moduleError, prepareModuleModels, previewModulePlan } from "../services/analysisModuleClient";
import { listAnalysisJobs } from "../services/analysisClient";

export function useModularAnalysisCreation({ mode, sourceKey, prepare, metadata, onCreated }: {
  mode: AnalysisCreationMode; sourceKey: string; prepare: () => Promise<PreparedModuleSources>;
  metadata: AnalysisUploadMetadata; onCreated: (job: AnalysisJobSummary, sources: PreparedModuleSources) => void;
}) {
  const [catalog, setCatalog] = useState<Awaited<ReturnType<typeof loadModuleCatalog>> | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [reload, setReload] = useState(0);
  const [draft, setDraft] = useState<ModuleDraft>(initialModuleDraft);
  const [preparedState, setPrepared] = useState<{ key: string; value: PreparedModuleSources } | null>(null);
  const [models, setModels] = useState<Awaited<ReturnType<typeof prepareModuleModels>>>({});
  const [preview, setPreview] = useState<{ signature: string; plan: ModulePlan; request: ModuleRequest } | null>(null);
  const [operation, setOperation] = useState<{ scope: string; phase: string }>({ scope: "", phase: "" });
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [history, setHistory] = useState<AnalysisJobSummary[]>([]);
  const generation = useRef(0);
  const pending = useRef(false);
  const scope = `${sourceKey}:${mode}`;
  const signature = JSON.stringify([scope, draft]);
  const prepared = preparedState?.key === sourceKey ? preparedState.value : null;
  const plan = preview?.signature === signature ? preview.plan : null;
  const phase = operation.scope === scope ? operation.phase : "";
  const busy = ["preparing", "previewing", "submitting", "history"].includes(phase);

  useEffect(() => {
    let alive = true;
    loadModuleCatalog().then((result) => { if (alive) { setCatalog(result); setCatalogError(""); } })
      .catch((cause) => { if (alive) { setCatalog(null); setCatalogError(moduleError(cause).message); } });
    return () => { alive = false; };
  }, [reload]);
  useEffect(() => {
    generation.current += 1;
    pending.current = false;
    return () => { generation.current += 1; pending.current = false; };
  }, [scope]);

  function updateDraft(update: Partial<ModuleDraft>) {
    generation.current += 1;
    pending.current = false;
    setDraft((previous) => ({ ...previous, ...update }));
    setPreview(null); setError(""); setOperation({ scope, phase: "" });
  }
  async function run(nextPhase: string, action: (current: () => boolean) => Promise<void>) {
    if (pending.current) return;
    const token = ++generation.current;
    pending.current = true;
    setOperation({ scope, phase: nextPhase }); setError("");
    const current = () => generation.current === token;
    try { await action(current); }
    catch (cause) {
      if (!current()) return;
      const notice = moduleError(cause);
      setError(notice.message);
      if (nextPhase === "submitting" && draft.newVersion && notice.uncertain) {
        setUncertain(true); setError("创建请求的结果尚未确认，请先核对下方任务历史。不会自动重复创建新版本。");
      }
      if (["plan_preview_stale", "source_binding_stale", "preparation_required"].includes(notice.code ?? "")) {
        setPreview(null); setPrepared(null);
      }
    } finally {
      if (current()) { pending.current = false; setOperation({ scope, phase: "" }); }
    }
  }
  const prepareInputs = () => run("preparing", async (current) => {
    setPreview(null);
    setPrepared(null);
    const sources = await prepare();
    if (!current()) return;
    const result = await prepareModuleModels();
    if (current()) { setModels(result); setPrepared({ key: sourceKey, value: sources }); }
  });
  let request: ModuleRequest | null = null;
  let validation = "";
  if (prepared) {
    try { request = moduleRequest(mode, draft, prepared); }
    catch (cause) { validation = moduleError(cause).message; }
  }
  const targetsAvailable = Boolean(request && catalog?.enabled && request.targets.every((id) => catalog.capabilities.some((c) => c.capability_id === id && c.status === "implemented")));
  const previewPlan = () => run("previewing", async (current) => {
    if (!request || !targetsAvailable) return;
    const result = await previewModulePlan(request);
    if (!current()) return;
    const missing = result.nodes.filter((node) => models[node.implementation.implementation_id]?.status !== "prepared");
    if (missing.length) throw new Error(`所需模型未准备：${missing.map((node) => node.implementation.implementation_id).join("、")}。请检查模型环境后重新准备。`);
    setPreview({ signature, plan: result, request });
  });
  const submit = () => run("submitting", async (current) => {
    if (!plan || !preview || !prepared || uncertain) return;
    const reference = prepared.sources.find((s) => s.view_id === prepared.reference_view_id)!;
    const job = await createModuleJob(preview.request, { ...metadata, sourceFps: reference.fps,
      capture_take_id: prepared.source_binding?.take_id ?? metadata.capture_take_id,
      recording_session_id: prepared.recording_session_id ?? metadata.recording_session_id,
    }, plan.plan_hash);
    if (current()) onCreated(job, prepared);
  });
  const checkHistory = () => run("history", async (current) => {
    const jobs = await listAnalysisJobs();
    if (current()) setHistory(jobs.filter((job) => job.analysisEngine === "modular_v1" && job.planHash === preview?.plan.plan_hash));
  });
  return { catalog, catalogError, reloadCatalog: () => setReload((n) => n + 1), draft, updateDraft, prepared, plan,
    validation, error, phase, busy, uncertain, history, targetsAvailable, prepareInputs, previewPlan, submit, checkHistory,
    openHistoryJob: (job: AnalysisJobSummary) => { if (prepared) onCreated(job, prepared); },
  };
}
