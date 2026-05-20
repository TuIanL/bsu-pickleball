import { AlertTriangle, Footprints } from "lucide-react";
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
};

export function ReportVisualization({
  definition,
  diagnoses,
  movementPath,
}: ReportVisualizationProps) {
  const Icon = iconMap[definition.visualization];
  const movementPolyline = movementPath.map((point) => `${point.x},${point.y}`).join(" ");

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
        <div className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
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
            <svg className="aspect-[16/11] w-full" viewBox="0 0 100 72" aria-label={`${definition.title}可视化`}>
              <rect x="12" y="6" width="76" height="60" rx="2" fill="rgba(47,128,237,0.1)" />
              <rect x="12" y="6" width="76" height="60" rx="2" fill="none" stroke="rgba(31,61,43,0.34)" strokeWidth="0.7" />
              <line x1="50" x2="50" y1="6" y2="66" stroke="rgba(31,61,43,0.28)" strokeWidth="0.55" />
              <line x1="12" x2="88" y1="36" y2="36" stroke="rgba(31,61,43,0.38)" strokeWidth="0.65" />
              <line x1="12" x2="88" y1="28" y2="28" stroke="rgba(34,197,94,0.62)" strokeWidth="0.55" />
              <line x1="12" x2="88" y1="44" y2="44" stroke="rgba(34,197,94,0.62)" strokeWidth="0.55" />

              {definition.visualization === "movement" ? (
                <>
                  <polyline
                    fill="none"
                    points={
                      movementPath.length
                        ? movementPolyline.split(" ").map((pair) => {
                            const [x, y] = pair.split(",").map(Number);
                            return `${x},${y * 0.64 + 6}`;
                          }).join(" ")
                        : undefined
                    }
                    stroke="#22C55E"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.6"
                  />
                  {movementPath.map((point, index) => (
                    <circle
                      cx={point.x}
                      cy={point.y * 0.64 + 6}
                      fill={index === movementPath.length - 1 ? "#D9FF3F" : "#22C55E"}
                      key={`${point.x}-${point.y}-${index}`}
                      r={index === movementPath.length - 1 ? 3 : 2}
                    />
                  ))}
                  {!movementPath.length ? (
                    <text fill="#64748B" fontSize="4" fontWeight="700" textAnchor="middle" x="50" y="37">
                      暂无可用轨迹
                    </text>
                  ) : null}
                </>
              ) : null}

            </svg>
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
