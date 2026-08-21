import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart, FunnelChart, GaugeChart, HeatmapChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, TitleComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";

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

/** 项目语义色（与页面绿/黄/红/灰一致）。 */
export const VIZ_PALETTE = {
  green: "#3B6D11",
  greenLight: "#EAF3DE",
  amber: "#BA7517",
  amberLight: "#FAEEDA",
  red: "#A32D2D",
  redLight: "#FCEBEB",
  gray: "#888780",
  grayLight: "#F1EFE8",
  teal: "#0F6E56",
  blue: "#185FA5",
  text: "#14241B",
} as const;

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
 * ECharts 轻量封装：初始化、setOption、resize 与 dispose 生命周期托管。
 * jsdom / canvas 不可用时优雅降级为占位说明，不影响测试与降级场景。
 */
export function EChart({ option, height = 260, ariaLabel, testId, fallbackText = "图表渲染不可用", onEvents }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

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
      chart.setOption(option);
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
  }, [option, onEvents]);

  return (
    <div aria-label={ariaLabel} className="w-full" data-testid={testId} role="img">
      <div ref={containerRef} style={{ height, width: "100%" }} />
      {failed ? <p className="px-2 pb-2 text-xs text-slate-500">{fallbackText}</p> : null}
    </div>
  );
}
