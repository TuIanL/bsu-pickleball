import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, FileUp, GitBranch, GitCompare, Loader2, Pencil, Power, RefreshCw, Trash2, X } from "lucide-react";
import {
  compareVidatPackages, confirmVidatImport, createVidatPackage, deleteVidatPackage, deriveVidatPackage,
  getVidatServiceStatus, listVidatPackages, openVidatPackage, previewVidatImport, purgeVidatPackage,
  startVidatService, stopVidatService, updateVidatPackage, type VidatImportPreview, type VidatPackage,
  type VidatPackageComparison, type VidatServiceStatus,
} from "../../services/analysisClient";

function friendlyVidatError(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : String(reason);
  if (message.includes("PICKLEBALL_VIDAT_DIST") || message.includes("VIDAT_DIST")) {
    return "找不到 Vidat 工作目录。请先启动本机 Vidat，或配置 PICKLEBALL_VIDAT_DIR / PICKLEBALL_VIDAT_DIST 后重启后端。";
  }
  if (message.includes("标注包视频引用已失效")) {
    return "当前标注包的视频文件已不可用，请重新导出标注包。";
  }
  return message;
}

function packageLabel(packageItem: VidatPackage): string {
  const versionLabel = `第 ${packageItem.version} 版`;
  return packageItem.name === versionLabel ? versionLabel : `${packageItem.name} · ${versionLabel}`;
}

