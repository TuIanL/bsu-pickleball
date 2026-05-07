import { Timer } from "lucide-react";
import type { Rally } from "../types/report";

interface RallyAnalysisProps {
  rallies: Rally[];
}

export function RallyAnalysis({ rallies }: RallyAnalysisProps) {
  return (
    <section className="rally-panel" aria-label="回合分析">
      <div className="panel-heading compact">
        <div>
          <span className="panel-kicker">回合复盘</span>
          <h2>关键回合分析</h2>
        </div>
      </div>
      <div className="rally-list">
        {rallies.map((rally) => (
          <article className="rally-item" key={rally.id}>
            <div className="rally-title">
              <strong>{rally.title}</strong>
              <span>
                <Timer size={14} aria-hidden="true" />
                {rally.duration}
              </span>
            </div>
            <div className="rally-stats">
              <span>{rally.shots} 拍</span>
              <span>{rally.result}</span>
            </div>
            <p className="pattern">{rally.pattern}</p>
            <p>{rally.observation}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
