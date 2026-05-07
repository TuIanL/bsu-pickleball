import { CirclePause, Maximize2, Play, Volume2 } from "lucide-react";
import type { CSSProperties } from "react";
import type {
  MatchSummary,
  PlayerMarker,
  ShotTrajectory,
  TimelineMarker,
  VideoOverlayLabel,
} from "../../types/report";

interface VideoAnalysisCardProps {
  compact?: boolean;
  labels: VideoOverlayLabel[];
  match: MatchSummary;
  players: PlayerMarker[];
  timeline: TimelineMarker[];
  trajectories: ShotTrajectory[];
}

const toneClass = {
  advantage: "border-[#22C55E]/40 bg-[#22C55E]/15 text-[#DCFCE7]",
  risk: "border-[#FF9500]/40 bg-[#FF9500]/15 text-[#FFD7A0]",
  error: "border-[#FF4D4F]/40 bg-[#FF4D4F]/15 text-[#FFC2C3]",
  training: "border-[#2F80ED]/40 bg-[#2F80ED]/15 text-[#BBD8FF]",
};

const markerClass = {
  advantage: "bg-[#22C55E]",
  risk: "bg-[#FF9500]",
  error: "bg-[#FF4D4F]",
  training: "bg-[#2F80ED]",
};

export function VideoAnalysisCard({
  compact = false,
  labels,
  match,
  players,
  timeline,
  trajectories,
}: VideoAnalysisCardProps) {
  return (
    <article className="sport-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-[#DDE9D6] px-4 py-3 sm:px-5">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">实时智能标注</p>
          <h2 className="mt-1 text-lg font-black text-[#14241B] sm:text-xl">视频回放 · {match.currentRally}</h2>
        </div>
        <div className="rounded-full border border-[#DDE9D6] bg-[#17231D] px-3 py-1 text-sm font-black text-white">
          {match.score}
        </div>
      </div>

      <div className="relative aspect-video overflow-hidden bg-[#091016]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_45%,rgba(34,197,94,0.1),transparent_35%),linear-gradient(135deg,rgba(47,128,237,0.22),transparent_42%),linear-gradient(180deg,#151A1F,#080C10)]" />
        <div className="absolute inset-4 rounded-[1.75rem] border border-white/10 bg-black/20 shadow-[inset_0_0_80px_rgba(0,0,0,0.5)]" />

        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 100 56"
          role="img"
          aria-label="模拟匹克球视频分析，包含场地线、球路和击球路径"
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur result="blur" stdDeviation="1.2" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect x="12" y="7" width="76" height="42" rx="1.5" fill="rgba(47,128,237,0.14)" />
          <rect x="12" y="7" width="76" height="42" rx="1.5" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="0.55" />
          <line x1="50" x2="50" y1="7" y2="49" stroke="rgba(255,255,255,0.55)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="28" y2="28" stroke="rgba(255,255,255,0.7)" strokeWidth="0.55" />
          <line x1="12" x2="88" y1="21.5" y2="21.5" stroke="rgba(34,197,94,0.62)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="34.5" y2="34.5" stroke="rgba(34,197,94,0.62)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="7" y2="7" stroke="rgba(255,255,255,0.55)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="49" y2="49" stroke="rgba(255,255,255,0.55)" strokeWidth="0.45" />
          <rect x="12" y="21.5" width="76" height="13" fill="rgba(34,197,94,0.045)" />

          {trajectories.map((trajectory) => (
            <path
              d={trajectory.path}
              fill="none"
              filter="url(#glow)"
              key={trajectory.id}
              stroke={trajectory.color}
              strokeDasharray={trajectory.id === "dink" ? "2 2" : undefined}
              strokeLinecap="round"
              strokeWidth="1.2"
            />
          ))}

          <circle cx="66" cy="31" r="5.6" fill="rgba(34,197,94,0.12)" />
          <circle cx="35" cy="25" r="4.8" fill="rgba(255,149,0,0.1)" />
          <circle cx="63" cy="38" r="4.2" fill="rgba(255,77,79,0.1)" />
        </svg>

        {players.map((player) => (
          <div
            className="absolute grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white/70 text-xs font-black text-[#071008] shadow-[0_8px_28px_rgba(0,0,0,0.42)]"
            key={player.id}
            style={
              {
                left: `${player.x}%`,
                top: `${player.y}%`,
                backgroundColor: player.color,
              } as CSSProperties
            }
          >
            {player.label}
          </div>
        ))}

        {labels.map((label) => (
          <span
            className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border px-3 py-1 text-[0.68rem] font-black shadow-[0_12px_32px_rgba(0,0,0,0.35)] backdrop-blur ${toneClass[label.tone]}`}
            key={label.id}
            style={{ left: `${label.x}%`, top: `${label.y}%` }}
          >
            {label.label}
          </span>
        ))}

        <div className="absolute left-4 top-4 rounded-2xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur">
          <p className="text-xs font-semibold text-slate-400">{match.teams}</p>
          <strong className="text-sm text-white">{match.venue}</strong>
        </div>

        <div className="absolute bottom-4 left-4 rounded-2xl border border-white/10 bg-black/50 px-3 py-2 backdrop-blur">
          <p className="text-xs font-semibold text-slate-400">{match.currentTime}</p>
          <strong className="text-sm text-white">{match.currentRally}</strong>
        </div>

        <button
          className="absolute left-1/2 top-1/2 grid size-16 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-[#22C55E]/35 bg-[#22C55E]/20 text-[#22C55E] shadow-[0_0_48px_rgba(34,197,94,0.22)] transition hover:scale-105 hover:bg-[#22C55E] hover:text-[#071008]"
          type="button"
          aria-label="播放演示视频"
        >
          <Play size={28} fill="currentColor" aria-hidden="true" />
        </button>
      </div>

      {!compact ? (
        <div className="border-t border-[#DDE9D6] bg-white/70 px-4 py-4 sm:px-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3 text-slate-600">
              <CirclePause size={18} aria-hidden="true" />
              <Volume2 size={18} aria-hidden="true" />
              <span className="text-xs font-bold">{match.currentTime} / {match.duration}</span>
            </div>
            <div className="relative h-2 flex-1 rounded-full bg-[#DFEADA]">
              <span className="absolute inset-y-0 left-0 rounded-full bg-[#22C55E]" style={{ width: "69%" }} />
              {timeline.map((marker) => (
                <span
                  className={`group absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#071008] ${markerClass[marker.tone]}`}
                  key={marker.id}
                  style={{ left: `${marker.position}%` }}
                  tabIndex={0}
                >
                  <span className="pointer-events-none absolute bottom-6 left-1/2 z-10 w-48 -translate-x-1/2 rounded-xl border border-white/10 bg-[#111318] px-3 py-2 text-xs font-semibold text-white opacity-0 shadow-2xl transition group-hover:opacity-100 group-focus:opacity-100">
                    {marker.time} · {marker.label}
                  </span>
                </span>
              ))}
            </div>
            <Maximize2 size={18} className="text-slate-600" aria-hidden="true" />
          </div>
        </div>
      ) : null}
    </article>
  );
}
