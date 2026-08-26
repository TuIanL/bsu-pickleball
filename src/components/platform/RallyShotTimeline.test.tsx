import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import fixture from "../../test/fixtures/shot-rally-events.v1.json";
import type { ShotRallyEventsArtifact } from "../../types/shotRallyEvents";
import { RallyShotTimeline } from "./RallyShotTimeline";

const availableFixture = fixture as unknown as ShotRallyEventsArtifact;

function cloneFixture(): ShotRallyEventsArtifact {
  return JSON.parse(JSON.stringify(availableFixture)) as ShotRallyEventsArtifact;
}

describe("RallyShotTimeline", () => {
  afterEach(() => cleanup());

  it("按权威回合分行并展示阶段、摘要和事件详情", () => {
    render(<RallyShotTimeline artifact={availableFixture} loadState="available" />);

    expect(screen.getByText("回合—击球阶段时序图")).toBeTruthy();
    expect(screen.getByText("第 1 回合")).toBeTruthy();
    expect(screen.getByText("第 2 回合")).toBeTruthy();
    expect(screen.getByText("发球")).toBeTruthy();
    expect(screen.getByText("归属不明")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /shot-001/ }));
    expect(screen.getByTestId("rally-shot-details")).toBeTruthy();
    expect(screen.getByText(/证据窗口/)).toBeTruthy();
  });

  it("没有可靠回合边界时回退为单行时间排序", () => {
    const noBoundary = cloneFixture();
    noBoundary.rallies = [];
    noBoundary.diagnostics.rally_boundary_status = "unavailable";
    noBoundary.shots = noBoundary.shots.map((shot) => ({ ...shot, rally_id: null, ordinal_in_rally: null }));

    render(<RallyShotTimeline artifact={noBoundary} loadState="available" />);

    expect(screen.getByText("按时间排序")).toBeTruthy();
    expect(screen.getByText(/未提供可靠回合边界/)).toBeTruthy();
    expect(screen.queryByText("第 1 回合")).toBeNull();
  });

  it("没有击球事件时显示空态", () => {
    const empty = cloneFixture();
    empty.rallies = [];
    empty.shots = [];

    render(<RallyShotTimeline artifact={empty} loadState="available" />);

    expect(screen.getByText("暂无可展示击球事件。")).toBeTruthy();
  });

  it("加载失败和不可用只影响时序图", () => {
    const { rerender } = render(<RallyShotTimeline artifact={null} loadState="loading" />);
    expect(screen.getByText("正在读取回合事件…")).toBeTruthy();

    rerender(<RallyShotTimeline artifact={null} loadState="failed" detail="事件接口读取失败" />);
    expect(screen.getByText("读取失败")).toBeTruthy();
    expect(screen.getByText("事件接口读取失败")).toBeTruthy();
  });

  it("只对有证据窗口的事件触发视频定位", () => {
    const onSeekToMs = vi.fn();
    render(<RallyShotTimeline artifact={availableFixture} loadState="available" onSeekToMs={onSeekToMs} />);

    fireEvent.click(screen.getByRole("button", { name: /shot-001/ }));
    fireEvent.click(screen.getByRole("button", { name: "定位到视频证据" }));
    expect(onSeekToMs).toHaveBeenCalledWith(1100);

    fireEvent.click(screen.getByRole("button", { name: /shot-004/ }));
    expect(screen.queryByRole("button", { name: "定位到视频证据" })).toBeNull();
  });
});
