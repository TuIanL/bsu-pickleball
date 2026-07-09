import {
  Activity,
  AlertTriangle,
  Radar,
  Send,
  Shield,
  Target,
  Timer,
  Waves,
} from "lucide-react";
import type { DashboardMetric } from "../../types/report";

const iconMap = {
  activity: Activity,
  target: Target,
  send: Send,
  waves: Waves,
  shield: Shield,
  alert: AlertTriangle,
  radar: Radar,
  timer: Timer,
};

interface MetricCardProps {
  metric: DashboardMetric;
}

export function MetricCard({ metric }: MetricCardProps) {
  const Icon = iconMap[metric.icon as keyof typeof iconMap] ?? Activity;
  const values = metric.sparkline.map((v) => Number(v));
  const avg = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  const avgY = 38 - (avg / 100) * 30;

  const points = values.map((value, index) => {
    const x = index * (100 / Math.max(values.length - 1, 1));
    const y = Math.max(4, Math.min(36, 38 - (value / 100) * 30));
    return { x, y };
  });

  const polylineStr = points.map((p) => `${p.x},${p.y}`).join(" ");
  const areaStr =
    points.length > 0
      ? `${points[0].x},38 ${points.map((p) => `${p.x},${p.y}`).join(" ")} ${points[points.length - 1].x},38`
      : "";

  return (
    <article className="sport-card group p-5 transition duration-300 hover:-translate-y-1 hover:border-[#22C55E]/35">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{metric.label}</p>
          <strong className="mt-3 block text-3xl font-black text-[#14241B] sm:text-4xl">{metric.value}</strong>
        </div>
        <span className="grid size-10 place-items-center rounded-2xl border border-[#22C55E]/25 bg-[#22C55E]/12 text-[#168A34]">
          <Icon size={19} aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 min-h-10 text-sm leading-6 text-slate-600">{metric.detail}</p>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[#DFEADA]">
        <span
          className="block h-full rounded-full bg-[#22C55E]"
          style={{ width: `${metric.progress}%` }}
        />
      </div>
      <div className="mt-4 flex items-end justify-between gap-3">
        <span
          className={`text-xs font-bold ${
            metric.direction === "down"
              ? "text-[#FF9500]"
              : metric.direction === "up"
                ? "text-[#168A34]"
                : "text-slate-500"
          }`}
        >
          {metric.trend}
        </span>
        <svg className="h-10 w-24 text-[#168A34]/80" viewBox="0 0 100 42" aria-hidden="true">
          <defs>
            <linearGradient id={`sparkArea-${metric.id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.25" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {points.length >= 3 && (
            <line x1={0} y1={avgY} x2={100} y2={avgY} stroke="currentColor" strokeWidth="1" strokeDasharray="2,3" opacity="0.35" />
          )}
          <polygon
            points={areaStr}
            fill={`url(#sparkArea-${metric.id})`}
          />
          <polyline
            fill="none"
            points={polylineStr}
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="3"
          />
        </svg>
      </div>
    </article>
  );
}
