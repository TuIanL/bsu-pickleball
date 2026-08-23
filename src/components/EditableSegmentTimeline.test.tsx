import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaptureSegmentSummary } from "../types/report";
import { EditableSegmentTimeline } from "./EditableSegmentTimeline";

afterEach(() => cleanup());

function segment(overrides: Partial<CaptureSegmentSummary> = {}): CaptureSegmentSummary {
  return {
    id: "rally-1",
    segment_type: "rally",
    ordinal: 1,
    label: "第1分",
    start_ms: 1000,
    end_ms: 5000,
    edit_version: 2,
    edit_status: "active",
    status: "closed",
    source: "algorithm",
    is_highlight: false,
    ...overrides,
  };
}

describe("EditableSegmentTimeline 联动与拖拽", () => {
  it("点击片段块只定位到片段起点并高亮 active 块", () => {
    const onSegmentClick = vi.fn();
    const { container } = render(
      <EditableSegmentTimeline
        segments={[segment()]}
        events={[]}
        totalDurationMs={10000}
        currentTimeMs={0}
        activeSegmentId="rally-1"
        onSeek={vi.fn()}
        onSegmentClick={onSegmentClick}
        onBoundaryChange={vi.fn()}
      />,
    );
    fireEvent.click(container.querySelector('[title*="第1分"]')!);
    expect(onSegmentClick).toHaveBeenCalledWith("rally-1", 1000);
    expect(container.querySelector('[title*="第1分"]')?.className).toContain("ring-2");
  });

  it("拖拽移动只更新本地预览，释放时只提交一次并携带 edit_version", () => {
    const onBoundaryChange = vi.fn();
    const setPointerCapture = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: setPointerCapture });
    const { container } = render(
      <EditableSegmentTimeline
        segments={[segment()]}
        events={[]}
        totalDurationMs={10000}
        currentTimeMs={0}
        onSeek={vi.fn()}
        onBoundaryChange={onBoundaryChange}
      />,
    );
    const timeline = container.querySelector(".select-none")!;
    const handle = container.querySelector(".cursor-col-resize")!;

    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 100 });
    fireEvent.pointerMove(timeline, { pointerId: 1, clientX: 150 });
    expect(onBoundaryChange).not.toHaveBeenCalled();
    fireEvent.pointerUp(timeline, { pointerId: 1, clientX: 150 });

    expect(onBoundaryChange).toHaveBeenCalledTimes(1);
    expect(onBoundaryChange).toHaveBeenCalledWith("rally-1", expect.any(Number), 5000, 2);
  });

  it("拖拽红色播放头只 seek，不修改片段边界", () => {
    const onSeek = vi.fn();
    const onBoundaryChange = vi.fn();
    const setPointerCapture = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: setPointerCapture });
    const { container } = render(
      <EditableSegmentTimeline
        segments={[segment()]}
        events={[]}
        totalDurationMs={10000}
        currentTimeMs={0}
        onSeek={onSeek}
        onBoundaryChange={onBoundaryChange}
      />,
    );
    const timeline = container.querySelector(".select-none")!;
    Object.defineProperty(timeline, "getBoundingClientRect", {
      configurable: true,
      value: () => ({ left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100 }),
    });
    const playhead = screen.getByRole("button", { name: "拖拽视频播放头" });

    fireEvent.pointerDown(playhead, { pointerId: 2, clientX: 10 });
    fireEvent.pointerMove(timeline, { pointerId: 2, clientX: 50 });
    fireEvent.pointerUp(timeline, { pointerId: 2, clientX: 50 });

    expect(onSeek).toHaveBeenCalledWith(1000);
    expect(onSeek).toHaveBeenLastCalledWith(5000);
    expect(onBoundaryChange).not.toHaveBeenCalled();
  });
});
