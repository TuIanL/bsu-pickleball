import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { getPlayerDisplayDiagnostics } from "../../../services/analysisClient";
import type { PlayerDisplayDiagnosticsRow } from "../../../types/report";
import { EChart, VIZ_PALETTE } from "./EChart";
import { STAGE_LABELS } from "./observabilityCharts";

/** 热力图分段拉取窗口（ms）。 */
const FETCH_WINDOW_MS = 2000;
/** 最大拉取段数（防止未知视频长度无限请求；40 段 ≈ 80s 视频）。 */
const MAX_SEGMENTS = 40;

/** 每行 stage 提取：返回 true / false / null（未触发）。 */
const STAGE_FIELDS: Array<[keyof PlayerDisplayDiagnosticsRow, string]> = [
  ["expected_region_status", "期望区域"],
  ["eligible_detections_in_expected_gate", "门内候选"],
  ["eligible_detection_present", "有检测框"],
  ["position_present", "有位置"],
  ["court_position_present", "球场投影"],
  ["formal_observation_emitted", "正式观测"],
  ["global_associated", "全局关联"],
  ["binding_visibility", "绑定可见性"],
  ["available_miss_streak", "连续漏检"],
];

function stageValue(row: PlayerDisplayDiagnosticsRow, field: keyof PlayerDisplayDiagnosticsRow): boolean | null {
  const value = row[field];
  switch (field) {
    case "expected_region_status":
      return value === "available";
    case "eligible_detections_in_expected_gate":
      return typeof value === "number" ? value > 0 : value != null;
    case "binding_visibility":
      return typeof value === "string" && value.length > 0 ? value === "observed" : null;
    case "available_miss_streak":
      return typeof value === "number" ? value <= 0 : null;
    default:
      return typeof value === "boolean" ? value : null;
  }
}

/** 聚合为 (stage × tick) 状态矩阵：1=通过 2=卡住 0=未触发。 */
export function buildHeatmapMatrix(rows: PlayerDisplayDiagnosticsRow[]): { ticks: number[]; matrix: number[][]; rowsByTick: Map<number, PlayerDisplayDiagnosticsRow[]> } {
  const ticks = Array.from(new Set(rows.map((row) => row.canonical_tick))).sort((a, b) => a - b);
  const rowsByTick = new Map<number, PlayerDisplayDiagnosticsRow[]>();
  for (const row of rows) {
    const bucket = rowsByTick.get(row.canonical_tick) ?? [];
    bucket.push(row);
    rowsByTick.set(row.canonical_tick, bucket);
  }
  const matrix: number[][] = ticks.map((tick) => {
    const bucket = rowsByTick.get(tick) ?? [];
    return STAGE_FIELDS.map(([field]) => {
      const values = bucket.map((row) => stageValue(row, field)).filter((value): value is boolean => value !== null);
      if (values.length === 0) return 0;
      // 双视角聚合：任一视角可用即视为通过（细节保留在 tick 详情面板）
      return values.some((value) => value) ? 1 : 2;
    });
  });
  return { ticks, matrix, rowsByTick };
}

interface DisplayHeatmapProps {
  jobId: string;
  /** Debug Replay 可用时，点击格子定位到该 tick 时间。 */
  onSeek?: (timestampMs: number) => void;
  /** Debug Replay 是否可用（决定点击是否定位视频）。 */
  debugAvailable: boolean;
}

/**
 * 球员显示诊断热力图：按窗口分段拉取该球员全部诊断行，聚合成
 * (9 阶段 × tick) 矩阵渲染热力图；点击格子展示该 tick 详情并可选定位视频。
 */
