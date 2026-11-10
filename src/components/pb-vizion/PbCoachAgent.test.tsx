import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { demoAnalysisReport } from "../../data/demoData";
import PbCoachAgent from "./PbCoachAgent";

const MOVEMENT_QUESTION = "解释这位球员的移动数据，列出依据";
const PLAN_QUESTION = "给这位初学者安排 15 分钟步法练习";
// 对话开始后快捷问题收缩为短标签
const ADJUST_SHORT = "改成 8 分钟两人";

// 本仓库未配置全局 cleanup，逐用例手动卸载，避免上一条用例的 DOM 影响查询
afterEach(() => cleanup());

function askChip(text: string) {
  fireEvent.click(screen.getByRole("button", { name: text }));
}

describe("PbCoachAgent", () => {
  it("未提问时展示示例问题与计划空态，并标注演示数据", () => {
    render(<PbCoachAgent report={demoAnalysisReport} />);

    expect(screen.getByText("AI 教学助教")).toBeTruthy();
    expect(screen.getByText("演示样例数据")).toBeTruthy();
    expect(screen.getByText("还没有训练计划")).toBeTruthy();
    expect(screen.getByText(MOVEMENT_QUESTION)).toBeTruthy();
    expect(screen.getByText(PLAN_QUESTION)).toBeTruthy();
  });

  it("回答先展示工具调用，再给出带证据引用的结论", async () => {
    render(<PbCoachAgent report={demoAnalysisReport} />);

    askChip(MOVEMENT_QUESTION);

    await waitFor(() => expect(screen.getByText("读取分析证据")).toBeTruthy(), { timeout: 3000 });
    await waitFor(() => expect(screen.getByText(/累计移动 186 英尺/)).toBeTruthy(), { timeout: 8000 });
    // 证据 chip 以编号 + 指标呈现
    expect(screen.getByText("E1")).toBeTruthy();
  }, 20000);

  it("训练计划按对话版本递增：v1 生成后改成 v2 并保留原目标", async () => {
    render(<PbCoachAgent report={demoAnalysisReport} />);

    askChip(PLAN_QUESTION);
    await waitFor(() => expect(screen.getByText("v1")).toBeTruthy(), { timeout: 12000 });

    askChip(ADJUST_SHORT);
    await waitFor(() => expect(screen.getByText("v2")).toBeTruthy(), { timeout: 12000 });
    expect(screen.getByText("2 人（轮转）")).toBeTruthy();
  }, 40000);
});
