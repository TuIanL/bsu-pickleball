import { useMemo } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import PbEvidenceUnavailable from "./PbEvidenceUnavailable";

/**
 * 设计 D6：Coach 卡不再扮演真实教练。改以"AI 训练洞察 · 基于本场可观测指标生成"。
 * 结论仅来自 findings / recommendations / 真实 coachNotes；无 evidence 则显示
 * "当前数据不足以生成可靠训练建议"。
 */
export default function PbCoachInsight() {
  const { evidence } = usePbReport();

  const suggestion = useMemo<string>(() => {
    const findings = evidence?.insights.findings;
    if (findings?.status === "available" && findings.value.length > 0) {
      const top = findings.value[0];
      if (top?.diagnosis && top.diagnosis.trim()) return top.diagnosis.trim();
      if (top?.title && top.title.trim()) return top.title.trim();
    }
    const recs = evidence?.insights.recommendations;
    if (recs?.status === "available" && recs.value.length > 0) {
      const top = recs.value[0];
      if (top?.detail && top.detail.trim()) return top.detail.trim();
      if (top?.title && top.title.trim()) return top.title.trim();
    }
    const notes = evidence?.insights.coachNotes;
    if (notes?.status === "available" && notes.value.length > 0) {
      const n = notes.value[0] as unknown as { body?: string; title?: string };
      if (n?.body && n.body.trim()) return n.body.trim();
      if (n?.title && n.title.trim()) return n.title.trim();
    }
    return "";
  }, [evidence]);

  const hasEvidence = suggestion.length > 0;

  return (
    <div
      className="rounded-2xl p-5 sm:p-6"
      style={{
        background: "var(--pb-coach-bg, #FFF7E6)",
        border: "1px solid var(--pb-coach-border, #FDE68A)",
        boxShadow: "0 1px 3px rgba(245, 158, 11, 0.06)",
      }}
    >
      <div className="flex flex-col gap-4">
        <div>
          {/* 去掉假教练身份，改为 AI 洞察定位 */}
          <p className="font-bold text-base text-amber-900">AI 训练洞察</p>
          <p className="text-xs text-amber-700/80">
            基于本场可观测指标生成
          </p>
        </div>

        {hasEvidence ? (
          <h3 className="text-xl font-black leading-snug text-[#14241B]">
            {suggestion}
          </h3>
        ) : (
          <PbEvidenceUnavailable reason="当前数据不足以生成可靠训练建议" />
        )}
      </div>
    </div>
  );
}