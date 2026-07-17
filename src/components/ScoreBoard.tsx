import type { LiveCodingState } from "../types/report";

interface ScoreBoardProps {
  liveState: LiveCodingState | null;
  onCorrectScore?: (scoreA: number, scoreB: number, server: "A" | "B", reason: string) => void;
  onInitialServerSelect?: (server: "A" | "B") => void;
  showInitialServerSelector?: boolean;
  openRallyExists?: boolean;
}

export function ScoreBoard({
  liveState, onCorrectScore, onInitialServerSelect,
  showInitialServerSelector, openRallyExists,
}: ScoreBoardProps) {
  if (!liveState) return null;

  const scoringMode = liveState.scoring_mode ?? "none";
  if (scoringMode === "manual") {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center text-sm text-slate-500">
        双打自动计分暂不可用
      </div>
    );
  }

  const isScoring = scoringMode === "side_out_singles_v1";
  const server = liveState.server_team;
  const scoreA = liveState.score_a ?? 0;
  const scoreB = liveState.score_b ?? 0;

  return (
    <div className="space-y-3 rounded-xl border border-[#DDE9D6] bg-white p-4">
      {/* Header */}
      <ScoreHeader setOrdinal={liveState.set_ordinal} gameOrdinal={liveState.game_ordinal} />

      {/* Score Display */}
      <ScoreDisplay scoreA={scoreA} scoreB={scoreB} server={server} />

      {/* Recent Points */}
      <RecentPoints results={liveState.recent_results ?? []} openRallyExists={openRallyExists} />

      {/* Initial Server Selector */}
      {showInitialServerSelector && onInitialServerSelect && isScoring && (
        <InitialServerSelector onSelect={onInitialServerSelect} />
      )}
    </div>
  );
}

function ScoreHeader({ setOrdinal, gameOrdinal }: { setOrdinal: number; gameOrdinal: number }) {
  return (
    <div className="text-xs font-bold text-slate-500">
      {setOrdinal > 0 ? `盘 ${setOrdinal}` : ""} {gameOrdinal > 0 ? `· 局 ${gameOrdinal}` : ""}
    </div>
  );
}

function ScoreDisplay({ scoreA, scoreB, server }: { scoreA: number; scoreB: number; server: string | null | undefined }) {
  return (
    <div className="flex items-center justify-center gap-4 text-2xl font-black">
      <div className="flex flex-col items-center gap-1">
        {server === "A" && <span className="text-xs text-green-600">● 发球</span>}
        <span className={`${server === "A" ? "text-green-700" : "text-slate-700"}`}>{scoreA}</span>
        <span className="text-xs text-slate-400">A 方</span>
      </div>
      <span className="text-slate-300 text-xl">:</span>
      <div className="flex flex-col items-center gap-1">
        {server === "B" && <span className="text-xs text-blue-600">● 发球</span>}
        <span className={`${server === "B" ? "text-blue-700" : "text-slate-700"}`}>{scoreB}</span>
        <span className="text-xs text-slate-400">B 方</span>
      </div>
    </div>
  );
}

function RecentPoints({ results, openRallyExists }: { results: Array<{ winner: string | null; validity: string }>; openRallyExists?: boolean }) {
  return (
    <div className="flex items-center gap-1 justify-center">
      {results.map((r, i) => (
        <div
          key={i}
          className="w-4 h-4 rounded-sm border"
          style={{
            backgroundColor: r.winner === "A" ? "#22C55E" : r.winner === "B" ? "#3B82F6" : "#CBD5E1",
            borderColor: r.winner === "A" ? "#16A34A" : r.winner === "B" ? "#2563EB" : "#94A3B8",
          }}
          title={r.validity === "replay" ? "重打" : `A${r.winner === "A" ? "✓" : ""} B${r.winner === "B" ? "✓" : ""}`}
        />
      ))}
      {openRallyExists && (
        <div className="w-4 h-4 rounded-sm border border-dashed border-slate-400 bg-slate-100 animate-pulse" title="进行中" />
      )}
    </div>
  );
}

function InitialServerSelector({ onSelect }: { onSelect: (server: "A" | "B") => void }) {
  return (
    <div className="border-t border-slate-200 pt-2 mt-2">
      <p className="text-xs font-bold text-slate-500 mb-2">本局先发球方</p>
      <div className="flex gap-2">
        <button
          className="flex-1 rounded-lg bg-green-50 border border-green-300 px-3 py-1.5 text-xs font-bold text-green-700 hover:bg-green-100"
          onClick={() => onSelect("A")}
          type="button"
        >
          A 方
        </button>
        <button
          className="flex-1 rounded-lg bg-blue-50 border border-blue-300 px-3 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-100"
          onClick={() => onSelect("B")}
          type="button"
        >
          B 方
        </button>
      </div>
    </div>
  );
}
