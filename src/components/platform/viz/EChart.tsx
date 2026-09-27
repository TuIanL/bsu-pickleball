import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart, FunnelChart, GaugeChart, HeatmapChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, TitleComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { useThemeOptional } from "../../../theme/ThemeProvider";
import { getChartTheme, VIZ_PALETTE_LIGHT } from "../../../theme/chartTheme";

// 按需注册：只打包本页使用的图表与组件，控制产物体积
export const REGISTERED_ECHART_MODULES = [
  BarChart,
  FunnelChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  TitleComponent,
  VisualMapComponent,
  CanvasRenderer,
];

echarts.use(REGISTERED_ECHART_MODULES);

/**
 * 项目语义色（与页面绿/黄/红/灰一致）。
 * 仅表示**亮色**取值：随主题变化请使用 `useVizPalette()`。
 */
export const VIZ_PALETTE = VIZ_PALETTE_LIGHT;

interface EChartProps {
  /** ECharts option（调用方应通过 useMemo 保持引用稳定）。 */
  option: EChartsCoreOption;
  /** 图表高度（px 或 CSS 字符串），默认 260。 */
  height?: number | string;
  /** 可访问标签（role=img 的 aria-label）。 */
  ariaLabel?: string;
  /** 测试定位用 data-testid。 */
  testId?: string;
  /** 渲染失败（如 jsdom 无 canvas）时的占位文案。 */
  fallbackText?: string;
  /** 图表事件绑定（如 click），key 为事件名，value 为处理器。 */
  onEvents?: Record<string, (params: unknown) => void>;
}

/**
 * 把主题相关的界面色并入图表 option：文字、坐标轴、网格线、图例与提示框。
 * 调用方显式给出的同名配置优先，未被覆盖的项才回落到主题值。
 */
function withChartTheme(option: EChartsCoreOption, mode: "light" | "dark"): EChartsCoreOption {
  const t = getChartTheme(mode);
  const source = (option ?? {}) as Record<string, unknown>;
  const merged: Record<string, unknown> = { ...source };

  merged.backgroundColor = source.backgroundColor ?? "transparent";
  merged.textStyle = { color: t.text, ...((source.textStyle as object) ?? {}) };

  if (source.tooltip !== false) {
    merged.tooltip = {
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: t.tooltipText },
      ...((source.tooltip as object) ?? {}),
    };
  }

  if (source.legend !== false && !Array.isArray(source.legend)) {
    merged.legend = {
      textStyle: { color: t.legendText },
      ...((source.legend as object) ?? {}),
    };
  }

  const axisDefaults = {
    axisLine: { lineStyle: { color: t.axisLine } },
    axisLabel: { color: t.axisLabel },
    splitLine: { lineStyle: { color: t.splitLine } },
    nameTextStyle: { color: t.axisLabel },
  };

  for (const key of ["xAxis", "yAxis"] as const) {
    const axis = source[key];
    if (axis === undefined || axis === null) continue;
    if (Array.isArray(axis)) {
      merged[key] = axis.map((item) => ({ ...axisDefaults, ...((item as object) ?? {}) }));
    } else {
      merged[key] = { ...axisDefaults, ...(axis as object) };
    }
  }

  return merged as EChartsCoreOption;
}

/**
 * ECharts 轻量封装：初始化、setOption、resize 与 dispose 生命周期托管。
 * jsdom / canvas 不可用时优雅降级为占位说明，不影响测试与降级场景。
 *
 * 主题切换时重新并入界面色并 `setOption`，保证坐标轴、图例、提示框随之更新。
 */
export function EChart({ option, height = 260, ariaLabel, testId, fallbackText = "图表渲染不可用", onEvents }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const { theme } = useThemeOptional();

  const themedOption = useMemo(() => withChartTheme(option, theme), [option, theme]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    let chart: echarts.ECharts | null = null;
    let resizeObserver: ResizeObserver | null = null;
    try {
      // jsdom / 无 canvas 环境：getContext 返回 null，直接降级为占位
      const probe = document.createElement("canvas");
      if (typeof probe.getContext !== "function" || !probe.getContext("2d")) {
        throw new Error("canvas unavailable");
      }
      chart = echarts.init(element);
      chart.setOption(themedOption);
      for (const [eventName, handler] of Object.entries(onEvents ?? {})) {
        chart.on(eventName, handler);
      }
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 初始化成功后清除失败标记
      setFailed(false);
      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => chart?.resize());
        resizeObserver.observe(element);
      }
    } catch {
      setFailed(true);
    }
    return () => {
      try {
        resizeObserver?.disconnect();
      } catch {
        /* ignore */
      }
      if (chart) {
        try {
          for (const [eventName, handler] of Object.entries(onEvents ?? {})) {
            chart.off(eventName, handler);
          }
          chart.dispose();
        } catch {
          /* dispose 在无 canvas 环境下可能抛错，忽略 */
        }
      }
    };
  }, [themedOption, onEvents]);

  return (
    <div aria-label={ariaLabel} className="w-full" data-testid={testId} role="img">
      <div ref={containerRef} style={{ height, width: "100%" }} />
      {failed ? <p className="px-2 pb-2 text-xs text-[var(--ui-text-secondary)]">{fallbackText}</p> : null}
    </div>
  );
}
