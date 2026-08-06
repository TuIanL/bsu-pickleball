import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PlayerScoringPanel } from "./PlayerScoringPanel";
import { MOCK_PLAYER_SCORES } from "../../data/mockPlayerScores";
import { PLAYER_SCORE_DIMENSIONS } from "../../types/report";

const DOUBLES_ROSTER = ["Player_1", "Player_2", "Player_3", "Player_4"];
const SINGLES_ROSTER = ["Player_1", "Player_2"];

// 本仓库未启用 vitest globals，RTL 不会自动清理；每个用例后显式卸载避免 DOM 叠加。
afterEach(cleanup);

describe("PlayerScoringPanel", () => {
  it("默认选中第一个球员并展示六个维度", () => {
    render(<PlayerScoringPanel roster={DOUBLES_ROSTER} />);
    expect(screen.getByRole("button", { name: "P1" })).toBeTruthy();
    expect(screen.getByText(/均分/)).toBeTruthy();
    for (const dimension of PLAYER_SCORE_DIMENSIONS) {
      // 维度名同时出现在雷达轴标签与分值列表
      expect(screen.getAllByText(dimension.label).length).toBeGreaterThan(0);
    }
  });

  it("点击 tab 切换到对应球员（P2 分值出现）", () => {
    render(<PlayerScoringPanel roster={DOUBLES_ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: /P2/ }));
    expect(screen.getAllByText("7.1").length).toBeGreaterThan(0); // P2 serve
  });

  it("切换球员后分值列表同步更新（P3 分值出现）", () => {
    render(<PlayerScoringPanel roster={DOUBLES_ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: /P3/ }));
    expect(screen.getAllByText("6.9").length).toBeGreaterThan(0); // P3 serve
  });

  it("按结果自适应球员数量（单打 2 人无 P3/P4 tab）", () => {
    render(<PlayerScoringPanel roster={SINGLES_ROSTER} />);
    expect(screen.getByRole("button", { name: /P1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /P2/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /P3/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /P4/ })).toBeNull();
  });

  it("未传 scores 时回退 mock 并标注演示数据", () => {
    render(<PlayerScoringPanel roster={DOUBLES_ROSTER} />);
    expect(screen.getByText("演示数据")).toBeTruthy();
  });

  it("传入 scores 时不显示演示数据标注", () => {
    render(<PlayerScoringPanel roster={DOUBLES_ROSTER} scores={MOCK_PLAYER_SCORES} />);
    expect(screen.queryByText("演示数据")).toBeNull();
  });
});
