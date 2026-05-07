import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { Diagnosis, TrainingRecommendation } from "../types/report";

interface DiagnosisSectionProps {
  diagnoses: Diagnosis[];
  recommendations: TrainingRecommendation[];
}

export function DiagnosisSection({ diagnoses, recommendations }: DiagnosisSectionProps) {
  return (
    <section className="section-band diagnosis-band" id="diagnosis">
      <div className="section-inner">
        <div className="section-title-row">
          <div>
            <span className="panel-kicker">动作诊断</span>
            <h2>个性化动作诊断</h2>
          </div>
          <p>算法输出被整理为动作问题、证据和可执行训练方向。</p>
        </div>

        <div className="diagnosis-grid">
          {diagnoses.map((diagnosis) => {
            const recommendation = recommendations.find((item) => item.issueId === diagnosis.id);

            return (
              <article className={`diagnosis-card severity-${diagnosis.severity}`} key={diagnosis.id}>
                <div className="diagnosis-head">
                  <div className="severity-icon" aria-hidden="true">
                    <AlertCircle size={19} />
                  </div>
                  <div>
                    <span>{diagnosis.priority}</span>
                    <strong>{diagnosis.issue}</strong>
                  </div>
                  <em>{diagnosis.severity}</em>
                </div>
                <p className="evidence">{diagnosis.evidence}</p>
                <div className="suggestion-block">
                  <CheckCircle2 size={17} aria-hidden="true" />
                  <div>
                    <strong>{diagnosis.suggestion}</strong>
                    <span>{diagnosis.expectedOutcome}</span>
                  </div>
                </div>
                {recommendation ? (
                  <div className="linked-training">
                    <span>关联训练</span>
                    <strong>{recommendation.title}</strong>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
