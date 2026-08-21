import { useMemo } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import { PB_DIMENSION_META, PB_DIMENSION_ORDER } from "../../types/pbReport";
import PbEvidenceUnavailable from "./PbEvidenceUnavailable";

/**
 * 设计 D5（fail-closed）：正式六维评分模型（player-skill-rating.v1 + modelVersion）
 * 出现前，job 模式一律不显示 PB 式 2.0~5.5 评分。模块改名为「本场表现概览」，
 * 展示六维标签位（无分数），并提示"技能评分模型尚未生成"。不误用旧 skillRatings。
 */
export default function PbSkillRatingSection() {
  const { report } = usePbReport();

  const isDemo = report?.source === "demo";

  // 仅 demo 允许代表性演示表现；否则一律"模型尚未生成"
  const showDemoOverview = isDemo;

  // 正式模型存在性判定（无 player-skill-rating.v1 → 恒为 false）
  const hasFormalModel = useMemo(() => {
    return false; // 正式 skill-rating model artifact 尚未定义
  }, []);

  if (hasFormalModel) {
    // 未来正式模型接入后，在此渲染"单场技能评分"（含 6 维饼图/值）。暂未定义。
    return null;
  }

  return (
    <div className="pb-card p-6">
      <div className="mb-6">
        <p className="text-xs font-bold uppercase tracking-wider text-gray-500">
          单场比赛
        </p>
        <h2 className="mt-1 text-2xl font-black text-[var(--pb-text-primary,#111827)]">
          {showDemoOverview ? "演示表现概览" : "本场表现概览"}
        </h2>
      </div>

      <div className="mb-6">
        <PbEvidenceUnavailable
          reason={
            showDemoOverview
              ? "演示数据：正式技能评分模型尚未接入"
              : "技能评分模型尚未生成"
          }
        />
      </div>

      {/* 仅保留六维标签位（无语义分数，避免伪 2.0~5.5） */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {PB_DIMENSION_ORDER.map((key) => {
          const meta = PB_DIMENSION_META[key];
          return (
            <div
              key={key}
              className="rounded-xl p-4 border border-dashed bg-white"
            >
              <div className="font-bold text-sm text-[var(--pb-text-secondary,#6b7280)]">
                {meta.label}
              </div>
              <div className="mt-2 text-sm text-[var(--pb-text-muted,#9ca3af)]">
                模型尚未生成
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}