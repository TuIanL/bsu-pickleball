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
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#54FE49]">Progress Tracking</p>
          <h2 className="mt-2 text-2xl font-black text-white">最近 5 场表现趋势</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-400">
          最大进步来自接发深度，主要弱项仍是压力下的反手 dink 稳定性。
        </p>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
          <div className="flex h-56 items-end gap-3">
            {points.map((point) => (
              <div className="flex min-w-0 flex-1 flex-col items-center gap-2" key={point.match}>
                <div className="flex h-44 w-full items-end justify-center gap-1 rounded-2xl bg-white/[0.035] px-2 py-2">
                  <span
                    className="w-2.5 rounded-full bg-[#54FE49]"
                    style={{ height: `${point.performance}%` }}
                    title={`Performance ${point.performance}`}
                  />
                  <span
                    className="w-2.5 rounded-full bg-[#2F80ED]"
                    style={{ height: `${point.thirdShot}%` }}
                    title={`Third shot ${point.thirdShot}`}
                  />
                  <span
                    className="w-2.5 rounded-full bg-[#D9FF3F]"
                    style={{ height: `${point.kitchen}%` }}
                    title={`Kitchen ${point.kitchen}`}
                  />
                </div>
                <span className="text-xs font-bold text-slate-400">{point.match}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-xs font-semibold text-slate-400">
            <span className="inline-flex items-center gap-2">
              <i className="size-2 rounded-full bg-[#54FE49]" /> Performance
            </span>
            <span className="inline-flex items-center gap-2">
              <i className="size-2 rounded-full bg-[#2F80ED]" /> 3rd Shot
            </span>
            <span className="inline-flex items-center gap-2">
              <i className="size-2 rounded-full bg-[#D9FF3F]" /> Kitchen
            </span>
          </div>
        </div>

        <div className="grid gap-3">
          {points.map((point) => (
            <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-4" key={point.match}>
              <div className="flex items-center justify-between">
                <strong>{point.match}</strong>
                <span className="text-sm font-bold text-[#54FE49]">{point.performance}</span>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                <span className="block h-full rounded-full bg-[#54FE49]" style={{ width: `${point.performance}%` }} />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Errors {point.errors}/{maxError} · 3rd shot {point.thirdShot}% · Kitchen {point.kitchen}%
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
