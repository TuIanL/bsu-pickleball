import { usePbReport } from "../../contexts/PbReportContext";
import PbEvidenceUnavailable from "./PbEvidenceUnavailable";

/**
 * 设计 D6：LegalThirds 只在有 numerator/denominator 时显示"第三拍成功率 X% · n/m"；
 * 否则降级为"第三拍训练建议"或"本次分析暂无第三拍统计"。绝不无比例自称"合法第三拍率"。
 */
export default function PbLegalThirds() {
  const { evidence } = usePbReport();

  const thirdShot = evidence?.insights.thirdShot;

  const hasRatio = thirdShot?.status === "available" && thirdShot.value != null;

  const title = hasRatio ? "第三拍成功率" : "第三拍训练建议";

  return (
    <div className="pb-card p-5 sm:p-6">
      <div className="flex flex-row items-start gap-0">
        <div
          className="rounded-2xl inline-flex items-center justify-center shrink-0"
          style={{
            width: 48,
            height: 48,
            backgroundColor: "#FEF3C7",
            fontSize: 28,
            lineHeight: 1,
          }}
          aria-hidden
        >
          💡
        </div>

        <div className="flex-1 pl-4 min-w-0">
          <h3
            className="font-bold text-2xl"
            style={{ color: "var(--pb-text-primary, #111827)" }}
          >
            {title}
          </h3>
          <div className="mt-3 h-px bg-[var(--pb-card-border,#e5e7eb)]" />

          {hasRatio ? (
            <div className="mt-4">
              <div className="text-3xl font-black text-[var(--pb-primary,#23985b)]">
                {Math.round((thirdShot.value.numerator / thirdShot.value.denominator) * 100)}%
              </div>
              <div className="mt-1 text-sm text-[var(--pb-text-secondary,#6b7280)]">
                {thirdShot.value.numerator} / {thirdShot.value.denominator} 次
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <PbEvidenceUnavailable reason="本次分析暂无第三拍统计" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}