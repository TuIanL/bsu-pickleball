import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ init: vi.fn() }));
vi.mock("echarts/core", async (importOriginal) => ({
  ...(await importOriginal<typeof import("echarts/core")>()),
  init: mocks.init,
}));

import { EChart } from "./EChart";

const chart = {
  setOption: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
  dispose: vi.fn(),
  resize: vi.fn(),
};

describe("EChart event handlers", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    chart.setOption.mockClear();
    chart.on.mockClear();
    chart.off.mockClear();
    chart.dispose.mockClear();
  });

  it("updates inline event handlers without disposing and reinitializing the chart", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D);
    mocks.init.mockReturnValue(chart as never);
    const option = { series: [] };
    const firstHandler = vi.fn();
    const secondHandler = vi.fn();

    const { rerender } = render(
      <EChart option={option} onEvents={{ click: firstHandler }} />,
    );
    rerender(<EChart option={option} onEvents={{ click: secondHandler }} />);

    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(chart.dispose).not.toHaveBeenCalled();
    expect(chart.off).toHaveBeenCalledWith("click", firstHandler);
    expect(chart.on).toHaveBeenLastCalledWith("click", secondHandler);
  });
});
