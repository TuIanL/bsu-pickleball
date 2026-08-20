import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReportPerformanceInsights } from "../types/report";
import { PerformanceInsightsPanel } from "../components/platform/PerformanceInsightsPanel";
import { withTaskListContext } from "../app/navigationContext";
import { taskContextForJob } from "../app/navigationContext";
import type { AnalysisJobSummary } from "../types/report";

afterEach(cleanup);

function makeInsights(overrides: Partial<ReportPerformanceInsights> = {}): ReportPerformanceInsights {
  return {
    status: "available",
    match_format: "doubles",
    rule_profile_version: "insight-rule-profile.v1",
    data_quality_summary: "有效 Rally 2 个；轨迹覆盖率 58%",
    subjects: [
      { id: "Player_1", label: "P1", kind: "player" },
      { id: "Player_3", label: "P3", kind: "player" },
      { id: "team_near", label: "近侧组合", kind: "team" },
    ],
    dimensions: [
      {
        dimension: "court_positioning",
        label: "场位与网前控制",
        subject_id: "Player_1",
        status: "needs_improvement",
        summary: "过渡区停留占用约 52%，高于产品参考基准 45%。",
      },
      {
        dimension: "transition_decision",
        label: "攻防转换与决策",
        subject_id: "Player_1",
        status: "unsupported",
        summary: "当前证据能力不支持该维度评价。",
      },
    ],
    findings: [
      {
        id: "finding:transition_zone_dwell:Player_1",
        subject_id: "Player_1",
        dimension: "court_positioning",
        dimension_label: "场位与网前控制",
        assessment: "needs_improvement",
        priority: 2,
        confidence: "medium",
        title: "过渡区停留比例较高",
        diagnosis: "该球员在有效比赛时间中，过渡区停留占用约 52%。",
        impact: "停留在过渡区意味着既未建立网前压制也未完成后场站位。",
        evidence_ids: ["ev:Player_1:transition_occupancy"],
        evidence_windows: [{ start_ms: 184200, end_ms: 191500, rally_id: null }],
      },
      {
        id: "finding:kitchen_line_proximity:Player_3",
        subject_id: "Player_3",
        dimension: "court_positioning",
        dimension_label: "场位与网前控制",
        assessment: "insufficient_evidence",
        priority: 3,
        confidence: "low",
        title: "站位距离数据有限",
        diagnosis: "有效帧覆盖不足。",
        impact: "建议补充有效跟踪时间后再评估。",
        evidence_ids: ["ev:Player_3:avg_distance_to_kitchen_line_m"],
        evidence_windows: [],
      },
    ],
    recommendations: [
      {
        id: "rec:transition_zone_dwell:Player_1",
        subject_id: "Player_1",
        title: "接发后推进与网前转换训练",
        detail: "重点训练接发后立即前压与第三拍后的网前转换。",
        metric: "transition_occupancy",
        baseline: "过渡区占用 52%",
        next_target: "降低到 42% 以下",
        direction: "decrease",
        finding_id: "finding:transition_zone_dwell:Player_1",
      },
    ],
    candidate_facts: [
      {
        kind: "bounce_candidates",
        count: 14,
        detail: "检测到 14 个弹跳候选（algorithm candidate，非确认落点事件）。",
        sample_windows: [],
      },
    ],
    primary_focus_finding_id: "finding:transition_zone_dwell:Player_1",
    ...overrides,
  };
}

function renderPanel(insights: ReportPerformanceInsights, jobId = "job-panel-1") {
  const onNavigate = vi.fn();
  const job = { id: jobId, metadata: {} } as unknown as AnalysisJobSummary;
  render(<PerformanceInsightsPanel insights={insights} jobId={jobId} job={job} onNavigate={onNavigate} />);
  return { onNavigate, job };
}

describe("PerformanceInsightsPanel", () => {
  it("renders summary cards and dimension status without numeric scores", () => {
    renderPanel(makeInsights());
    expect(screen.getByText("本场表现")).toBeTruthy();
    expect(screen.getByText("首要问题")).toBeTruthy();
    // 首要问题标题出现在首屏总结卡（全场视角）与关键发现列表中。
    expect(screen.getAllByText("过渡区停留比例较高").length).toBeGreaterThanOrEqual(1);
    // 维度状态卡：状态标签 + 无数值分文案。
    expect(screen.getAllByText("待改进").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("暂不评价").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/不提供未经校准的数值评分/)).toBeTruthy();
  });

  it("filters findings and recommendations when switching subject chips", () => {
    renderPanel(makeInsights());
    // 默认 P1：关键发现区含 Player_1 的 finding（标题出现 ≥2 次：总结卡 + 发现卡）。
    expect(screen.getAllByText("过渡区停留比例较高").length).toBeGreaterThanOrEqual(2);
    // 切到 P3：P3 的 finding 出现，P1 的 finding 卡消失（总结卡仍保留全场首要问题）。
    fireEvent.click(screen.getByRole("button", { name: "P3" }));
    expect(screen.getByText("站位距离数据有限")).toBeTruthy();
    expect(screen.getAllByText("过渡区停留比例较高").length).toBe(1);
    // P1 的训练建议随视角过滤消失。
    expect(screen.queryByText("接发后推进与网前转换训练")).toBeNull();
  });

  it("navigates to vision with t param when clicking video evidence", () => {
    const { onNavigate, job } = renderPanel(makeInsights());
    fireEvent.click(screen.getByRole("button", { name: /查看视频证据 03:04 - 03:11/ }));
    expect(onNavigate).toHaveBeenCalledWith(
      withTaskListContext(`/analysis/job-panel-1/vision?t=184200`, taskContextForJob(job)),
    );
  });

  it("renders candidate facts as a separate non-finding section", () => {
    renderPanel(makeInsights());
    expect(screen.getByText("算法候选事实")).toBeTruthy();
    expect(screen.getByText(/不构成落点统计或战术结论/)).toBeTruthy();
  });

  it("renders training target with baseline and next target only (no history)", () => {
    renderPanel(makeInsights());
    expect(screen.getByText("本次 baseline")).toBeTruthy();
    expect(screen.getByText("下一次目标")).toBeTruthy();
    expect(screen.getAllByText("过渡区占用 52%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("降低到 42% 以下").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/跨场次历史对比需建立稳定球员档案后提供/)).toBeTruthy();
  });

  it("shows explicit unavailable state instead of demo conclusions", () => {
    renderPanel(
      makeInsights({
        status: "unavailable",
        unavailable_reason: "pipeline 结果不可用，无法生成洞察。",
      }),
    );
    expect(screen.getByText("洞察暂不可用")).toBeTruthy();
    expect(screen.getByText(/仍展示真实的移动数据/)).toBeTruthy();
  });
});