export function VidatWorkbenchPanel({ captureTakeId, onImported }: { captureTakeId: string; onImported: () => void | Promise<void> }) {
  const [packages, setPackages] = useState<VidatPackage[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [preview, setPreview] = useState<VidatImportPreview | null>(null);
  const [annotation, setAnnotation] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [ownerDraft, setOwnerDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [compareTarget, setCompareTarget] = useState("");
  const [comparison, setComparison] = useState<VidatPackageComparison | null>(null);
  const [serviceStatus, setServiceStatus] = useState<VidatServiceStatus | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const vidatWindowRef = useRef<Window | null>(null);

  const reload = useCallback(async () => {
    const next = await listVidatPackages(captureTakeId);
    setPackages(next);
    setSelected(current => next.some(item => item.id === current) ? current : next[0]?.id || "");
    setCompareTarget(current => next.some(item => item.id === current) ? current : next[1]?.id || next[0]?.id || "");
  }, [captureTakeId]);
  useEffect(() => {
    // Load the external Vidat package list when the selected Take changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes async load/error state.
    void Promise.all([reload(), getVidatServiceStatus().then(setServiceStatus)]).catch(() => setError("无法读取 Vidat 状态"));
  }, [reload]);

  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await work(); } catch (reason) { setError(friendlyVidatError(reason)); }
    finally { setBusy(false); }
  };

  const readMetadata = () => ({
    name: nameDraft.trim() || undefined,
    owner: ownerDraft.trim() || undefined,
    note: noteDraft.trim() || undefined,
  });
  const exportPackage = () => run(async () => {
    const created = await createVidatPackage(captureTakeId, readMetadata());
    await reload(); setSelected(created.id); setPreview(null); setAnnotation(null); setMetadataOpen(false);
  });
  const openPackage = () => run(async () => {
    if (!selected) return;
    const status = await startVidatService();
    setServiceStatus(status);
    if (status.status === "uncontrolled") throw new Error("Vidat 地址已被其他进程占用，平台不会停止该服务");
    const result = await openVidatPackage(selected);
    vidatWindowRef.current = window.open(result.url, "_blank", "noopener,noreferrer");
  });
  const closePackageWindow = () => {
    if (vidatWindowRef.current && !vidatWindowRef.current.closed) {
      vidatWindowRef.current.close();
      vidatWindowRef.current = null;
      return;
    }
    setError("当前 Vidat 标签页不是由平台打开，请在浏览器中手工关闭");
  };
  const derivePackage = () => run(async () => {
    if (!selected) return;
    const created = await deriveVidatPackage(selected, readMetadata());
    await reload(); setSelected(created.id); setMetadataOpen(false); setComparison(null);
  });
  const updateMetadata = () => run(async () => {
    if (!selected) return;
    const updated = await updateVidatPackage(selected, readMetadata());
    await reload(); setSelected(updated.id); setMetadataOpen(false);
  });
  const comparePackages = () => run(async () => {
    if (!selected || !compareTarget || selected === compareTarget) return;
    setComparison(await compareVidatPackages(compareTarget, selected));
  });
  const deletePackage = () => run(async () => {
    if (!selected || !window.confirm("删除后该版本会从默认列表隐藏，但审计和快照仍会保留。确定继续吗？")) return;
    await deleteVidatPackage(selected); await reload(); setComparison(null);
  });
  const purgePackage = () => run(async () => {
    if (!selected || !window.confirm("永久清理不可恢复，并会删除包文件。确定继续吗？")) return;
    await purgeVidatPackage(selected); await reload(); setComparison(null);
  });
  const stopService = () => run(async () => {
    const status = await stopVidatService();
    setServiceStatus(status);
  });
  const chooseFile = async (file?: File) => {
    if (!file || !selected) return;
    await run(async () => {
      const parsed = JSON.parse(await file.text());
      setAnnotation(parsed); setPreview(await previewVidatImport(selected, parsed));
    });
  };
  const confirm = () => run(async () => {
    if (!selected || !preview || !annotation) return;
    const result = await confirmVidatImport(selected, preview.confirmation_token, annotation);
    setPreview(null); setAnnotation(null); await reload(); setSelected(result.result_package_id); await onImported();
  });

  const current = packages.find(item => item.id === selected);
  const openMetadataEditor = () => {
    if (current) {
      setNameDraft(current.name);
      setOwnerDraft(current.owner ?? "");
      setNoteDraft(current.note ?? "");
    }
    setMetadataOpen(open => !open);
  };

  return (
    <section className="border-y border-[#DDE9D6] bg-white px-4 py-4 sm:px-5" aria-label="Vidat 视频标注工作台">
      <div className="flex flex-col gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className="text-base font-black text-[#14241B]">Vidat 视频标注</h2>
            <span className="text-xs text-slate-500">在 Vidat 中逐帧修正比赛事件</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">{current ? `${packageLabel(current)} · ${current.provenance} · ${current.imported_at ? "已导入" : "待编辑"}${current.is_active ? " · 当前投影" : ""}` : "还没有标注包，先导出一份视频标注"}</p>
          {current && <p className="mt-1 text-xs text-slate-500">负责人：{current.owner || "未指定"} · {current.note || "暂无备注"}</p>}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {packages.length > 0 && <label className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <span>选择标注包</span>
            <select aria-label="选择标注包" className="h-9 min-w-[150px] rounded-lg border border-[#D8E5D2] bg-white px-3 text-sm font-semibold text-[#203127] outline-none focus:border-[#22C55E]" value={selected} onChange={event => {
              const next = packages.find(item => item.id === event.target.value);
              setSelected(event.target.value);
              setPreview(null);
              if (next) {
                setNameDraft(next.name);
                setOwnerDraft(next.owner ?? "");
                setNoteDraft(next.note ?? "");
              }
            }}>
              {packages.map(item => <option key={item.id} value={item.id}>{packageLabel(item)}{item.imported_at ? " · 已导入" : " · 待编辑"}</option>)}
            </select>
          </label>}
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy} onClick={openMetadataEditor} type="button"><Pencil size={15} />{metadataOpen ? "收起元数据" : "填写元数据"}</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy} onClick={exportPackage} title="导出一份新的 Vidat 标注包" type="button"><RefreshCw size={15} />导出新版本</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={derivePackage} title="从当前版本派生一份新包" type="button"><GitBranch size={15} />派生版本</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={openPackage} title="在 Vidat 中打开当前标注包" type="button"><ExternalLink size={15} />打开 Vidat</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={() => inputRef.current?.click()} title="选择 Vidat 导出的 JSON 文件" type="button"><FileUp size={15} />导入标注 JSON</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={deletePackage} type="button"><Trash2 size={15} />删除版本</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={purgePackage} type="button"><Trash2 size={15} />永久清理</button>
        </div>
        <input ref={inputRef} className="hidden" type="file" accept="application/json,.json" onChange={event => void chooseFile(event.target.files?.[0])} />
        {busy && <Loader2 className="animate-spin text-slate-400" size={17} />}
      </div>
      {metadataOpen && <div className="mt-4 grid gap-2 border-t border-[#DDE9D6] pt-4 sm:grid-cols-3">
        <label className="text-xs font-semibold text-slate-500">名称<input className="mt-1 h-9 w-full rounded-lg border border-[#D8E5D2] px-2 text-sm" value={nameDraft} onChange={event => setNameDraft(event.target.value)} placeholder="第 N 版" /></label>
        <label className="text-xs font-semibold text-slate-500">负责人<input className="mt-1 h-9 w-full rounded-lg border border-[#D8E5D2] px-2 text-sm" value={ownerDraft} onChange={event => setOwnerDraft(event.target.value)} placeholder="可选" /></label>
        <label className="text-xs font-semibold text-slate-500">备注<input className="mt-1 h-9 w-full rounded-lg border border-[#D8E5D2] px-2 text-sm" value={noteDraft} onChange={event => setNoteDraft(event.target.value)} placeholder="可选" /></label>
        <div className="flex flex-wrap gap-2 sm:col-span-3">
          <button className="green-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={updateMetadata} type="button">保存当前元数据</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy} onClick={derivePackage} type="button">从当前元数据派生</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy} onClick={() => { setNameDraft(""); setOwnerDraft(""); setNoteDraft(""); }} type="button"><X size={14} />清空表单</button>
        </div>
      </div>}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#DDE9D6] pt-4 text-xs text-slate-500">
        <span>Vidat 服务：{serviceStatus?.status ?? "未知"}</span>
        <button className="quiet-button px-3 py-2 text-xs" disabled={busy} onClick={closePackageWindow} type="button"><X size={14} />关闭 Vidat 标签页</button>
        <button className="quiet-button px-3 py-2 text-xs" disabled={busy} onClick={stopService} type="button"><Power size={14} />停止 Vidat 服务</button>
      </div>
      {packages.length > 1 && <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#DDE9D6] pt-4">
        <GitCompare size={16} className="text-slate-500" />
        <span className="text-xs font-semibold text-slate-500">比较当前版本与</span>
        <select aria-label="比较版本" className="h-9 min-w-[180px] rounded-lg border border-[#D8E5D2] bg-white px-3 text-sm" value={compareTarget} onChange={event => setCompareTarget(event.target.value)}>
          {packages.filter(item => item.id !== selected).map(item => <option key={item.id} value={item.id}>{packageLabel(item)}</option>)}
        </select>
        <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !compareTarget || compareTarget === selected} onClick={comparePackages} type="button">比较版本</button>
      </div>}
      {comparison && <div className="mt-4 rounded-lg border border-[#DDE9D6] bg-[#F8FCF6] p-3 text-sm">
        <div className="flex items-center justify-between gap-2"><strong>版本差异</strong><button className="text-slate-500" onClick={() => setComparison(null)} type="button" aria-label="关闭版本差异"><X size={16} /></button></div>
        <p className="mt-1 text-xs text-slate-500">{String(comparison.before.name)} → {String(comparison.after.name)} · 变更 {comparison.changes.length} 条</p>
        <ul className="mt-2 grid gap-1 text-xs text-slate-700 sm:grid-cols-2">{comparison.changes.map((change, index) => <li key={`${change.kind}-${index}`}>{change.kind}</li>)}</ul>
      </div>}
      {error && <p className="mt-3 text-sm text-red-700" role="alert">{error}</p>}
      {preview && <div className="mt-4 border-t border-[#DDE9D6] pt-4">
        <div className="grid gap-2 text-sm sm:grid-cols-4">
          <span>变更 {preview.changes.length}</span><span>受影响回合 {preview.score_summary.affected_scores.length}</span>
          <span>最终胜者 {String(preview.score_summary.final.match_winner ?? "未决出")}</span><span>阻塞 {preview.blocking_errors.length}</span>
        </div>
        {preview.blocking_errors.length > 0 && <ul className="mt-2 text-sm text-red-700">{preview.blocking_errors.map(message => <li key={message}>{message}</li>)}</ul>}
        <button className="green-button mt-3 px-4 py-2 text-sm" disabled={busy || preview.blocking_errors.length > 0} onClick={confirm} type="button">确认导入并重建比分</button>
      </div>}
    </section>
  );
}
