import { useState } from "react";
import type { PlayerScore } from "../../types/report";
import { PLAYER_SCORE_DIMENSIONS } from "../../types/report";
import { MOCK_PLAYER_SCORES } from "../../data/mockPlayerScores";
import { formatPlayerId, playerColor } from "../../utils/analysisHelpers";
import { RadarChart } from "./RadarChart";

interface PlayerScoringPanelProps {
  /** canonical 球员 id 列表（`Player_1`..`Player_4`），按自然序传入。 */
  roster: string[];
  /** 按 canonical 球员 id 索引的评分；缺省回退演示 mock。 */
  scores?: Record<string, PlayerScore>;
}

/**
 * 球员六维雷达评分面板：左侧六轴雷达图，右侧 P1-P4 切换 tab + 分值列表 + 均分。
 * 评分键为 canonical player id；未传 scores 时使用演示 mock 并标注"演示数据"。
 */
export function PlayerScoringPanel({ roster, scores }: PlayerScoringPanelProps) {
  const resolvedScores = scores ?? MOCK_PLAYER_SCORES;
  const isMock = scores === undefined;
  const [selectedPlayerId, setSelectedPlayerId] = useState<string>(roster[0] ?? "");
  const selectedId = roster.includes(selectedPlayerId) ? selectedPlayerId : (roster[0] ?? "");
  const selected = selectedId ? (resolvedScores[selectedId] ?? null) : null;

  if (roster.length === 0) {
    return (
      <section className="sport-card p-5 sm:p-6">
        <p className="text-sm font-semibold leading-6 text-slate-500">暂无球员评分数据。</p>
      </section>
    );
  }

  const values = selected ? PLAYER_SCORE_DIMENSIONS.map((dimension) => selected[dimension.key]) : [];
  const average =
    selected && values.length === PLAYER_SCORE_DIMENSIONS.length
      ? (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1)
      : null;

  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">球员评分</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">六维雷达评分</h2>
        </div>
        {isMock ? (
          <span className="rounded-full bg-[#FF9500]/14 px-3 py-1 text-xs font-black text-[#A45A00]">演示数据</span>
        ) : null}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)]">
        <div className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
          {selected && values.length === PLAYER_SCORE_DIMENSIONS.length ? (
            <RadarChart color={playerColor(selected.player_id)} values={values} />
          ) : (
            <p className="py-16 text-center text-sm font-semibold leading-6 text-slate-500">暂无该球员评分</p>
          )}
        </div>

        <div className="grid content-start gap-4">
          {/* 球员切换 tab（P1-P4，自适应） */}
          <div className="flex flex-wrap gap-2">
            {roster.map((playerId) => {
              const isSelected = playerId === selectedId;
              return (
                <button
                  className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-black transition ${
                    isSelected
                      ? "border-[#168A34] bg-[#22C55E]/12 text-[#14241B] shadow-sm"
                      : "border-[#DDE9D6] bg-white/80 text-slate-600 hover:border-[#22C55E]/60"
                  }`}
                  key={playerId}
                  onClick={() => setSelectedPlayerId(playerId)}
                  type="button"
                >
                  <span className="size-2.5 rounded-full" style={{ backgroundColor: playerColor(playerId) }} />
                  {formatPlayerId(playerId) || playerId}
                </button>
              );
            })}
          </div>

          {/* 选中球员分值列表 */}
          {selected ? (
            <div className="rounded-3xl border border-[#DDE9D6] bg-white/78 p-4">
              <div className="flex items-center justify-between gap-3">
                <strong className="text-base font-black text-[#14241B]">
                  {formatPlayerId(selected.player_id) || selected.player_id}
                </strong>
                {average !== null ? <span className="text-sm font-black text-[#168A34]">均分 {average}</span> : null}
              </div>
              <dl className="mt-3 grid gap-2 text-sm">
                {PLAYER_SCORE_DIMENSIONS.map((dimension) => (
                  <div className="flex items-center justify-between gap-3" key={dimension.key}>
                    <dt className="font-semibold text-slate-600">{dimension.label}</dt>
                    <dd className="font-black tabular-nums text-[#14241B]">{selected[dimension.key].toFixed(1)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
