import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScatterChart } from "echarts/charts";
import type { RecoveryEpisode } from "../../../types/multiviewObservability";

// jsdom 无 canvas，真实 EChart 不绑定事件；stub 掉渲染层以捕获 onEvents 与 option，
// 保留 VIZ_PALETTE / REGISTERED_ECHART_MODULES 真实导出供契约断言。
vi.mock("./EChart", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./EChart")>();
  return {
    ...actual,
    EChart: vi.fn(() => null),
  };
});

import { EChart, REGISTERED_ECHART_MODULES } from "./EChart";
import { RecoveryTimeline, buildRecoveryTimelineOption } from "./recoveryTimeline";

interface ScatterPoint {
  value: number[];
  itemStyle: { color: string; opacity: number; borderColor: string; borderWidth: number };
}

function makeEpisodes(count: number): RecoveryEpisode[] {
  return Array.from({ length: count }, (_, index) => ({
    recovery_episode_id: `re_${index}`,
    start_ms: index * 1000,
    end_ms: index * 1000 + 500,
    global_player_id: `global_${index % 3}`,
    donor_view: "cam_1",
    target_view: "cam_2",
    outcome: index % 2 === 0 ? "guided_recovery_success" : "guidance_failed",
    guidance_attempts: 1,
    pre_gate_rejections: 0,
    lock_rejections: 0,
    debug_video_seek_ms: index * 1000 + 100,
  }));
}

function lastEChartProps() {
  const calls = vi.mocked(EChart).mock.calls;
  const props = calls[calls.length - 1][0];
  return { ...props, onEvents: props.onEvents ?? {} };
}

function firstSeries(option: unknown) {
  const series = (option as { series: Array<{ type: string; data: ScatterPoint[] }> }).series[0];
  return series;
}

describe("buildRecoveryTimelineOption 契约", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("contract A：option 声明 scatter series 且数据点与 episodes 一一对应", () => {
    const episodes = makeEpisodes(5);
    const option = buildRecoveryTimelineOption(episodes);
    expect(option).not.toBeNull();
    const series = firstSeries(option);
    expect(series.type).toBe("scatter");
    expect(series.data).toHaveLength(episodes.length);
    // 每个数据点 value[2] 回填 episode 索引，点击定位依赖该契约
    series.data.forEach((point, index) => {
      expect(point.value[2]).toBe(index);
    });
  });

  it("空 episodes 返回 null option（由组件渲染占位，而非空坐标系）", () => {
    expect(buildRecoveryTimelineOption([])).toBeNull();
  });

  it("contract B：运行时按需注册集合包含 ScatterChart", () => {
    // 「option 合法但运行时未注册」类回归（坐标轴在、散点消失）由该断言兜底
    expect(REGISTERED_ECHART_MODULES).toContain(ScatterChart);
  });
});

describe("RecoveryTimeline 点击定位与高亮", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("value 形态：onSeek 收到 episodes[57]，且该点更新为选中样式", () => {
    const episodes = makeEpisodes(60);
    const onSeek = vi.fn();
    render(<RecoveryTimeline episodes={episodes} debugAvailable onSeek={onSeek} />);
    const initial = lastEChartProps();
    act(() => {
      initial.onEvents.click({ value: [12.3, 0, 57] });
    });
    expect(onSeek).toHaveBeenCalledTimes(1);
    expect(onSeek).toHaveBeenCalledWith(episodes[57]);
    const after = lastEChartProps();
    const series = firstSeries(after.option);
    expect(series.data[57].itemStyle.borderColor).toBe("#14241B");
    expect(series.data[57].itemStyle.borderWidth).toBe(3);
    expect(series.data[0].itemStyle.borderColor).toBe("#FFFFFF");
  });

  it("params.data.value 形态兼容：同样定位到 episodes[57]", () => {
    const episodes = makeEpisodes(60);
    const onSeek = vi.fn();
    render(<RecoveryTimeline episodes={episodes} debugAvailable onSeek={onSeek} />);
    const initial = lastEChartProps();
    act(() => {
      initial.onEvents.click({ data: { value: [12.3, 1, 57], itemStyle: { color: "#A32D2D" } } });
    });
    expect(onSeek).toHaveBeenCalledTimes(1);
    expect(onSeek).toHaveBeenCalledWith(episodes[57]);
  });

  it("越界/负数 index：不报错、不选中、不触发 onSeek", () => {
    const episodes = makeEpisodes(60);
    const onSeek = vi.fn();
    render(<RecoveryTimeline episodes={episodes} debugAvailable onSeek={onSeek} />);
    const callsBefore = vi.mocked(EChart).mock.calls.length;
    expect(() =>
      act(() => {
        lastEChartProps().onEvents.click({ value: [12.3, 0, 999] });
      }),
    ).not.toThrow();
    expect(() =>
      act(() => {
        lastEChartProps().onEvents.click({ value: [12.3, 0, -1] });
      }),
    ).not.toThrow();
    expect(onSeek).not.toHaveBeenCalled();
    // 无选中状态变化 → 不重渲染
    expect(vi.mocked(EChart).mock.calls.length).toBe(callsBefore);
  });

  it("debug 不可用时点击仅高亮，不调用 onSeek", () => {
    const episodes = makeEpisodes(60);
    const onSeek = vi.fn();
    render(<RecoveryTimeline episodes={episodes} debugAvailable={false} onSeek={onSeek} />);
    const initial = lastEChartProps();
    act(() => {
      initial.onEvents.click({ value: [12.3, 0, 57] });
    });
    expect(onSeek).not.toHaveBeenCalled();
    const series = firstSeries(lastEChartProps().option);
    expect(series.data[57].itemStyle.borderColor).toBe("#14241B");
  });

  it("episodes 为空时渲染占位说明而不是空坐标系", () => {
    render(<RecoveryTimeline episodes={[]} debugAvailable={false} />);
    expect(vi.mocked(EChart).mock.calls.length).toBe(0);
    expect(document.body.textContent).toContain("当前没有可展示的恢复事件时间线数据");
  });
});
