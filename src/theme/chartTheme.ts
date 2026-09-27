/**
 * 图表界面色：ECharts 的画布、轴线、标签、图例与提示框属于界面色，
 * 必须随主题生成；系列数据色保留语义（见 `getVizPalette`）。
 */

import type { ThemeMode } from "./theme";

export interface ChartTheme {
  /** 图表内文字（标题、数值标签） */
  text: string;
  /** 坐标轴刻度文字 */
  axisLabel: string;
  /** 坐标轴线 */
  axisLine: string;
  /** 网格分割线 */
  splitLine: string;
  /** 图例文字 */
  legendText: string;
  /** 提示框底色 / 描边 / 文字 */
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
}

const LIGHT: ChartTheme = {
  text: "#14241b",
  axisLabel: "#64748b",
  axisLine: "#dde9d6",
  splitLine: "#eef2f0",
  legendText: "#475569",
  tooltipBg: "#ffffff",
  tooltipBorder: "#dde9d6",
  tooltipText: "#14241b",
};

const DARK: ChartTheme = {
  text: "#e8efea",
  axisLabel: "#93a29c",
  axisLine: "#2a352f",
  splitLine: "#232e28",
  legendText: "#b0bfba",
  tooltipBg: "#1b2420",
  tooltipBorder: "#3a4a41",
  tooltipText: "#e8efea",
};

export function getChartTheme(mode: ThemeMode): ChartTheme {
  return mode === "dark" ? DARK : LIGHT;
}

/** 项目数据语义色：暗色下提亮以在深底上保持可辨，色相关系不变。 */
export interface VizPalette {
  green: string;
  greenLight: string;
  amber: string;
  amberLight: string;
  red: string;
  redLight: string;
  gray: string;
  grayLight: string;
  teal: string;
  blue: string;
  text: string;
}

export const VIZ_PALETTE_LIGHT: VizPalette = {
  green: "#3b6d11",
  greenLight: "#eaf3de",
  amber: "#ba7517",
  amberLight: "#faeeda",
  red: "#a32d2d",
  redLight: "#fcebeb",
  gray: "#888780",
  grayLight: "#f1efe8",
  teal: "#0f6e56",
  blue: "#185fa5",
  text: "#14241b",
};

export const VIZ_PALETTE_DARK: VizPalette = {
  green: "#7fc98d",
  greenLight: "#16281a",
  amber: "#f0b357",
  amberLight: "#2e2413",
  red: "#ff6b5e",
  redLight: "#331518",
  gray: "#8b9691",
  grayLight: "#1a211e",
  teal: "#4fc0a5",
  blue: "#7ea2ff",
  text: "#e8efea",
};

export function getVizPalette(mode: ThemeMode): VizPalette {
  return mode === "dark" ? VIZ_PALETTE_DARK : VIZ_PALETTE_LIGHT;
}
