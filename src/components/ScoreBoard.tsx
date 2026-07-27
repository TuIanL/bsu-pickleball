import type { LiveCodingState, SessionTimelineEvent } from "../types/report";

interface ScoreBoardProps {
  liveState: LiveCodingState | null;
  matchFormat?: string;
  onCorrectScore?: (scoreA: number, scoreB: number, server: "A" | "B", reason: string) => void;
  onInitialServerSelect?: (server: "A" | "B") => void;
  showInitialServerSelector?: boolean;
  openRallyExists?: boolean;
  timelineEvents?: SessionTimelineEvent[];
}

export function ScoreBoard({
  liveState, matchFormat, openRallyExists, timelineEvents = [],
}: ScoreBoardProps) {
  if (!liveState) return null;
  const server = liveState.server_team;
  const scoreA = liveState.score_a ?? 0;
  const scoreB = liveState.score_b ?? 0;

  return (
    <div className="space-y-3 rounded-xl border border-[#DDE9D6] bg-white p-4">
      {/* Header */}
      <ScoreHeader
        gameOrdinal={liveState.game_ordinal}
        hasCurrentGame={Boolean(liveState.current_game_segment_id)}
        gamesWonA={liveState.games_won_a ?? 0}
        gamesWonB={liveState.games_won_b ?? 0}
      />

      {/* Score Display */}
      <ScoreDisplay scoreA={scoreA} scoreB={scoreB} server={server} />

      <div className="flex flex-wrap items-center justify-center gap-2 text-xs font-bold">
        <span className="rounded bg-slate-100 px-2 py-1 text-slate-600">
          {liveState.scoring_phase === "serve_only" ? "发球得分" : "每球得分"}
        </span>
        {server && liveState.serving_side && (
          <span className="rounded bg-emerald-50 px-2 py-1 text-emerald-700">
            {server} 方{liveState.serving_side === "left" ? "左区" : "右区"}{matchFormat === "doubles" ? "队员" : ""}发球
          </span>
        )}
      </div>

      {liveState.match_status === "completed" && (
        <div className="rounded-lg bg-emerald-50 px-3 py-2 text-center text-sm font-bold text-emerald-800">
          比赛结束 · {liveState.match_winner} 方胜 · {liveState.games_won_a}:{liveState.games_won_b}
        </div>
      )}

      <CompletedGameSummary events={timelineEvents} />

      {/* Recent Points */}
      <RecentPoints results={liveState.recent_results ?? []} openRallyExists={openRallyExists} />

    </div>
  );
}

function ScoreHeader({ gameOrdinal, hasCurrentGame, gamesWonA, gamesWonB }: { gameOrdinal: number; hasCurrentGame: boolean; gamesWonA: number; gamesWonB: number }) {
  const visibleGame = gameOrdinal + (gameOrdinal > 0 && !hasCurrentGame ? 1 : 0);
  return (
    <div className="flex items-center justify-between text-xs font-bold text-slate-500">
      <span>{visibleGame > 0 ? `第 ${visibleGame} 局` : "等待开局"}</span>
      <span>胜局 A {gamesWonA} : {gamesWonB} B</span>
    </div>
  );
}

function CompletedGameSummary({ events }: { events: SessionTimelineEvent[] }) {
  const completed = events
    .filter(event => event.event_type === "game_end" && event.payload_json?.score_a != null && event.payload_json?.score_b != null)
    .slice(-1)[0];
  if (!completed) return null;

  const scoreA = Number(completed.payload_json.score_a);
  const scoreB = Number(completed.payload_json.score_b);
  const winner = completed.payload_json.winner === "A" ? "A 方胜" : completed.payload_json.winner === "B" ? "B 方胜" : "平局";
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2 text-center text-xs text-slate-500">
      上一局：<strong className="text-slate-700">A {scoreA} : {scoreB} B</strong> · {winner}
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
