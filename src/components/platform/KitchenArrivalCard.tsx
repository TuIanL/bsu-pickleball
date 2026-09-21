import type { KitchenArrivalArtifact, KitchenArrivalPlayerResult } from "../../types/kitchenArrival";

type LoadState = "idle" | "loading" | "available" | "unavailable" | "failed";

const TEAM_COLORS = { A: "#1455F5", B: "#F59E0B" } as const;

function stateLabel(player: KitchenArrivalPlayerResult): string {
  if (player.status === "available") return `${player.arrived_count}/${player.eligible_count} 回合到位`;
  if (player.status === "insufficient_evidence") return `${player.sample_count} 个有效样本 · 样本不足`;
  if (player.status === "not_applicable") return "单打不适用";
  return "身份或轨迹不可用";
}

export function KitchenArrivalCard({
  artifact,
  detail,
  loadState,
  status,
}: {
  artifact: KitchenArrivalArtifact | null;
  detail?: string;
  loadState: LoadState;
  status?: string;
}) {
  const effectiveStatus = artifact?.status ?? status;
  const isLoading = loadState === "loading";
  const players = artifact?.players ?? [];
  const showPercent = (player: KitchenArrivalPlayerResult) => player.status === "available" && player.arrival_rate !== null;
  return (
    <article className="rounded-2xl border border-[#DDE9D6] bg-white/75 p-4" data-testid="kitchen-arrival-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <strong className="block text-sm text-[#14241B]">发球队 · 网前到位率</strong>
          <p className="mt-1 text-xs leading-5 text-slate-500">按冻结的发球队与回合上下文统计，不是实时位置。</p>
        </div>
        <span className="rounded-full bg-[#E9F5FF] px-2.5 py-1 text-xs font-black text-[#1769AA]">双打</span>
      </div>
      <div className="mt-4 overflow-hidden rounded-xl border border-[#DDE9D6] bg-[#F5FAF1] p-3" data-testid="kitchen-arrival-court-profile">
        <svg aria-label="横向厨房线场地控制画像" className="h-20 w-full" role="img" viewBox="0 0 640 120">
          <rect fill="#EAF6E5" height="88" rx="12" width="640" x="0" y="16" />
          <rect fill="#D5ECCD" height="88" width="112" x="208" y="16" />
          <rect fill="#D5ECCD" height="88" width="112" x="320" y="16" />
          <line stroke="#FFFFFF" strokeDasharray="5 5" strokeWidth="4" x1="320" x2="320" y1="12" y2="108" />
          <line stroke="#7FB879" strokeWidth="3" x1="208" x2="208" y1="16" y2="104" />
          <line stroke="#7FB879" strokeWidth="3" x1="432" x2="432" y1="16" y2="104" />
          <text fill="#1455F5" fontSize="16" fontWeight="800" x="72" y="68">Team A 发球侧</text>
          <text fill="#B96B00" fontSize="16" fontWeight="800" x="470" y="68">Team B 发球侧</text>
          <text fill="#53705B" fontSize="11" fontWeight="700" textAnchor="middle" x="320" y="11">网</text>
          <text fill="#53705B" fontSize="11" fontWeight="700" textAnchor="middle" x="208" y="116">厨房线</text>
          <text fill="#53705B" fontSize="11" fontWeight="700" textAnchor="middle" x="432" y="116">厨房线</text>
        </svg>
        <p className="mt-1 text-center text-[11px] font-semibold text-slate-500">横向场地只表达两侧厨房线统计对照，不表示逐帧站位</p>
      </div>
      {isLoading ? <p className="mt-5 text-sm text-slate-500">正在读取厨房线到位产物…</p> : null}
      {!isLoading && players.length > 0 ? (
        <div className="mt-5 grid gap-4">
          {(["A", "B"] as const).map((team) => {
            const teamPlayers = players.filter((player) => player.team_id === team);
            if (!teamPlayers.length) return null;
            return (
              <div key={team}>
                <div className="mb-2 flex items-center gap-2 text-xs font-black text-slate-600">
                  <span className="size-2 rounded-full" style={{ backgroundColor: TEAM_COLORS[team] }} />
                  Team {team} 发球
                </div>
                <div className="grid gap-2">
                  {teamPlayers.map((player) => {
                    const percent = showPercent(player) ? Math.round((player.arrival_rate ?? 0) * 100) : null;
                    return (
                      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3" key={player.player_id}>
                        <div>
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <span className="font-bold text-[#14241B]">
                              {player.player_id.replace("Player_", "P")}{player.display_name ? ` · ${player.display_name}` : ""}
                            </span>
                            <span className="text-slate-500">{stateLabel(player)}</span>
                          </div>
                          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                            {percent !== null ? <div className="h-full rounded-full" style={{ width: `${percent}%`, backgroundColor: TEAM_COLORS[team] }} /> : null}
                          </div>
                        </div>
                        <span className="min-w-12 text-right text-lg font-black" style={{ color: percent === null ? "#94A3B8" : TEAM_COLORS[team] }}>
                          {percent === null ? "—" : `${percent}%`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
      {!isLoading && !players.length ? (
        <p className="mt-5 text-sm leading-6 text-slate-500" data-testid="kitchen-arrival-empty">
          {loadState === "failed"
            ? "厨房线到位产物读取失败；视频与其他可视化仍可继续使用。"
            : artifact?.detail || detail || (effectiveStatus === "not_applicable" ? "单打任务不适用该指标。" : "冻结身份或轨迹证据不足，暂不展示百分比。")}
        </p>
      ) : null}
      {artifact?.status === "insufficient_evidence" && artifact.detail ? <p className="mt-3 text-xs text-amber-700">{artifact.detail}</p> : null}
    </article>
  );
}

export default KitchenArrivalCard;
