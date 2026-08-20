import { useMemo } from "react";
import type { ShotRow } from "../../types/report";
import { usePbReport } from "../../contexts/PbReportContext";
import { mockInPercent, mockSpeedPercentile } from "../../utils/pbMockData";

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

function stableHash01(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return (h % 1000) / 1000;
}

export default function PbPlayerHeaderCard() {
  const { selectedPlayerId, selectedSubject, report } = usePbReport();

  // React Compiler 需要完整稳定的依赖，而不是可选链片段
  const shotRows = report?.shotRows;
  const subjectName = selectedSubject?.name;
  const totalShots = useMemo(() => {
    if (!shotRows) return 0;
    return shotRows.filter(
      (row: ShotRow) => !subjectName || row.player === subjectName
    ).length;
  }, [shotRows, subjectName]);

  const inPct = useMemo(() => mockInPercent(selectedPlayerId), [selectedPlayerId]);

  const ballPercentile = useMemo(
    () => mockSpeedPercentile(selectedPlayerId, "ball"),
    [selectedPlayerId]
  );
  const paddlePercentile = useMemo(
    () => mockSpeedPercentile(selectedPlayerId, "paddle"),
    [selectedPlayerId]
  );

  const ballSpeed = useMemo(() => {
    const base = 35;
    const delta = (stableHash01(selectedPlayerId + ":balls") - 0.5) * 4;
    return Math.round((base + delta) * 10) / 10;
  }, [selectedPlayerId]);

  const paddleSpeed = useMemo(() => {
    const base = 27;
    const delta = (stableHash01(selectedPlayerId + ":paddles") - 0.5) * 4;
    return Math.round((base + delta) * 10) / 10;
  }, [selectedPlayerId]);

  const playerName = selectedSubject?.name || "球员";

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
              总击球数： <span className="text-lg">{totalShots}</span>
            </div>
            <div className="flex items-center gap-2 flex-1 min-w-[200px]">
              <div className="text-sm font-semibold whitespace-nowrap">
                进区率 ({Math.round(inPct * 100)}%)
              </div>
              <div className="flex-1 h-3 bg-[var(--pb-gray-light,#e5e7eb)] rounded-full overflow-hidden flex">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${inPct * 100}%`,
                    background: "var(--pb-neon-green, #00FF41)",
                  }}
                />
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.max(0, Math.min(8, (1 - inPct) * 50))}%`,
                    background: "var(--pb-magenta, #EC4899)",
                    marginLeft: 2,
                  }}
                  title="擦网率"
                />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-sm whitespace-nowrap">
              <span className="font-semibold text-[var(--pb-text-primary,#111827)]">
                球速
              </span>
              <span className="mx-2">—</span>
              <span className="font-bold text-lg text-[var(--pb-text-primary,#111827)]">
                {ballSpeed} 英里/小时
              </span>
              <span className="ml-2 text-xs font-semibold text-[var(--pb-text-secondary,#6b7280)]">
                {ballPercentile.label}
              </span>
            </div>
            <div className="flex-1 min-w-[180px] h-2.5 bg-[var(--pb-gray-light,#e5e7eb)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${ballPercentile.percentile}%`,
                  background: "var(--pb-neon-green, #00FF41)",
                }}
              />
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-sm whitespace-nowrap">
              <span className="font-semibold text-[var(--pb-text-primary,#111827)]">
                拍速
              </span>
              <span className="mx-2">—</span>
              <span className="font-bold text-lg text-[var(--pb-text-primary,#111827)]">
                {paddleSpeed} 英里/小时
              </span>
              <span className="ml-2 text-xs font-semibold text-[var(--pb-text-secondary,#6b7280)]">
                {paddlePercentile.label}
              </span>
            </div>
            <div className="flex-1 min-w-[180px] h-2.5 bg-[var(--pb-gray-light,#e5e7eb)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${paddlePercentile.percentile}%`,
                  background: "var(--pb-neon-green, #00FF41)",
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
