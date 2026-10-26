import { analysisModes, type AnalysisCreationMode } from "../../services/analysisModeConfig";

export function AnalysisModeSelector({ value, onChange }: { value: AnalysisCreationMode; onChange: (mode: AnalysisCreationMode) => void }) {
  return <section className="sport-card my-5 p-4" aria-label="分析模式">
    <h2 className="text-lg font-bold">选择分析模式</h2>
    <p className="mt-1 text-sm text-slate-500">按这次想查看的内容创建分析，专项分析可只运行一个视频片段。</p>
    <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {analysisModes.map((mode) => <button key={mode.id} type="button" aria-pressed={value === mode.id} onClick={() => onChange(mode.id)}
        className={`rounded-2xl border p-3 text-left ${value === mode.id ? "border-[var(--ui-brand)] bg-[var(--ui-brand-selection-bg)]" : "border-[var(--ui-border)]"}`}>
        <strong className="block text-sm">{mode.label}</strong><span className="mt-1 block text-xs leading-5 text-slate-500">{mode.description}</span>
      </button>)}
    </div>
  </section>;
}
