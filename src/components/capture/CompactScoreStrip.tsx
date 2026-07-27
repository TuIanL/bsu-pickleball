import type { LiveCodingState } from "../../types/report";

interface Props {
  liveState: LiveCodingState | null;
}

export function CompactScoreStrip({ liveState }: Props) {
  if (!liveState) return null;

  const server = liveState.server_team;
  const scoreA = liveState.score_a ?? 0;
  const scoreB = liveState.score_b ?? 0;

  return (
    <div className="flex items-center justify-between rounded-lg px-4 py-2 text-sm" style={{ background: "var(--capture-surface-card)", border: "1px solid var(--capture-border-default)", minHeight: 48 }}>
      <span style={{ color: "var(--capture-text-secondary)" }}>
        {liveState.game_ordinal > 0 ? `第 ${liveState.game_ordinal} 局` : "等待开局"}
        <small className="ml-2">胜局 {liveState.games_won_a ?? 0}:{liveState.games_won_b ?? 0}</small>
      </span>
      <div className="flex items-center gap-3 font-bold" style={{ color: "var(--capture-text-primary)" }}>
        <span className={server === "A" ? "text-green-700" : ""}>A {scoreA}</span>
        <span style={{ color: "var(--capture-text-muted)" }}>:</span>
        <span className={server === "B" ? "text-blue-700" : ""}>B {scoreB}</span>
        {server && (
          <span className="text-xs font-medium" style={{ color: server === "A" ? "var(--capture-status-success)" : "var(--capture-status-info)" }}>
            ● {server} 方{liveState.serving_side === "left" ? "左区" : "右区"}发球
          </span>
        )}
      </div>
      <span className="text-xs" style={{ color: "var(--capture-text-muted)" }}>
        {liveState.match_status === "completed"
          ? `${liveState.match_winner} 方胜`
          : liveState.current_rally_segment_id
            ? `第 ${liveState.rally_ordinal} 分进行中`
            : liveState.scoring_phase === "serve_only" ? "发球得分" : "每球得分"}
      </span>
    </div>
  );
}
