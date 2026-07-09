import { useState } from "react";
import type { ProgressPoint } from "../../types/report";

interface ProgressChartProps {
  points: ProgressPoint[];
}

const BAR_COLORS = {
  performance: "#22C55E",
  thirdShot: "#2F80ED",
  kitchen: "#D9FF3F",
} as const;

type BarKey = keyof typeof BAR_COLORS;

const BAR_LABELS: Record<BarKey, string> = {
  performance: "综合表现",
  thirdShot: "回位效率",
  kitchen: "网前控制",
};

export function ProgressChart({ points }: ProgressChartProps) {
  const [hoveredMatch, setHoveredMatch] = useState<string | null>(null);
  const [hoveredBar, setHoveredBar] = useState<BarKey | null>(null);
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
            {points.map((point) => {
              const isHovered = hoveredMatch === point.match;
              return (
                <div
                  className="flex min-w-0 flex-1 flex-col items-center gap-1"
                  key={point.match}
                  onMouseEnter={() => setHoveredMatch(point.match)}
                  onMouseLeave={() => { setHoveredMatch(null); setHoveredBar(null); }}
                >
                  <div className="flex h-44 w-full items-end justify-center gap-1 rounded-2xl bg-white/75 px-2 py-2">
                    {(["performance", "thirdShot", "kitchen"] as BarKey[]).map((key) => {
                      const barHovered = isHovered && hoveredBar === key;
                      return (
                        <div key={key} className="relative flex flex-col items-center">
                          {isHovered && (
                            <span className="absolute -top-5 whitespace-nowrap text-[10px] font-bold text-[#14241B]">
                              {point[key]}
                            </span>
                          )}
                          <span
                            className={`rounded-full transition-all duration-200 ${barHovered ? "" : ""}`}
                            style={{
                              width: barHovered ? 6 : 3,
                              height: `${point[key]}%`,
                              backgroundColor: BAR_COLORS[key],
                              minHeight: 4,
                            }}
                            onMouseEnter={(e) => { e.stopPropagation(); setHoveredBar(key); }}
                            onMouseLeave={() => setHoveredBar(null)}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <span className="text-xs font-bold text-slate-600">{point.match}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-xs font-semibold text-slate-600">
            {(["performance", "thirdShot", "kitchen"] as BarKey[]).map((key) => (
              <span key={key} className="inline-flex items-center gap-2">
                <i className="size-2 rounded-full" style={{ backgroundColor: BAR_COLORS[key] }} /> {BAR_LABELS[key]}
              </span>
            ))}
          </div>
        </div>

        <div className="grid gap-3">
          {points.map((point) => (
            <div
              className={`rounded-2xl border bg-white/75 p-4 transition-all duration-200 ${
                hoveredMatch === point.match ? "border-[#22C55E] shadow-sm" : "border-[#DDE9D6]"
              }`}
              key={point.match}
              onMouseEnter={() => setHoveredMatch(point.match)}
              onMouseLeave={() => setHoveredMatch(null)}
            >
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
