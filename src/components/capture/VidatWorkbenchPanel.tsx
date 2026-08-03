import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, FileUp, Loader2, RefreshCw } from "lucide-react";
import {
  confirmVidatImport, createVidatPackage, listVidatPackages, openVidatPackage, startVidatService,
  previewVidatImport, type VidatImportPreview, type VidatPackage,
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

export function VidatWorkbenchPanel({ captureTakeId, onImported }: { captureTakeId: string; onImported: () => void | Promise<void> }) {
  const [packages, setPackages] = useState<VidatPackage[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [preview, setPreview] = useState<VidatImportPreview | null>(null);
  const [annotation, setAnnotation] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    const next = await listVidatPackages(captureTakeId);
    setPackages(next);
    setSelected(current => current || next[0]?.id || "");
  }, [captureTakeId]);
  useEffect(() => {
    // Load the external Vidat package list when the selected Take changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- publishes async load/error state.
    void reload().catch(() => setError("无法读取 Vidat 标注包"));
  }, [reload]);

  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await work(); } catch (reason) { setError(friendlyVidatError(reason)); }
    finally { setBusy(false); }
  };

  const exportPackage = () => run(async () => {
    const created = await createVidatPackage(captureTakeId);
    await reload(); setSelected(created.id); setPreview(null); setAnnotation(null);
  });
  const openPackage = () => run(async () => {
    if (!selected) return;
    await startVidatService();
    const result = await openVidatPackage(selected);
    window.open(result.url, "_blank", "noopener,noreferrer");
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
    await confirmVidatImport(selected, preview.confirmation_token, annotation);
    setPreview(null); setAnnotation(null); await reload(); await onImported();
  });

  const current = packages.find(item => item.id === selected);
  return (
    <section className="border-y border-[#DDE9D6] bg-white px-4 py-4 sm:px-5" aria-label="Vidat 视频标注工作台">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className="text-base font-black text-[#14241B]">Vidat 视频标注</h2>
            <span className="text-xs text-slate-500">在 Vidat 中逐帧修正比赛事件</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">{current ? `标注包 ${current.version} · ${current.imported_at ? "已导入" : "待编辑"}` : "还没有标注包，先导出一份视频标注"}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {packages.length > 0 && <label className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <span>选择标注包</span>
            <select aria-label="选择标注包" className="h-9 min-w-[150px] rounded-lg border border-[#D8E5D2] bg-white px-3 text-sm font-semibold text-[#203127] outline-none focus:border-[#22C55E]" value={selected} onChange={event => { setSelected(event.target.value); setPreview(null); }}>
              {packages.map(item => <option key={item.id} value={item.id}>第 {item.version} 版{item.imported_at ? " · 已导入" : " · 待编辑"}</option>)}
            </select>
          </label>}
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy} onClick={exportPackage} title="导出一份新的 Vidat 标注包" type="button"><RefreshCw size={15} />导出新版本</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={openPackage} title="在 Vidat 中打开当前标注包" type="button"><ExternalLink size={15} />打开 Vidat</button>
          <button className="quiet-button px-3 py-2 text-xs" disabled={busy || !selected} onClick={() => inputRef.current?.click()} title="选择 Vidat 导出的 JSON 文件" type="button"><FileUp size={15} />导入标注 JSON</button>
        </div>
        <input ref={inputRef} className="hidden" type="file" accept="application/json,.json" onChange={event => void chooseFile(event.target.files?.[0])} />
        {busy && <Loader2 className="animate-spin text-slate-400" size={17} />}
      </div>
      {error && <p className="mt-3 text-sm text-red-700" role="alert">{error}</p>}
      {preview && <div className="mt-4 border-t border-[#DDE9D6] pt-4">
        <div className="grid gap-2 text-sm sm:grid-cols-4">
          <span>变更 {preview.changes.length}</span><span>受影响回合 {preview.score_summary.affected_scores.length}</span>
          <span>最终胜者 {String(preview.score_summary.final.match_winner ?? "未决出")}</span><span>阻塞 {preview.blocking_errors.length}</span>
        </div>
        {preview.blocking_errors.length > 0 && <ul className="mt-2 text-sm text-red-700">{preview.blocking_errors.map(message => <li key={message}>{message}</li>)}</ul>}
        <button className="primary-button mt-3 px-4 py-2 text-sm" disabled={busy || preview.blocking_errors.length > 0} onClick={confirm} type="button">确认导入并重建比分</button>
      </div>}
    </section>
  );
}
