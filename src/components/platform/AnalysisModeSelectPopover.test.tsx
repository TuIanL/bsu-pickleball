import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AnalysisModeSelectPopover } from "./AnalysisModeSelectPopover";
import type { AnalysisModeSelectRow } from "./AnalysisModeSelectPopover";

function makeRows(): AnalysisModeSelectRow[] {
  return [
    { mode: "demo", eligibleCount: 2, state: "checked" },
    { mode: "limited", eligibleCount: 3, state: "unchecked" },
    { mode: "real", eligibleCount: 0, state: "unchecked" },
  ];
}

function renderPopover(overrides: Partial<React.ComponentProps<typeof AnalysisModeSelectPopover>> = {}) {
  return renderToStaticMarkup(
    createElement(AnalysisModeSelectPopover, {
      open: true,
      onClose: () => {},
      onToggleMode: () => {},
      onSelectModeFilter: () => {},
      modeFilter: "all",
      rows: makeRows(),
      ...overrides,
    }),
  );
}

describe("AnalysisModeSelectPopover", () => {
  it("renders nothing when closed", () => {
    const html = renderPopover({ open: false });
    expect(html).toBe("");
  });

  it("renders one row per analysis mode with counts", () => {
    const html = renderPopover();
    expect(html).toContain("样例任务");
    expect(html).toContain("有限分析");
    expect(html).toContain("真实视频分析");
    expect(html).toContain(">2<");
    expect(html).toContain(">3<");
    expect(html).toContain(">0<");
  });

  it("renders the filter section with all four options", () => {
    const html = renderPopover();
    expect(html).toContain("按类型筛选");
    expect(html).toContain("全部");
    // 筛选区 + 选择区共出现 4 次「样例任务」「有限分析」「真实视频分析」
    expect((html.match(/样例任务/g) ?? []).length).toBe(2);
    expect((html.match(/有限分析/g) ?? []).length).toBe(2);
    expect((html.match(/真实视频分析/g) ?? []).length).toBe(2);
  });

  it("marks the active filter with aria-pressed", () => {
    const html = renderPopover({ modeFilter: "demo" });
    // 3 个筛选按钮只有 demo 是激活态
    expect(html.match(/aria-pressed="true"/g)?.length).toBe(1);
    expect(html).toContain("aria-pressed=\"true\"");
  });

  it("checks the box only when state is checked", () => {
    const html = renderPopover();
    expect((html.match(/checked/g) ?? []).length).toBe(1);
  });

  it("disables rows with zero eligible tasks", () => {
    const html = renderPopover();
    expect((html.match(/disabled/g) ?? []).length).toBe(1);
  });
});
