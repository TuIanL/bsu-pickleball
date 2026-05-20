import type { ProgressPoint } from "../../types/report";

interface ProgressChartProps {
  points: ProgressPoint[];
}

export function ProgressChart({ points }: ProgressChartProps) {
  const maxError = Math.max(...points.map((point) => point.errors));

  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">进展追踪</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">最近 5 场表现趋势</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-600">
          当前趋势聚焦移动覆盖、回位效率和网前站位控制。
        </p>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-2xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
          <div className="flex h-56 items-end gap-3">
            {points.map((point) => (
              <div className="flex min-w-0 flex-1 flex-col items-center gap-2" key={point.match}>
                <div className="flex h-44 w-full items-end justify-center gap-1 rounded-2xl bg-white/75 px-2 py-2">
                  <span
                    className="w-2.5 rounded-full bg-[#22C55E]"
                    style={{ height: `${point.performance}%` }}
                    title={`综合表现 ${point.performance}`}
                  />
                  <span
                    className="w-2.5 rounded-full bg-[#2F80ED]"
                    style={{ height: `${point.thirdShot}%` }}
                    title={`回位效率 ${point.thirdShot}`}
                  />
                  <span
                    className="w-2.5 rounded-full bg-[#D9FF3F]"
                    style={{ height: `${point.kitchen}%` }}
                    title={`网前控制 ${point.kitchen}`}
                  />
                </div>
                <span className="text-xs font-bold text-slate-600">{point.match}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-xs font-semibold text-slate-600">
            <span className="inline-flex items-center gap-2">
              <i className="size-2 rounded-full bg-[#22C55E]" /> 综合表现
            </span>
            <span className="inline-flex items-center gap-2">
              <i className="size-2 rounded-full bg-[#2F80ED]" /> 回位效率
            </span>
            <span className="inline-flex items-center gap-2">
              <i className="size-2 rounded-full bg-[#D9FF3F]" /> 网前控制
            </span>
          </div>
        </div>

        <div className="grid gap-3">
          {points.map((point) => (
            <div className="rounded-2xl border border-[#DDE9D6] bg-white/75 p-4" key={point.match}>
              <div className="flex items-center justify-between">
                <strong>{point.match}</strong>
                <span className="text-sm font-bold text-[#168A34]">{point.performance}</span>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#DFEADA]">
                <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${point.performance}%` }} />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                失误 {point.errors}/{maxError} · 回位 {point.thirdShot}% · 网前 {point.kitchen}%
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
