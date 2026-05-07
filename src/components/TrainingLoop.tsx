import { ArrowRight, Dumbbell, Play, ScanLine } from "lucide-react";
import type { Diagnosis, TrainingRecommendation } from "../types/report";

interface TrainingLoopProps {
  diagnoses: Diagnosis[];
  recommendations: TrainingRecommendation[];
}

export function TrainingLoop({ diagnoses, recommendations }: TrainingLoopProps) {
  return (
    <section className="section-band training-band" id="training">
      <div className="section-inner training-layout">
        <div className="training-intro">
          <span className="panel-kicker">学习 · 练习 · 复测</span>
          <h2>学-练-评教学闭环</h2>
          <p>报告问题被转成训练任务，下一次报告继续验证目标完成情况。</p>
          <div className="loop-icons" aria-label="闭环步骤">
            <span>
              <ScanLine size={18} aria-hidden="true" />
              数据问题
            </span>
            <ArrowRight size={17} aria-hidden="true" />
            <span>
              <Play size={18} aria-hidden="true" />
              内容对标
            </span>
            <ArrowRight size={17} aria-hidden="true" />
            <span>
              <Dumbbell size={18} aria-hidden="true" />
              复测目标
            </span>
          </div>
        </div>

        <div className="training-cards">
          {recommendations.map((item) => {
            const diagnosis = diagnoses.find((entry) => entry.id === item.issueId);
            const range = Math.abs(item.progress.target - item.progress.previous);
            const completed = Math.abs(item.progress.current - item.progress.previous);
            const progressValue = range === 0 ? 100 : Math.min((completed / range) * 100, 100);

            return (
              <article className="training-card" key={item.id}>
                <div className="training-card-head">
                  <span>{diagnosis?.issue ?? "专项问题"}</span>
                  <strong>{item.title}</strong>
                </div>
                <div className="media-row">
                  <div className="video-placeholder">
                    <Play size={25} aria-hidden="true" />
                    <span>{item.learningContent}</span>
                  </div>
                  <div className="motion-placeholder" aria-label="动作对标占位">
                    <div className="skeleton-line shoulder" />
                    <div className="skeleton-line arm" />
                    <div className="skeleton-line leg left" />
                    <div className="skeleton-line leg right" />
                  </div>
                </div>
                <p>{item.practiceTask}</p>
                <div className="goal-row">
                  <span>{item.nextTarget}</span>
                  <strong>
                    {item.progress.current}
                    {item.progress.unit}
                  </strong>
                </div>
                <div className="progress-track" aria-label="训练进度">
                  <span style={{ width: `${progressValue}%` }} />
                </div>
                <div className="progress-labels">
                  <span>
                    前次 {item.progress.previous}
                    {item.progress.unit}
                  </span>
                  <span>
                    目标 {item.progress.target}
                    {item.progress.unit}
                  </span>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
