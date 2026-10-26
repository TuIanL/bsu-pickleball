import { useEffect, useState } from "react";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import type { AnalysisJobSummary, AnalysisNodeRun, ModularRunManifest } from "../types/report";
import { cancelAnalysisJob, getAnalysisModuleArtifact, getAnalysisModuleManifest, getAnalysisRunTrace } from "../services/analysisClient";
import { capabilityName } from "../services/analysisModeConfig";

const labels: Record<AnalysisNodeRun["status"], string> = {
  pending: "待执行", running: "执行中", cached: "已复用", completed: "已完成",
  failed: "失败", blocked: "被上游阻断", canceled: "已取消", skipped: "已跳过",
};

export function ModularAnalysisRunView({ job, onNavigate, backPath, backLabel = "返回任务管理" }: {
  job: AnalysisJobSummary; onNavigate: NavigateFn; backPath: NavigatePath; backLabel?: string;
}) {
  const [reload, setReload] = useState(0);
  const [manifest, setManifest] = useState<ModularRunManifest | null>(null);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  useEffect(() => {
    let alive = true;
    getAnalysisModuleManifest(job.id).then((value) => {
      if (alive) { setManifest(value); setError(""); }
    }).catch(() => {
      if (alive) setError("运行清单暂时不可用，请稍后重试。");
    });
    return () => { alive = false; };
  }, [job.id, job.status, job.progress, job.attempt, reload]);
  const nodes = manifest?.nodes ?? job.nodeRuns ?? [];
  const active = ["queued", "uploaded", "processing"].includes(job.status);
  const incomplete = manifest?.completeness === "partial" || manifest?.completeness === "none";
  const showArtifact = async (id: string) => {
    setBusy(true);
    try {
      const payload = await getAnalysisModuleArtifact(id);
      setDetail(JSON.stringify(payload, null, 2));
      setDetailsOpen(true);
      setError("");
    } catch {
      setError("观测产物暂时不可读，请检查存储可用性。");
    } finally { setBusy(false); }
  };
  return (
    <main className="mx-auto max-w-6xl space-y-5 p-6">
      <button type="button" className="quiet-button" onClick={() => onNavigate(backPath)}>{backLabel}</button>
      <div className="sport-card space-y-3 p-6">
        <h1 className="text-2xl font-bold">局部能力分析</h1>
        <p className="text-sm font-semibold">专项分析 · {(manifest?.targets ?? job.analysisTargets ?? []).map(capabilityName).join("、")}</p>
        <p>{job.metadata.matchTitle}</p>
        {job.clipStartMs != null && job.clipEndMs != null ? <p className="text-sm">窗口 {job.clipStartMs / 1000}–{job.clipEndMs / 1000} 秒</p> : null}
        <p className="text-sm">进度 {job.progress}% · {active ? "正在执行" : job.status === "completed" ? "执行完成" : job.status === "failed" ? "执行失败" : job.status === "interrupted" ? "任务失联" : "已取消"}</p>
        {incomplete && !active ? <p role="status" className="text-[var(--ui-warning)]">部分目标未完成，已保留的产物仍可查看。</p> : null}
        {manifest ? <p className="text-sm">结果完整性：{({ complete: "全部目标完成", partial: "部分目标完成", none: "尚无已完成目标" })[manifest.completeness]}</p> : null}
        {error ? <div role="alert"><p>{error}</p><button type="button" className="quiet-button mt-2" onClick={() => setReload((n) => n + 1)}>重试读取清单</button></div> : null}
        {active ? <button type="button" className="quiet-button" onClick={() => {
          void cancelAnalysisJob(job.id).then(() => setError("已提交取消请求，等待安全检查点退出。")).catch(() => setError("取消请求未成功，请重试。"));
        }}>取消分析</button> : null}
      </div>
      <section className="sport-card p-6" aria-label="能力执行状态">
        <h2 className="mb-4 text-lg font-bold">请求能力与计算结果</h2>
        <ul className="space-y-4">
          {nodes.map((node) => (
            <li key={node.node_key} className="rounded-xl border border-[var(--ui-border)] p-4">
              <strong>{capabilityName(node.capability_id)}</strong> · {labels[node.status]}
              <p className="mt-1 text-xs text-slate-500">{(manifest?.targets ?? job.analysisTargets)?.includes(node.capability_id) ? "所选目标" : (manifest?.targets ?? job.analysisTargets) ? "自动加入的依赖" : "正在读取目标信息"}</p>
              {node.artifact ? <ArtifactQuality manifest={manifest} artifactId={node.artifact.artifact_id} /> : null}
              {node.node_attempt > 0 ? <span> · 节点尝试 {node.node_attempt}</span> : null}
              {node.message ? <p className="mt-2 text-sm">{node.message}</p> : null}
              {node.error_code ? <p className="mt-1 text-xs">{node.error_code}</p> : null}
              {node.artifact ? <button type="button" className="quiet-button mt-2" disabled={busy}
                onClick={() => void showArtifact(node.artifact!.artifact_id)}>查看观测产物</button> : null}
              <details className="mt-2 text-sm"><summary>执行计数与实现详情</summary>
                <p className="my-2 text-xs">{node.capability_id} · {node.implementation_id} · v{node.implementation_version} · 配置 {node.configuration_digest?.slice(0, 12)}</p>
                <pre className="overflow-auto">{JSON.stringify(node.counters, null, 2)}</pre>
              </details>
            </li>
          ))}
        </ul>
      </section>
      <details className="sport-card p-6" open={detailsOpen} onToggle={(event) => setDetailsOpen(event.currentTarget.open)}>
        <summary>技术详情</summary>
        <p className="my-2 break-all text-xs">计划：{job.planId} · 指纹：{job.planHash}</p>
        <button type="button" className="quiet-button" onClick={() => {
          void getAnalysisRunTrace(job.id).then((trace) => setDetail(JSON.stringify(trace, null, 2))).catch(() => setError("运行轨迹暂时不可用。"));
        }}>读取运行轨迹</button>
        {detail ? <><pre className="mt-3 max-h-96 overflow-auto text-xs">{detail.slice(0, 40000)}</pre>{detail.length > 40000 ? <p>当前显示前 40000 个字符。</p> : null}</> : null}
      </details>
    </main>
  );
}

function ArtifactQuality({ manifest, artifactId }: { manifest: ModularRunManifest | null; artifactId: string }) {
  const detail = manifest?.artifact_details?.find((item) => item.manifest.ref.artifact_id === artifactId);
  if (!detail) return null;
  const quality: Record<string, string> = { sufficient: "证据充分", no_candidates: "执行完成，未检测到候选", insufficient_evidence: "证据不足", truncated: "片段边界已截断" };
  const availability: Record<string, string> = { available: "产物可读取", location_unavailable: "存储暂不可用", missing: "产物缺失", corrupt: "产物校验失败" };
  return <p className="mt-2 text-sm" role="status">{quality[detail.manifest.quality] ?? detail.manifest.quality} · {availability[detail.availability] ?? detail.availability}</p>;
}
