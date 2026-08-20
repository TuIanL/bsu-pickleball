import { useCallback, useMemo, useState } from "react";
import type { EChartsCoreOption }  from "echarts/core";
import type { RecoveryEpisode, RecoveryOutcome } from "../../../types/multiviewObservability";
import { EChart, VIZ_PALETTE } from "./EChart";

const OUTCOME_META: Record<RecoveryOutcome, { label: string; color: string }> = {
  guided_recovery_success: { label: "引导恢复成功", color: VIZ_PALETTE.green },
  base_recovered: { label: "基础观测自恢复", color: VIZ_PALETTE.teal },
  guidance_failed: { label: "引导未成功", color: VIZ_PALETTE.red },
  pre_gate_rejected: { label: "前置门拒绝", color: VIZ_PALETTE.amber },
  lock_rejected: { label: "锁定拒绝", color: VIZ_PALETTE.amber },
  global_mismatch: { label: "全局身份不匹配", color: "#7F77DD" },
};

const OUTCOME_ORDER = Object.keys(OUTCOME_META) as RecoveryOutcome[];

interface RecoveryTimelineProps {
  episodes: RecoveryEpisode[];
  /** 点击事件定位 Debug Replay（debug 可用时）。 */
  onSeek?: (episode: RecoveryEpisode) => void;
  debugAvailable: boolean;
}

/**
 * 从 ECharts 点击事件的 params 中解析 episode 索引。
 * ECharts 点击事件的 params 可能是 `{ value: [...] }` 或 `{ data: { value: [...] } }`，
 * 且 value 形如 `[startSec, outcomeIndex, episodeIndex]`。
 */
export function resolveEpisodeIndex(params: unknown): number | undefined {
  const p = params as { value?: unknown; data?: { value?: unknown } };
  const raw = Array.isArray(p.value) ? p.value : p.data?.value;
  const index = Array.isArray(raw) ? raw[2] : undefined;
  return typeof index === "number" && Number.isInteger(index) && index >= 0 ? index : undefined;
}

/** 构建恢复事件时间线的 ECharts option（纯函数，便于测试）。 */
export function buildRecoveryTimelineOption(episodes: RecoveryEpisode[], selectedIndex?: number): EChartsCoreOption | null {
  if (episodes.length === 0) return null;
  return {
    grid: { left: 96, right: 24, top: 16, bottom: 48 },
    tooltip: {
      formatter: (params: { dataIndex: number }) => {
        const episode = episodes[params.dataIndex];
        if (!episode) return "";
        const meta = OUTCOME_META[episode.outcome];
        const durationSec = ((episode.end_ms ?? episode.start_ms) - episode.start_ms) / 1000;
        return `${meta.label}<br/>起始 ${(episode.start_ms / 1000).toFixed(1)}s · 持续 ${durationSec.toFixed(1)}s${episode.target_view ? `<br/>目标 ${episode.target_view} · 供体 ${episode.donor_view ?? "-"}` : ""}<br/>引导尝试 ${episode.guidance_attempts}`;
      },
    },
    xAxis: { type: "value", name: "s", nameTextStyle: { color: "#94A3B8" }, axisLabel: { color: "#64748B" }, splitLine: { lineStyle: { color: "#E7EFE2" } } },
    // 固定 6 个 outcome 类别占位，与图例一一对应（空类也显示，避免"看似没有数据"）
    yAxis: { type: "category", data: OUTCOME_ORDER.map((outcome) => OUTCOME_META[outcome].label), axisLabel: { color: "#475569", fontSize: 11 } },
    series: [
      {
        type: "scatter",
        data: episodes.map((episode, index) => ({
          value: [Number((episode.start_ms / 1000).toFixed(2)), OUTCOME_ORDER.indexOf(episode.outcome), index],
          itemStyle: {
            color: OUTCOME_META[episode.outcome].color,
            opacity: 0.9,
            borderColor: index === selectedIndex ? "#14241B" : "#FFFFFF",
            borderWidth: index === selectedIndex ? 3 : 1.5,
          },
        })),
        symbolSize: (value: number[]) => {
          const episode = episodes[value[ 2]];
          const durationSec = ((episode?.end_ms ?? episode?.start_ms ?? 0) - (episode?.start_ms ?? 0)) / 1000;
          return Math.max(11, Math.min(24, 11 + durationSec * 8));
        },
        label: { show: false },
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: 0 },
      { type: "slider", xAxisIndex: 0, bottom: 8, height: 18, borderColor: "#E7EFE2", textStyle: { color: "#64748B" } },
    ],
  };
}

/**
 * 恢复事件时间线：episodes 按 start_ms 分布，outcome 着色，点击定位视频；
 * 任一 episode 被点击都会更新选中样式，仅当 debug 可用时触发 onSeek。
 */
export function RecoveryTimeline({ episodes, onSeek, debugAvailable }: RecoveryTimelineProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const option = useMemo<EChartsCoreOption | null>(
    () => buildRecoveryTimelineOption(episodes, selectedIndex ?? undefined),
    [episodes, selectedIndex],
  );

  const handleClick = useCallback(
    (params: unknown) => {
      const index = resolveEpisodeIndex(params);
      if (index == null || index >= episodes.length) return;
      setSelectedIndex(index);
      const episode = episodes[index];
      if (debugAvailable && onSeek) onSeek(episode);
    },
    [episodes, debugAvailable, onSeek],
  );

  if (episodes.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[#DDE9D6] bg-[#F7FBF5] p-4 text-sm leading-6 text-slate-600">
        当前没有可展示的恢复事件时间线数据。
      </div>
    );
  }

  return (
    <div>
      <EChart ariaLabel="恢复事件时间线" height={200} onEvents={{ click: handleClick }} option={option ?? {}} testId="recovery-timeline" />
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        {OUTCOME_ORDER.map((outcome) => (
          <span className="inline-flex items-center gap-1" key={outcome}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: OUTCOME_META[outcome].color }} aria-hidden="true" />
            {OUTCOME_META[outcome].label}
          </span>
        ))}
        {debugAvailable ? <span className="ml-auto">点击数据点定位到 Debug Replay</span> : null}
      </div>
    </div>
  );
}
