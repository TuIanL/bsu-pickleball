import { AlertTriangle, Footprints, Route, Target } from "lucide-react";
import type {
  CourtPoint,
  CourtRoute,
  Diagnosis,
  MovementPoint,
  Rally,
  ReportDefinition,
} from "../../types/report";

interface ReportVisualizationProps {
  definition: ReportDefinition;
  diagnoses: Diagnosis[];
  landingPoints: CourtPoint[];
  movementPath: MovementPoint[];
  rallies: Rally[];
  routes: CourtRoute[];
}

const iconMap = {
  heat: Target,
  movement: Footprints,
  rally: Route,
  diagnosis: AlertTriangle,
};

export function ReportVisualization({
  definition,
  diagnoses,
  landingPoints,
  movementPath,
  rallies,
  routes,
}: ReportVisualizationProps) {
  const Icon = iconMap[definition.visualization];
  const movementPolyline = movementPath.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-[#54FE49]">
            <Icon size={15} aria-hidden="true" />
            {definition.eyebrow}
          </p>
          <h2 className="mt-2 text-2xl font-black text-white">核心可视化</h2>
        </div>
        <p className="max-w-2xl text-sm leading-6 text-slate-400">{definition.summary}</p>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
          {definition.visualization === "diagnosis" ? (
            <div className="grid gap-3">
              {diagnoses.map((diagnosis) => (
                <article className="rounded-2xl border border-white/10 bg-white/[0.045] p-4" key={diagnosis.id}>
                  <div className="flex items-center justify-between gap-3">
                    <strong className="text-white">{diagnosis.issue}</strong>
                    <span className="rounded-full border border-[#FF9500]/30 bg-[#FF9500]/10 px-2 py-1 text-xs font-black text-[#FFD7A0]">
                      {diagnosis.severity}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-400">{diagnosis.evidence}</p>
                  <p className="mt-3 rounded-2xl bg-[#54FE49]/10 p-3 text-sm font-semibold leading-6 text-[#C9FFC5]">
                    {diagnosis.suggestion}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <svg className="aspect-[16/11] w-full" viewBox="0 0 100 72" aria-label={`${definition.title} visualization`}>
              <rect x="12" y="6" width="76" height="60" rx="2" fill="rgba(47,128,237,0.16)" />
              <rect x="12" y="6" width="76" height="60" rx="2" fill="none" stroke="rgba(255,255,255,0.52)" strokeWidth="0.7" />
              <line x1="50" x2="50" y1="6" y2="66" stroke="rgba(255,255,255,0.52)" strokeWidth="0.55" />
              <line x1="12" x2="88" y1="36" y2="36" stroke="rgba(255,255,255,0.7)" strokeWidth="0.65" />
              <line x1="12" x2="88" y1="28" y2="28" stroke="rgba(84,254,73,0.62)" strokeWidth="0.55" />
              <line x1="12" x2="88" y1="44" y2="44" stroke="rgba(84,254,73,0.62)" strokeWidth="0.55" />

              {definition.visualization === "heat"
                ? landingPoints.map((point) => (
                    <g key={point.id}>
                      <circle cx={point.x} cy={point.y * 0.64 + 6} fill="rgba(84,254,73,0.16)" r={6 + point.intensity * 7} />
                      <circle cx={point.x} cy={point.y * 0.64 + 6} fill="#54FE49" r={2.4 + point.intensity * 2} />
                    </g>
                  ))
                : null}

              {definition.visualization === "movement" ? (
                <>
                  <polyline
                    fill="none"
                    points={movementPolyline.split(" ").map((pair) => {
                      const [x, y] = pair.split(",").map(Number);
                      return `${x},${y * 0.64 + 6}`;
                    }).join(" ")}
                    stroke="#54FE49"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.6"
                  />
                  {movementPath.map((point, index) => (
                    <circle
                      cx={point.x}
                      cy={point.y * 0.64 + 6}
                      fill={index === movementPath.length - 1 ? "#D9FF3F" : "#54FE49"}
                      key={`${point.x}-${point.y}-${index}`}
                      r={index === movementPath.length - 1 ? 3 : 2}
                    />
                  ))}
                </>
              ) : null}

              {definition.visualization === "rally"
                ? routes.map((route) => (
                    <g key={route.id}>
                      <line
                        x1={route.from.x}
                        x2={route.to.x}
                        y1={route.from.y * 0.64 + 6}
                        y2={route.to.y * 0.64 + 6}
                        stroke="#D9FF3F"
                        strokeLinecap="round"
                        strokeWidth="1.4"
                      />
                      <circle cx={route.from.x} cy={route.from.y * 0.64 + 6} fill="#2F80ED" r="2.5" />
                      <circle cx={route.to.x} cy={route.to.y * 0.64 + 6} fill="#54FE49" r="3" />
                    </g>
                  ))
                : null}
            </svg>
          )}
        </div>

        <div className="grid gap-3">
          {definition.visualization === "rally"
            ? rallies.map((rally) => (
                <article className="rounded-2xl border border-white/10 bg-white/[0.045] p-4" key={rally.id}>
                  <div className="flex items-center justify-between gap-3">
                    <strong className="text-white">{rally.title}</strong>
                    <span className="text-xs font-bold text-[#54FE49]">{rally.duration}</span>
                  </div>
                  <p className="mt-2 text-sm font-semibold text-slate-300">{rally.pattern}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{rally.observation}</p>
                </article>
              ))
            : definition.insights.map((insight) => (
                <article className="rounded-2xl border border-white/10 bg-white/[0.045] p-4" key={insight.id}>
                  <strong className="text-white">{insight.title}</strong>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{insight.body}</p>
                </article>
              ))}
        </div>
      </div>
    </section>
  );
}
