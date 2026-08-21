import { usePbReport } from "../../contexts/PbReportContext";
import PbEvidenceUnavailable from "./PbEvidenceUnavailable";

/**
 * 设计 D7：ServeEvents 只证明"发球开始"（次数/发球者）；In/Out、深度、接发
 * 在相应 landing/bounce/return 权威建立前一律 unavailable。绝不硬接或伪造。
 */
export default function PbServesReturns() {
  const { evidence } = usePbReport();

  const serveCount = evidence?.serveReturn.serveCount;
  const serveInRate = evidence?.serveReturn.serveInRatePct;
  const serveDepth = evidence?.serveReturn.serveDepth;
  const returnCount = evidence?.serveReturn.returnCount;
  const returnDepth = evidence?.serveReturn.returnDepth;

  const showServeCount = serveCount?.status === "available";

  return (
    <div className="pb-card p-5 sm:p-6">
      <h3 className="font-bold text-lg text-[var(--pb-text-primary,#111827)]">
        发球与接发
      </h3>

      <div className="mt-5 space-y-5">
        {showServeCount ? (
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-[var(--pb-text-primary,#111827)]">
              发球次数
            </span>
            <span className="text-lg font-bold">{serveCount.value}</span>
          </div>
        ) : null}

        <div className="space-y-3">
          <SectionLabel label="发球进区率" />
          <div className="min-h-[80px]">
            {serveInRate?.status === "available" ? (
              <MetricPercent value={serveInRate.value} />
            ) : (
              <PbEvidenceUnavailable reason={serveInRate?.status === "unavailable" ? serveInRate.reason : undefined} />
            )}
          </div>

          <SectionLabel label="发球深度" />
          <div className="min-h-[80px]">
            {serveDepth?.status === "available" ? (
              <PbEvidenceUnavailable reason="深度解析尚未定义权威来源" />
            ) : (
              <PbEvidenceUnavailable reason={serveDepth?.status === "unavailable" ? serveDepth.reason : undefined} />
            )}
          </div>
        </div>

        <div className="space-y-3">
          <SectionLabel label="接发统计" />
          <div className="min-h-[80px]">
            {returnCount?.status === "available" ? (
              <div className="text-lg font-bold">{returnCount.value} 次</div>
            ) : (
              <PbEvidenceUnavailable reason={returnCount?.status === "unavailable" ? returnCount.reason : undefined} />
            )}
          </div>

          <SectionLabel label="接发深度" />
          <div className="min-h-[80px]">
            {returnDepth?.status === "available" ? (
              <PbEvidenceUnavailable reason="深度解析尚未定义权威来源" />
            ) : (
              <PbEvidenceUnavailable reason={returnDepth?.status === "unavailable" ? returnDepth.reason : undefined} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricPercent({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="text-2xl font-black text-[var(--pb-text-primary,#111827)]">
        {Math.round(value)}%
      </div>
    </div>
  );
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div className="text-sm font-semibold text-[var(--pb-text-secondary,#6b7280)]">
      {label}
    </div>
  );
}