import { ListFilter } from "lucide-react";
import { useMemo, useState } from "react";
import type { CourtPoint, ShotRow, ShotType } from "../../types/report";

type ShotFilter = ShotType | "All";

interface ShotExplorerProps {
  filters: readonly ShotFilter[];
  landingPoints: CourtPoint[];
  shots: ShotRow[];
}

const qualityClass = {
  high: "bg-[#54FE49]/15 text-[#C9FFC5] border-[#54FE49]/30",
  medium: "bg-[#D9FF3F]/14 text-[#F0FF9A] border-[#D9FF3F]/30",
  low: "bg-[#FF4D4F]/14 text-[#FFC2C3] border-[#FF4D4F]/30",
};

const resultClass: Record<string, string> = {
  Winner: "text-[#54FE49]",
  "Forced Error": "text-[#D9FF3F]",
  "Unforced Error": "text-[#FF4D4F]",
  Neutral: "text-slate-300",
  "Setup Advantage": "text-[#9CC8FF]",
};

export function ShotExplorer({ filters, landingPoints, shots }: ShotExplorerProps) {
  const [selectedFilter, setSelectedFilter] = useState<ShotFilter>("All");
  const filteredShots = useMemo(
    () =>
      shots.filter((shot) => {
        if (selectedFilter === "All") {
          return true;
        }

        if (selectedFilter === "Error") {
          return shot.result.includes("Error");
        }

        return shot.type === selectedFilter;
      }),
    [selectedFilter, shots]
  );

  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-[#54FE49]">
            <ListFilter size={15} aria-hidden="true" />
            Shot Explorer
          </p>
          <h2 className="mt-2 text-2xl font-black text-white">击球拆解与质量评分</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {filters.map((filter) => (
            <button
              className={`rounded-full border px-3 py-2 text-xs font-black transition ${
                selectedFilter === filter
                  ? "border-[#54FE49] bg-[#54FE49] text-[#071008]"
                  : "border-white/10 bg-white/[0.055] text-slate-300 hover:border-white/20 hover:bg-white/[0.09]"
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
        <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
          <div className="relative aspect-[4/5] overflow-hidden rounded-2xl bg-[#0C151D]">
            <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 120" aria-label="Shot landing map">
              <rect x="16" y="9" width="68" height="102" rx="2" fill="rgba(47,128,237,0.16)" />
              <rect x="16" y="9" width="68" height="102" rx="2" fill="none" stroke="rgba(255,255,255,0.52)" strokeWidth="0.7" />
              <line x1="50" x2="50" y1="9" y2="111" stroke="rgba(255,255,255,0.52)" strokeWidth="0.55" />
              <line x1="16" x2="84" y1="60" y2="60" stroke="rgba(255,255,255,0.66)" strokeWidth="0.7" />
              <line x1="16" x2="84" y1="47" y2="47" stroke="rgba(84,254,73,0.62)" strokeWidth="0.55" />
              <line x1="16" x2="84" y1="73" y2="73" stroke="rgba(84,254,73,0.62)" strokeWidth="0.55" />
              {landingPoints.map((point, index) => (
                <g key={point.id}>
                  <circle
                    cx={point.x}
                    cy={point.y + 12}
                    fill={index % 3 === 0 ? "rgba(84,254,73,0.18)" : index % 3 === 1 ? "rgba(255,149,0,0.18)" : "rgba(255,77,79,0.18)"}
                    r={5 + point.intensity * 7}
                  />
                  <circle
                    cx={point.x}
                    cy={point.y + 12}
                    fill={index % 3 === 0 ? "#54FE49" : index % 3 === 1 ? "#FF9500" : "#FF4D4F"}
                    r={2.5 + point.intensity * 2}
                  />
                </g>
              ))}
            </svg>
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-xs font-semibold text-slate-400">
            <span className="inline-flex items-center gap-2"><i className="size-2 rounded-full bg-[#54FE49]" /> Winner</span>
            <span className="inline-flex items-center gap-2"><i className="size-2 rounded-full bg-[#FF9500]" /> Risk</span>
            <span className="inline-flex items-center gap-2"><i className="size-2 rounded-full bg-[#FF4D4F]" /> Error</span>
          </div>
        </div>

        <div className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.035]">
          <div className="grid grid-cols-[0.7fr_1fr_0.65fr_1.25fr_0.8fr_1fr] gap-3 border-b border-white/10 px-4 py-3 text-xs font-black uppercase tracking-[0.12em] text-slate-500">
            <span>Time</span>
            <span>Shot</span>
            <span>Player</span>
            <span>Placement</span>
            <span>Quality</span>
            <span>Result</span>
          </div>
          <div className="divide-y divide-white/10">
            {filteredShots.map((shot) => (
              <article
                className="grid grid-cols-[0.7fr_1fr_0.65fr_1.25fr_0.8fr_1fr] gap-3 px-4 py-3 text-sm transition hover:bg-white/[0.055]"
                key={shot.id}
              >
                <span className="font-semibold text-slate-400">{shot.time}</span>
                <strong className="text-white">{shot.type}</strong>
                <span className="text-slate-300">Player {shot.player}</span>
                <span className="text-slate-400">{shot.placement}</span>
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
