import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { Metric } from "../types/report";

interface MetricStripProps {
  metrics: Metric[];
}

export function MetricStrip({ metrics }: MetricStripProps) {
  return (
    <section className="metric-strip" aria-label="核心指标">
      {metrics.map((metric) => {
        const TrendIcon =
          metric.direction === "up"
            ? TrendingUp
            : metric.direction === "down"
              ? TrendingDown
              : Minus;

        return (
          <article className={`metric-card trend-${metric.direction}`} key={metric.id}>
            <div className="metric-card-top">
              <span>{metric.label}</span>
              <TrendIcon size={17} aria-hidden="true" />
            </div>
            <strong>{metric.value}</strong>
            <p>{metric.detail}</p>
            <small>{metric.trend}</small>
          </article>
        );
      })}
    </section>
  );
}
