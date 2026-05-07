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
  const sparkline = metric.sparkline.map((value, index) => {
    const x = index * (100 / Math.max(metric.sparkline.length - 1, 1));
    const y = 38 - (Number(value) / 100) * 30;
    return `${x},${Math.max(4, Math.min(36, y))}`;
  });

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
          <polyline
            fill="none"
            points={sparkline.join(" ")}
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
