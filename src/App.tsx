import {
  Activity,
  BarChart3,
  Brain,
  Cpu,
  Dumbbell,
  Radar,
  ScanLine,
} from "lucide-react";
import { AppHeader } from "./components/AppHeader";
import { CourtAnalysis } from "./components/CourtAnalysis";
import { DiagnosisSection } from "./components/DiagnosisSection";
import { HardwareFusionPreview } from "./components/HardwareFusionPreview";
import { MetricStrip } from "./components/MetricStrip";
import { RallyAnalysis } from "./components/RallyAnalysis";
import { TrainingLoop } from "./components/TrainingLoop";
import {
  diagnoses,
  hardwarePreview,
  reportSession,
  trainingRecommendations,
} from "./data/demoData";
import { productCopy } from "./data/productCopy";

const sections = [
  { id: "report", label: productCopy.sectionLabels.report, icon: BarChart3 },
  { id: "diagnosis", label: productCopy.sectionLabels.diagnosis, icon: Brain },
  { id: "training", label: productCopy.sectionLabels.training, icon: Dumbbell },
  { id: "hardware", label: productCopy.sectionLabels.hardware, icon: Cpu },
] as const;

function App() {
  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <main className="app">
      <AppHeader sections={sections} onNavigate={scrollToSection} />

      <section className="report-workspace section-band" id="report">
        <div className="section-inner report-grid">
          <div className="report-copy">
            <div className="eyebrow">
              <ScanLine size={16} aria-hidden="true" />
              <span>{productCopy.reportBadge}</span>
            </div>
            <h1>{productCopy.reportTitle}</h1>
            <p>{reportSession.summary}</p>
            <div className="session-meta" aria-label="报告信息">
              <span>{reportSession.athlete}</span>
              <span>{reportSession.level}</span>
              <span>{reportSession.venue}</span>
              <span>{reportSession.date}</span>
            </div>
          </div>

          <div className="report-status" aria-label="平台能力概览">
            <div>
              <span className="status-label">报告编号</span>
              <strong>{reportSession.reportId}</strong>
            </div>
            <div>
              <span className="status-label">数据链路</span>
              <strong>视觉捕捉 → 分析报告</strong>
            </div>
            <div>
              <span className="status-label">二期接口</span>
              <strong>TENG + IMU 预留</strong>
            </div>
          </div>

          <MetricStrip metrics={reportSession.metrics} />

          <CourtAnalysis session={reportSession} />

          <RallyAnalysis rallies={reportSession.rallies} />
        </div>
      </section>

      <DiagnosisSection diagnoses={diagnoses} recommendations={trainingRecommendations} />

      <TrainingLoop diagnoses={diagnoses} recommendations={trainingRecommendations} />

      <section className="platform-flow section-band">
        <div className="section-inner flow-grid">
          <div>
            <div className="eyebrow muted">
              <Radar size={16} aria-hidden="true" />
              <span>全链路数字交互</span>
            </div>
            <h2>从一次训练到下一次进步</h2>
          </div>
          <div className="flow-steps" aria-label="平台工作流">
            {["视觉采集", "运动分析", "扫码报告", "个性建议", "教学复测"].map(
              (step, index) => (
                <div className="flow-step" key={step}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{step}</strong>
                </div>
              )
            )}
          </div>
        </div>
      </section>

      <HardwareFusionPreview preview={hardwarePreview} />

      <footer className="app-footer">
        <Activity size={16} aria-hidden="true" />
        <span>{productCopy.brand} · 北京体育大学体育工程学院创新训练项目展示原型</span>
      </footer>
    </main>
  );
}

export default App;
