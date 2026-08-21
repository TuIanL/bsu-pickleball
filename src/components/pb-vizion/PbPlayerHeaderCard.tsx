import { usePbReport } from "../../contexts/PbReportContext";
import PbEvidenceUnavailable from "./PbEvidenceUnavailable";

function PlayerAvatar({ name, size = 72 }: { name: string; size?: number }) {
  const initials = name?.trim().slice(0, 1).toUpperCase() || "P";
  const hue =
    name.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % 360;
  const bg = `linear-gradient(135deg, hsl(${hue} 85% 65%), hsl(${(hue + 40) % 360} 80% 55%))`;
  return (
    <div
      className="flex items-center justify-center rounded-full text-white font-semibold shrink-0"
      style={{
        background: bg,
        width: size,
        height: size,
        fontSize: size * 0.4,
      }}
    >
      {initials}
    </div>
  );
}

/** speed 数值：可用则显示 "xx 英里/小时"，否则显示明确空态（不伪造 35/27 mph）。 */
function SpeedMetric({ value }: { value: import("../../evidence/evidenceTypes").EvidenceValue<number> }) {
  if (value.status === "available") {
    return (
      <span className="font-bold text-lg text-[var(--pb-text-primary,#111827)]">
        {value.value} 英里/小时
      </span>
    );
  }
  return (
    <span className="text-sm font-semibold text-[var(--pb-text-muted,#9ca3af)]">
      暂未生成
    </span>
  );
}

export default function PbPlayerHeaderCard() {
  const { selectedSubject, report, evidence } = usePbReport();

  const playerName = selectedSubject?.name || "球员";

  // 证据层（设计 D2/D1）：总击球数按 canonical id 关联（evidence.summary.totalShots），
  // 而非展示名匹配。真实 job 里速度/百分位一律 unavailable，绝不 fake。
  const totalShots = evidence?.summary.totalShots;
  const ballSpeed = evidence?.summary.ballSpeedMph;
  const paddleSpeed = evidence?.summary.paddleSpeedMph;
  const inRate = evidence?.summary.inRatePct;

  const shownTotal =
    totalShots?.status === "available" ? totalShots.value : (report?.shotRows?.length ?? 0);

  return (
    <div className="pb-card p-5 sm:p-6">
      <div className="flex flex-col sm:flex-row gap-5 sm:gap-6 items-start sm:items-center">
        <div className="flex items-center gap-4 shrink-0">
          <PlayerAvatar name={playerName} size={72} />
          <div className="min-w-0">
            <div className="font-bold text-2xl text-[var(--pb-text-primary,#111827)] truncate">
              {playerName}
            </div>
            {selectedSubject?.role && (
              <div className="text-sm text-[var(--pb-text-secondary,#6b7280)] mt-1">
                {selectedSubject.role}
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 w-full space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-sm font-semibold text-[var(--pb-text-primary,#111827)] whitespace-nowrap">
              总击球数： <span className="text-lg">{shownTotal}</span>
            </div>
            <div className="flex items-center gap-2 flex-1 min-w-[200px]">
              {inRate?.status === "available" ? (
                <>
                  <div className="text-sm font-semibold whitespace-nowrap">
                    进区率 ({Math.round(inRate.value * 100)}%)
                  </div>
                  <div className="flex-1 h-3 bg-[var(--pb-gray-light,#e5e7eb)] rounded-full overflow-hidden flex">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${inRate.value * 100}%`,
                        background: "var(--pb-primary, #23985b)",
                      }}
                    />
                  </div>
                </>
              ) : (
                <PbEvidenceUnavailable />
              )}
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-sm whitespace-nowrap">
              <span className="font-semibold text-[var(--pb-text-primary,#111827)]">
                球速
              </span>
              <span className="mx-2">—</span>
              {ballSpeed ? <SpeedMetric value={ballSpeed} /> : <span className="text-sm text-[var(--pb-text-muted,#9ca3af)]">暂未生成</span>}
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-sm whitespace-nowrap">
              <span className="font-semibold text-[var(--pb-text-primary,#111827)]">
                拍速
              </span>
              <span className="mx-2">—</span>
              {paddleSpeed ? <SpeedMetric value={paddleSpeed} /> : <span className="text-sm text-[var(--pb-text-muted,#9ca3af)]">暂未生成</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}