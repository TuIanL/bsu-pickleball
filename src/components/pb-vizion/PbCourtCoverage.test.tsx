import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PbCourtCoverage from "./PbCourtCoverage";

const reportState = vi.hoisted(() => ({ evidence: undefined as unknown }));

vi.mock("../../contexts/PbReportContext", () => ({
  usePbReport: () => ({ evidence: reportState.evidence }),
}));

function zoneEvidence(playerId: string, sufficiency = "sufficient") {
  return {
    isDemo: false,
    courtCoverage: {
      distanceFt: { status: "available", value: 42, provenance: [] },
      zoneStats: {
        status: "available",
        provenance: [{ kind: "structured_visualization", playerId }],
        value: {
          id: playerId,
          label: playerId === "Player_1" ? "P1" : "P2",
          color: "#22C55E",
          denominator_seconds: 12,
          tracked_seconds: 10,
          data_sufficiency: sufficiency,
          nvz_occupancy_rate: 0.4,
          kitchen_control_rate: 0.4,
          avg_distance_to_kitchen_line_m: 1.2,
          zones: [
            { zone: "kitchen", label: "网前区", seconds: 4, occupancy: 0.4 },
            { zone: "transition", label: "过渡区", seconds: 4, occupancy: 0.4 },
            { zone: "backcourt", label: "后场区", seconds: 2, occupancy: 0.2 },
          ],
          feedback: { level: "moderate", summary: "站位分布正常" },
        },
      },
    },
  };
}

describe("PbCourtCoverage", () => {
  it("使用当前 canonical player 的真实 zone_stats，并显示有效帧不足提示", () => {
    reportState.evidence = zoneEvidence("Player_1", "insufficient");
    const { rerender } = render(<PbCourtCoverage />);
    expect(screen.getByText("P1")).toBeTruthy();
    expect(screen.getByText("有效帧不足，以下占用百分比为参考，勿作确定结论。")).toBeTruthy();

    reportState.evidence = zoneEvidence("Player_2");
    rerender(<PbCourtCoverage />);
    expect(screen.getByText("P2")).toBeTruthy();
  });

  it("真实任务缺少 zone_stats 时显示证据不可用状态，不显示演示球场", () => {
    reportState.evidence = {
      isDemo: false,
      courtCoverage: {
        distanceFt: { status: "unavailable", value: null, reason: "暂无移动距离数据" },
        zoneStats: { status: "unavailable", value: null, reason: "该历史任务未生成结构化区域统计" },
      },
    };
    render(<PbCourtCoverage />);
    expect(screen.getByText("本次分析暂未生成")).toBeTruthy();
    expect(screen.getByText("该历史任务未生成结构化区域统计")).toBeTruthy();
    expect(screen.queryByText("球网")).toBeNull();
  });
});
