import { useMemo } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import {
  mockServeReturnDepth,
  mockServeReturnStats,
} from "../../utils/pbMockData";
import type { PbDepthDistribution } from "../../types/pbReport";
import { EChart } from "../platform/viz/EChart";
import type { EChartsCoreOption } from "echarts/core";

const DEEP_COLOR = "#00FF41";
const MEDIUM_COLOR = "#FBBF24";
const SHALLOW_COLOR = "#F97316";
const NET_COLOR = "#E879F9";
const IN_COLOR = "var(--pb-primary,#00FF41)";

interface BarRowProps {
  label: string;
  serve: PbDepthDistribution;
  return_: PbDepthDistribution;
}

function DepthBars({ label, serve, return_ }: BarRowProps) {
  const total = serve.deep + serve.medium + serve.shallow;
  const totalR = return_.deep + return_.medium + return_.shallow;

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-[var(--pb-text-secondary,#6b7280)]">
        {label}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="w-16 text-xs text-[var(--pb-text-primary,#111827)]">
            发球
          </span>
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-[var(--pb-text-muted,#9ca3af)]">
                深区
              </span>
              <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${total ? (serve.deep / total) * 100 : 0}%`,
                    backgroundColor: DEEP_COLOR,
                  }}
                />
              </div>
              <span className="w-10 text-right text-xs tabular-nums text-[var(--pb-text-secondary,#6b7280)]">
                {serve.deep}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-[var(--pb-text-muted,#9ca3af)]">
                中区
              </span>
              <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${total ? (serve.medium / total) * 100 : 0}%`,
                    backgroundColor: MEDIUM_COLOR,
                  }}
                />
              </div>
              <span className="w-10 text-right text-xs tabular-nums text-[var(--pb-text-secondary,#6b7280)]">
                {serve.medium}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-[var(--pb-text-muted,#9ca3af)]">
                浅区
              </span>
              <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${total ? (serve.shallow / total) * 100 : 0}%`,
                    backgroundColor: SHALLOW_COLOR,
                  }}
                />
              </div>
              <span className="w-10 text-right text-xs tabular-nums text-[var(--pb-text-secondary,#6b7280)]">
                {serve.shallow}%
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="w-16 text-xs text-[var(--pb-text-primary,#111827)]">
            接发
          </span>
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-[var(--pb-text-muted,#9ca3af)]">
                深区
              </span>
              <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${totalR ? (return_.deep / totalR) * 100 : 0}%`,
                    backgroundColor: DEEP_COLOR,
                  }}
                />
              </div>
              <span className="w-10 text-right text-xs tabular-nums text-[var(--pb-text-secondary,#6b7280)]">
                {return_.deep}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-[var(--pb-text-muted,#9ca3af)]">
                中区
              </span>
              <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${totalR ? (return_.medium / totalR) * 100 : 0}%`,
                    backgroundColor: MEDIUM_COLOR,
                  }}
                />
              </div>
              <span className="w-10 text-right text-xs tabular-nums text-[var(--pb-text-secondary,#6b7280)]">
                {return_.medium}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-[var(--pb-text-muted,#9ca3af)]">
                浅区
              </span>
              <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${totalR ? (return_.shallow / totalR) * 100 : 0}%`,
                    backgroundColor: SHALLOW_COLOR,
                  }}
                />
              </div>
              <span className="w-10 text-right text-xs tabular-nums text-[var(--pb-text-secondary,#6b7280)]">
                {return_.shallow}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DepthDonut({
  label,
  depth,
  centerText,
}: {
  label: string;
  depth: PbDepthDistribution;
  centerText: string;
}) {
  const option = useMemo<EChartsCoreOption>(() => {
    return {
      tooltip: {
        trigger: "item",
        formatter: "{b}: {c}%",
      },
      legend: {
        bottom: 0,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { fontSize: 10, color: "#6b7280" },
      },
      title: {
        text: centerText,
        left: "center",
        top: "42%",
        textStyle: {
          fontSize: 11,
          fontWeight: 600,
          color: "#111827",
        },
      },
      series: [
        {
          name: label,
          type: "pie",
          radius: ["60%", "80%"],
          center: ["50%", "45%"],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 2,
            borderColor: "#fff",
            borderWidth: 1,
          },
          label: { show: false },
          labelLine: { show: false },
          emphasis: {
            scale: true,
            scaleSize: 3,
          },
          data: [
            {
              name: "深区",
              value: depth.deep,
              itemStyle: { color: DEEP_COLOR },
            },
            {
              name: "中区",
              value: depth.medium,
              itemStyle: { color: MEDIUM_COLOR },
            },
            {
              name: "浅区",
              value: depth.shallow,
              itemStyle: { color: SHALLOW_COLOR },
            },
          ],
        },
      ],
    };
  }, [label, depth, centerText]);

  return (
    <div className="w-full">
      <EChart option={option} height={180} />
    </div>
  );
}

export default function PbServesReturns() {
  const { selectedPlayerId } = usePbReport();

  const { serves, returns } = useMemo(
    () => mockServeReturnStats(selectedPlayerId),
    [selectedPlayerId]
  );
  const { serve, return_ } = useMemo(
    () => mockServeReturnDepth(selectedPlayerId),
    [selectedPlayerId]
  );

  const serveInPct = serves.total
    ? Math.round((serves.in / serves.total) * 100)
    : 0;
  const returnInPct = returns.total
    ? Math.round((returns.in / returns.total) * 100)
    : 0;
  const returnNetPct = returns.total
    ? (returns.net / returns.total) * 100
    : 0;
  const returnOutPct = Math.max(0, 100 - returnInPct - returnNetPct);

  return (
    <div className="pb-card p-5 sm:p-6">
      <h3 className="font-bold text-lg text-[var(--pb-text-primary,#111827)]">
        发球与接发
      </h3>

      <div className="mt-5 space-y-5">
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold text-[var(--pb-text-primary,#111827)]">
              发球进区/出界
            </div>
            <div className="text-sm text-[var(--pb-text-secondary,#6b7280)]">
              总计：<span className="font-bold">{serves.total}</span>
            </div>
          </div>
          <div className="w-full h-[10px] bg-slate-200 rounded-full overflow-hidden flex">
            <div
              className="h-full flex items-center justify-end pr-2 text-[10px] font-bold text-[#052e16] rounded-full"
              style={{
                width: `${serveInPct}%`,
                backgroundColor: IN_COLOR,
              }}
            >
              {serveInPct >= 15 ? `进区 (${serveInPct}%)` : ""}
            </div>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold text-[var(--pb-text-primary,#111827)]">
              接发进区/出界
            </div>
            <div className="text-sm text-[var(--pb-text-secondary,#6b7280)]">
              总计：<span className="font-bold">{returns.total}</span>
            </div>
          </div>
          <div className="w-full h-[10px] bg-slate-200 rounded-full overflow-hidden flex">
            <div
              className="h-full flex items-center justify-end pr-2 text-[10px] font-bold text-[#052e16] rounded-l-full"
              style={{
                width: `${returnInPct}%`,
                backgroundColor: IN_COLOR,
              }}
            >
              {returnInPct >= 20 ? `进区 (${returnInPct}%)` : ""}
            </div>
            <div
              className="h-full flex items-center justify-center text-[10px] font-bold text-white"
              style={{
                width: `${returnNetPct}%`,
                backgroundColor: NET_COLOR,
              }}
            >
              {returnNetPct >= 10 ? "擦网" : ""}
            </div>
            {returnOutPct > 0 && (
              <div
                className="h-full rounded-r-full"
                style={{
                  width: `${returnOutPct}%`,
                  backgroundColor: "#ef4444",
                }}
              />
            )}
          </div>
        </div>
      </div>

      <div className="my-6 h-px bg-[var(--pb-card-border,#e5e7eb)]" />

      <h4 className="font-semibold text-[var(--pb-text-primary,#111827)]">
        发球与接发深度
      </h4>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DepthBars label="深度分布" serve={serve} return_={return_} />

        <div className="grid grid-cols-2 gap-3">
          <DepthDonut
            label="发球深度"
            depth={serve}
            centerText="发球深度"
          />
          <DepthDonut
            label="接发深度"
            depth={return_}
            centerText="接发深度"
          />
        </div>
      </div>

      <div className="mt-5 flex items-center justify-center gap-5 flex-wrap">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-6 rounded-full"
            style={{ backgroundColor: DEEP_COLOR }}
          />
          <span className="text-xs text-[var(--pb-text-secondary,#6b7280)]">
            深区
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-6 rounded-full"
            style={{ backgroundColor: MEDIUM_COLOR }}
          />
          <span className="text-xs text-[var(--pb-text-secondary,#6b7280)]">
            中区
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-6 rounded-full"
            style={{ backgroundColor: SHALLOW_COLOR }}
          />
          <span className="text-xs text-[var(--pb-text-secondary,#6b7280)]">
            浅区
          </span>
        </div>
      </div>
    </div>
  );
}
