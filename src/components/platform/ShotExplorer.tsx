import { ListFilter } from "lucide-react";
import { useMemo, useState } from "react";
import type { CourtPoint, ShotRow, ShotType } from "../../types/report";

type ShotFilter = ShotType | "全部";

interface ShotExplorerProps {
  filters: readonly ShotFilter[];
  landingPoints: CourtPoint[];
  shots: ShotRow[];
}

const qualityClass = {
  high: "bg-[#22C55E]/15 text-[#168A34] border-[#22C55E]/30",
  medium: "bg-[#D9FF3F]/24 text-[#6B7200] border-[#D9FF3F]/45",
  low: "bg-[#FF4D4F]/12 text-[#C92A2A] border-[#FF4D4F]/30",
};

const resultClass: Record<string, string> = {
  制胜分: "text-[#169A3A]",
  受迫失误: "text-[#8A6F00]",
  非受迫失误: "text-[#D62828]",
  中性: "text-slate-500",
  建立优势: "text-[#1E63B6]",
};

export function ShotExplorer({ filters, landingPoints, shots }: ShotExplorerProps) {
  const [selectedFilter, setSelectedFilter] = useState<ShotFilter>("全部");
  const filteredShots = useMemo(
    () =>
      shots.filter((shot) => {
        if (selectedFilter === "全部") {
          return true;
        }

        if (selectedFilter === "失误") {
          return shot.result.includes("失误");
        }

        return shot.type === selectedFilter;
      }),
    [selectedFilter, shots]
  );

  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <ListFilter size={15} aria-hidden="true" />
            击球浏览
          </p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">击球拆解与质量评分</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {filters.map((filter) => (
            <button
              className={`rounded-full border px-3 py-2 text-xs font-black transition ${
                selectedFilter === filter
                  ? "border-[#22C55E] bg-[#22C55E] text-[#071008]"
                  : "border-[#DDE9D6] bg-white/80 text-slate-700 hover:border-[#22C55E]/35 hover:bg-[#F5FFF2]"
              }`}
              key={filter}
              onClick={() => setSelectedFilter(filter)}
              type="button"
            >
              {filter}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
          <div className="relative aspect-[4/5] overflow-hidden rounded-2xl bg-[#E8F4E4]">
            <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 120" aria-label="击球落点图">
              <rect x="16" y="9" width="68" height="102" rx="2" fill="rgba(47,128,237,0.1)" />
              <rect x="16" y="9" width="68" height="102" rx="2" fill="none" stroke="rgba(31,61,43,0.34)" strokeWidth="0.7" />
              <line x1="50" x2="50" y1="9" y2="111" stroke="rgba(31,61,43,0.28)" strokeWidth="0.55" />
              <line x1="16" x2="84" y1="60" y2="60" stroke="rgba(31,61,43,0.38)" strokeWidth="0.7" />
              <line x1="16" x2="84" y1="47" y2="47" stroke="rgba(34,197,94,0.62)" strokeWidth="0.55" />
              <line x1="16" x2="84" y1="73" y2="73" stroke="rgba(34,197,94,0.62)" strokeWidth="0.55" />
              {landingPoints.map((point, index) => (
                <g key={point.id}>
                  <circle
                    cx={point.x}
                    cy={point.y + 12}
                    fill={index % 3 === 0 ? "rgba(34,197,94,0.18)" : index % 3 === 1 ? "rgba(255,149,0,0.18)" : "rgba(255,77,79,0.18)"}
                    r={5 + point.intensity * 7}
                  />
                  <circle
                    cx={point.x}
                    cy={point.y + 12}
                    fill={index % 3 === 0 ? "#22C55E" : index % 3 === 1 ? "#FF9500" : "#FF4D4F"}
                    r={2.5 + point.intensity * 2}
                  />
                </g>
              ))}
            </svg>
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-xs font-semibold text-slate-600">
            <span className="inline-flex items-center gap-2"><i className="size-2 rounded-full bg-[#22C55E]" /> 制胜</span>
            <span className="inline-flex items-center gap-2"><i className="size-2 rounded-full bg-[#FF9500]" /> 风险</span>
            <span className="inline-flex items-center gap-2"><i className="size-2 rounded-full bg-[#FF4D4F]" /> 失误</span>
          </div>
        </div>

        <div className="overflow-x-auto rounded-3xl border border-[#DDE9D6] bg-white/75">
          <div className="grid min-w-[760px] grid-cols-[0.7fr_1fr_0.65fr_1.25fr_0.8fr_1fr] gap-3 border-b border-[#DDE9D6] px-4 py-3 text-xs font-black uppercase tracking-[0.12em] text-slate-500">
            <span>时间</span>
            <span>击球</span>
            <span>球员</span>
            <span>落点</span>
            <span>质量</span>
            <span>结果</span>
          </div>
          <div className="min-w-[760px] divide-y divide-[#DDE9D6]">
            {filteredShots.map((shot) => (
              <article
                className="grid grid-cols-[0.7fr_1fr_0.65fr_1.25fr_0.8fr_1fr] gap-3 px-4 py-3 text-sm transition hover:bg-[#F5FFF2]"
                key={shot.id}
              >
                <span className="font-semibold text-slate-600">{shot.time}</span>
                <strong className="text-[#14241B]">{shot.type}</strong>
                <span className="text-slate-700">球员 {shot.player}</span>
                <span className="text-slate-600">{shot.placement}</span>
                <span className={`w-fit rounded-full border px-2 py-1 text-xs font-black ${qualityClass[shot.qualityBand]}`}>
                  {shot.qualityScore}
                </span>
                <span className={`font-bold ${resultClass[shot.result]}`}>{shot.result}</span>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