export function DisplayHeatmap({ jobId, onSeek, debugAvailable }: DisplayHeatmapProps) {
  const [playerId, setPlayerId] = useState("Player_1");
  const [rows, setRows] = useState<PlayerDisplayDiagnosticsRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTick, setSelectedTick] = useState<number | null>(null);
  const requestSeq = useRef(0);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    setSelectedTick(null);
    const collected: PlayerDisplayDiagnosticsRow[] = [];
    const fetchSegment = (segment: number): Promise<void> => {
      return getPlayerDisplayDiagnostics(jobId, playerId, segment * FETCH_WINDOW_MS, FETCH_WINDOW_MS)
        .then((response) => {
          if (seq !== requestSeq.current) return;
          collected.push(...(response.rows ?? []));
          const emptyWindow = (response.rows?.length ?? 0) === 0;
          if (segment + 1 < MAX_SEGMENTS && !emptyWindow) {
            return fetchSegment(segment + 1);
          }
          return undefined;
        })
        .catch((reason: unknown) => {
          if (seq !== requestSeq.current) return;
          setError(reason instanceof Error ? reason.message : "读取显示诊断失败");
        });
    };
    fetchSegment(0).finally(() => {
      if (seq === requestSeq.current) {
        setRows(collected);
        setLoading(false);
      }
    });
  }, [jobId, playerId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 依赖变化时触发重新加载
    load();
  }, [load]);

  const { ticks, matrix, rowsByTick } = useMemo(() => buildHeatmapMatrix(rows), [rows]);

  const option = useMemo<EChartsCoreOption | null>(() => {
    if (ticks.length === 0) return null;
    const data: Array<[number, number, number]> = [];
    matrix.forEach((row, tickIndex) => {
      row.forEach((value, stageIndex) => {
        if (value !== 0) data.push([tickIndex, stageIndex, value]);
      });
    });
    return {
      grid: { left: 78, right: 24, top: 12, bottom: 64 },
      tooltip: {
        formatter: (params: { data: [number, number, number] }) => {
          const [tickIndex, stageIndex, value] = params.data;
          const tick = ticks[tickIndex];
          const stage = STAGE_LABELS[stageIndex];
          const stateLabel = value === 1 ? "通过" : "卡住";
          const bucket = rowsByTick.get(tick) ?? [];
          const reason = bucket.map((row) => row.association_reason ?? row.guidance_skip_reason ?? row.frame_status).filter(Boolean).join(" · ");
          return `${stage} @ tick ${tick}（${bucket[0]?.timestamp_ms != null ? Math.round(bucket[0].timestamp_ms) : tick}ms）<br/>${stateLabel}${reason ? `<br/>原因：${reason}` : ""}`;
        },
      },
      xAxis: {
        type: "category",
        data: ticks.map((tick) => tick),
        name: "tick",
        axisLabel: { color: "#64748B", rotate: 45, interval: "auto" },
        splitArea: { show: false },
      },
      yAxis: { type: "category", data: STAGE_LABELS, axisLabel: { color: "#475569", fontSize: 11 }, splitArea: { show: true } },
      visualMap: {
        min: 1,
        max: 2,
        show: false,
        inRange: { color: [VIZ_PALETTE.green, "#F09595"] },
      },
      series: [
        {
          type: "heatmap",
          data,
          label: { show: false },
          itemStyle: { borderColor: "#FFFFFF", borderWidth: 1, borderRadius: 1 },
          emphasis: { itemStyle: { borderColor: "#14241B", borderWidth: 2 } },
        },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: 0 },
        { type: "slider", xAxisIndex: 0, bottom: 8, height: 18, borderColor: "#E7EFE2", textStyle: { color: "#64748B" } },
      ],
    };
  }, [matrix, rowsByTick, ticks]);

  const handleClick = useCallback(
    (params: unknown) => {
      const data = (params as { data?: [number, number, number] }).data ?? (params as { value?: [number, number, number] }).value;
      if (!data) return;
      const tick = ticks[data[0]];
      if (tick == null) return;
      setSelectedTick(tick);
      const bucket = rowsByTick.get(tick) ?? [];
      if (debugAvailable && onSeek && bucket.length > 0) {
        onSeek(bucket[0].timestamp_ms ?? 0);
      }
    },
    [debugAvailable, onSeek, rowsByTick, ticks],
  );

  const selectedRows = selectedTick != null ? rowsByTick.get(selectedTick) ?? [] : [];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="text-xs font-bold text-slate-500">球员
          <select aria-label="球员" className="field-input mt-1 block py-2" value={playerId} onChange={(event) => setPlayerId(event.target.value)}>
            {["Player_1", "Player_2", "Player_3", "Player_4"].map((pid) => <option key={pid} value={pid}>{pid}</option>)}
          </select>
        </label>
        <span className="text-xs text-slate-500">{loading ? "读取中…" : `${ticks.length} 个 tick · ${rows.length} 行诊断`}</span>
      </div>

      {error ? <p className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}

      {!error && ticks.length === 0 && !loading ? (
        <p className="mt-3 rounded-2xl border border-dashed border-[#DDE9D6] bg-[#F7FBF5] p-5 text-sm text-slate-600">该球员没有可用的显示诊断行（窗口内无数据或产物不存在）。</p>
      ) : null}

      {!error && ticks.length > 0 ? (
        <>
          <div className="mt-3">
            <EChart ariaLabel={`${playerId} 显示诊断热力图`} height={280} onEvents={{ click: handleClick }} option={option ?? {}} testId="display-diagnostics-heatmap" />
          </div>
          <div className="mt-1 flex items-center gap-4 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm" style={{ backgroundColor: VIZ_PALETTE.green }} aria-hidden="true" />通过</span>
            <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm" style={{ backgroundColor: "#F09595" }} aria-hidden="true" />卡住</span>
            <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm border border-[#D3D1C7] bg-[#F1EFE8]" aria-hidden="true" />未触发</span>
            {debugAvailable ? <span className="ml-auto">点击格子可定位到 Debug Replay</span> : null}
          </div>
        </>
      ) : null}

      {selectedTick != null ? (
        <div className="mt-4 rounded-2xl border border-[#DDE9D6] bg-white" data-testid="tick-detail-panel">
          <div className="flex items-center justify-between border-b border-[#E7EFE2] px-4 py-2.5">
            <span className="text-xs font-black tracking-[0.14em] text-slate-500">tick {selectedTick} 详情{selectedRows[0]?.timestamp_ms != null ? ` · ${Math.round(selectedRows[0].timestamp_ms)}ms` : ""}</span>
            <button className="text-xs font-bold text-slate-400 hover:text-slate-600" onClick={() => setSelectedTick(null)} type="button">关闭</button>
          </div>
          <div className="grid gap-x-4 gap-y-1.5 px-4 py-3 sm:grid-cols-2">
            {selectedRows.map((row) => (
              <div className="rounded-xl bg-[#F7FBF5] px-3 py-2.5" key={`${row.view_id}-${row.canonical_tick}`}>
                <p className="text-xs font-black text-slate-500">{row.view_id}</p>
                <div className="mt-1.5 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                  {STAGE_FIELDS.map(([field, label]) => {
                    const value = stageValue(row, field);
                    const display = value === null ? "未触发" : value ? "是" : "否";
                    const emphasized = field === "formal_observation_emitted" || field === "global_associated";
                    return <div className="flex items-center justify-between gap-2" key={field}><span className="text-slate-500">{label}</span><strong className={emphasized && value ? "text-[#168A34]" : "text-[#14241B]"}>{display}</strong></div>;
                  })}
                </div>
                {row.association_reason ? <p className="mt-2 text-xs text-slate-500">关联原因：{row.association_reason}</p> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
