import { AlertTriangle, Footprints, Gauge } from "lucide-react";
import type {
  Diagnosis,
  MovementPoint,
  ReportDefinition,
} from "../../types/report";

interface ReportVisualizationProps {
  definition: ReportDefinition;
  diagnoses: Diagnosis[];
  movementPath: MovementPoint[];
}

const iconMap = {
  movement: Footprints,
  diagnosis: AlertTriangle,
  performance: Gauge,
};

const COURT = {
  ox: 120, oy: 60, w: 760, h: 600,
  cx: 500,
  netY: 360,
  kitchenTopY: 280,
  kitchenBottomY: 440,
  toSvgY: (y: number) => y * 6.4 + 60,
};

function gridLines() {
  const lines: { x1: number; y1: number; x2: number; y2: number }[] = [];
  for (let i = 1; i < 10; i++) {
    if (i === 5) continue;
    const y = COURT.oy + (i / 10) * COURT.h;
    lines.push({ x1: COURT.ox, y1: y, x2: COURT.ox + COURT.w, y2: y });
  }
  for (let i = 1; i < 4; i++) {
    const x = COURT.ox + (i / 4) * COURT.w;
    lines.push({ x1: x, y1: COURT.oy, x2: x, y2: COURT.oy + COURT.h });
  }
  return lines;
}

export function ReportVisualization({
  definition,
  diagnoses,
  movementPath,
}: ReportVisualizationProps) {
  const Icon = iconMap[definition.visualization];
  const movementPolyline = movementPath
    .map((p) => `${p.x * 10},${COURT.toSvgY(p.y)}`)
    .join(" ");

  const firstPt = movementPath.length > 0 ? movementPath[0] : null;
  const lastPt = movementPath.length > 1 ? movementPath[movementPath.length - 1] : null;

  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Icon size={15} aria-hidden="true" />
            {definition.eyebrow}
          </p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">核心可视化</h2>
        </div>
        <p className="max-w-2xl text-sm leading-6 text-slate-600">{definition.summary}</p>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="relative rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
          {definition.visualization === "diagnosis" ? (
            <div className="grid gap-3">
              {diagnoses.map((diagnosis) => (
                <article className="rounded-2xl border border-[#DDE9D6] bg-white/75 p-4" key={diagnosis.id}>
                  <div className="flex items-center justify-between gap-3">
                    <strong className="text-[#14241B]">{diagnosis.issue}</strong>
                    <span className="rounded-full border border-[#FF9500]/30 bg-[#FF9500]/12 px-2 py-1 text-xs font-black text-[#A45A00]">
                      {diagnosis.severity}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{diagnosis.evidence}</p>
                  <p className="mt-3 rounded-2xl bg-[#22C55E]/12 p-3 text-sm font-semibold leading-6 text-[#168A34]">
                    {diagnosis.suggestion}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <>
              <svg className="aspect-[16/11] w-full" viewBox="0 0 1000 720" aria-label={`${definition.title}可视化`}>
                <defs>
                  <linearGradient id="trailGrad" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#86EFAC" />
                    <stop offset="100%" stopColor="#16A34A" />
                  </linearGradient>
                </defs>
                {gridLines().map((l, i) => (
                  <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="#DDE9D6" strokeWidth={1} strokeDasharray="6,6" />
                ))}
                <rect x={COURT.ox} y={COURT.oy} width={COURT.w} height={COURT.h} rx={4} fill="rgba(47,128,237,0.08)" />
                <rect x={COURT.ox} y={COURT.oy} width={COURT.w} height={COURT.h} rx={4} fill="none" stroke="rgba(31,61,43,0.34)" strokeWidth={2} />
                <line x1={COURT.cx} y1={COURT.oy} x2={COURT.cx} y2={COURT.oy + COURT.h} stroke="rgba(31,61,43,0.28)" strokeWidth={1.5} />
                <line x1={COURT.ox} x2={COURT.ox + COURT.w} y1={COURT.netY} y2={COURT.netY} stroke="rgba(31,61,43,0.38)" strokeWidth={2} />
                <line x1={COURT.ox} x2={COURT.ox + COURT.w} y1={COURT.kitchenTopY} y2={COURT.kitchenTopY} stroke="rgba(34,197,94,0.62)" strokeWidth={1.5} strokeDasharray="8,4" />
                <line x1={COURT.ox} x2={COURT.ox + COURT.w} y1={COURT.kitchenBottomY} y2={COURT.kitchenBottomY} stroke="rgba(34,197,94,0.62)" strokeWidth={1.5} strokeDasharray="8,4" />

                {definition.visualization === "movement" && movementPath.length > 0 && (
                  <>
                    <polyline
                      fill="none"
                      points={movementPolyline}
                      stroke="url(#trailGrad)"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={8}
                      opacity={0.85}
                    />
                    {movementPath.map((point, index) => {
                      const isLast = index === movementPath.length - 1;
                      return (
                        <circle
                          cx={point.x * 10}
                          cy={COURT.toSvgY(point.y)}
                          fill={isLast ? "#D9FF3F" : "#22C55E"}
                          key={`${point.x}-${point.y}-${index}`}
                          r={isLast ? 7 : 5}
                          stroke="white"
                          strokeWidth={isLast ? 2 : 1.5}
                        />
                      );
                    })}
                    {firstPt && (
                      <text x={firstPt.x * 10 - 12} y={COURT.toSvgY(firstPt.y) - 10} fontSize={11} fontWeight={700} fill="#14241B">
                        起点
                      </text>
                    )}
                    {lastPt && (
                      <text x={lastPt.x * 10 + 12} y={COURT.toSvgY(lastPt.y) + 18} fontSize={11} fontWeight={700} fill="#14241B" textAnchor="end">
                        终点
                      </text>
                    )}
                  </>
                )}
                {!movementPath.length ? (
                  <text fill="#64748B" fontSize={14} fontWeight={700} textAnchor="middle" x={500} y={370}>
                    暂无可用轨迹
                  </text>
                ) : null}
              </svg>
              <div className="absolute bottom-6 right-6 rounded-xl border border-[#DDE9D6] bg-white/90 px-3 py-2 text-xs shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="inline-block h-2.5 w-5 rounded-full bg-gradient-to-r from-[#86EFAC] to-[#16A34A]" />
                  <span className="font-semibold text-[#14241B]">轨迹路径</span>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#D9FF3F] border border-[#16A34A]" />
                  <span className="text-slate-600">终点</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#22C55E]" />
                  <span className="text-slate-600">路径点</span>
                </div>
                <div className="border-t border-[#DDE9D6] mt-1.5 pt-1.5">
                  <span className="inline-block h-1 w-5 rounded border-t border-dashed border-[#22C55E] mr-1.5 align-middle" />
                  <span className="text-slate-600">厨房线</span>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="grid gap-3">
          {definition.insights.map((insight) => (
            <article className="rounded-2xl border border-[#DDE9D6] bg-white/75 p-4" key={insight.id}>
              <strong className="text-[#14241B]">{insight.title}</strong>
              <p className="mt-2 text-sm leading-6 text-slate-600">{insight.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
