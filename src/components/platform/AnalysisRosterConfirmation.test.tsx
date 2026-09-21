import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getPlayerBootstrap: vi.fn(),
}));

vi.mock("../../services/analysisClient", () => ({
  getPlayerBootstrap: mocks.getPlayerBootstrap,
}));

import { AnalysisRosterConfirmation } from "./AnalysisRosterConfirmation";
import type { RosterConfirmationRequest } from "../../types/rallyContext";

function bootstrapResult(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "player-bootstrap.v1",
    status: "available",
    owner_key: "take-1",
    capture_take_id: "take-1",
    bootstrap_run_id: "job-src",
    bootstrap_model_version: "player-render-trajectory.v2",
    reference_timestamp_ms: 1000,
    skippable: true,
    consumers_enabled: true,
    diagnostics: [],
    candidates: [1, 2, 3, 4].map((index) => ({
      canonical_player_id: `Player_${index}`,
      display_name: `球员${index}`,
      anchor_timestamp_ms: index * 1000,
      anchor_court_xy: [index, index + 1],
      confidence: 0.8,
    })),
    ...overrides,
  };
}

function lastRequest(onChange: ReturnType<typeof vi.fn>): RosterConfirmationRequest {
  return onChange.mock.calls.at(-1)?.[0] as RosterConfirmationRequest;
}

describe("AnalysisRosterConfirmation", () => {
  afterEach(() => cleanup());

  it("默认不推断 Team A/B：未确认时不提交任何名册条目", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapResult());
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" matchFormat="doubles" onChange={onChange} />);

    const root = await screen.findByTestId("analysis-roster-confirmation");
    await waitFor(() => expect(root.getAttribute("data-roster-status")).toBe("available"));

    // 四个槽位都不带 Team 归属
    for (const playerId of ["Player_1", "Player_2", "Player_3", "Player_4"]) {
      expect(screen.getByTestId(`roster-candidate-${playerId}`).getAttribute("data-team-assignment")).toBe(
        "unassigned",
      );
    }
    expect(screen.getByTestId("roster-incomplete").textContent).toContain("尚未完整");

    const request = lastRequest(onChange);
    expect(request.skipped).toBe(false);
    expect(request.entries).toEqual([]);
    expect(request.initial_team_a_end).toBeNull();
    expect(root.getAttribute("data-skipped")).toBe("false");
  });

  it("显式跳过：回抛 skipped 请求并说明不会推断 Team A/B", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapResult());
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" matchFormat="doubles" onChange={onChange} />);

    await screen.findByTestId("analysis-roster-confirmation");
    fireEvent.click(screen.getByTestId("roster-skip-toggle"));

    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.skipped).toBe(true);
      expect(request.entries).toEqual([]);
      expect(request.initial_team_a_end).toBeNull();
    });
    expect(screen.getByTestId("roster-skipped-note").textContent).toContain("不会推断 Team A/B");
  });

  it("人工确认四名球员与初始端位后，回抛冻结名册", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapResult());
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" matchFormat="doubles" onChange={onChange} />);

    await screen.findByTestId("analysis-roster-confirmation");
    fireEvent.click(screen.getByTestId("roster-team-0-A"));
    fireEvent.click(screen.getByTestId("roster-team-1-A"));
    fireEvent.click(screen.getByTestId("roster-team-2-B"));
    fireEvent.click(screen.getByTestId("roster-team-3-B"));
    fireEvent.click(screen.getByTestId("court-end-end_a"));

    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.skipped).toBe(false);
      expect(request.initial_team_a_end).toBe("end_a");
      expect(request.entries).toHaveLength(4);
      expect(request.entries.map((entry) => entry.team_id)).toEqual(["A", "A", "B", "B"]);
      // bootstrap 锚点被带入冻结名册，供后续身份连续性审计使用
      expect(request.entries[0].anchor_court_xy).toEqual([1, 2]);
      expect(request.entries[0].anchor_timestamp_ms).toBe(1000);
      expect(request.bootstrap_run_id).toBe("job-src");
      expect(request.bootstrap_model_version).toBe("player-render-trajectory.v2");
    });

    expect(screen.getByTestId("roster-ready").textContent).toContain("4 名球员");
    expect(screen.getByTestId("analysis-roster-confirmation").getAttribute("data-court-end")).toBe("end_a");
  });

  it("允许用户把本次 P 槽位映射到指定候选，且不重复使用候选", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapResult());
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" matchFormat="doubles" onChange={onChange} />);

    await screen.findByTestId("analysis-roster-confirmation");
    // 先释放 P2 的默认候选，才能把该候选明确选给本次 P1。
    fireEvent.change(screen.getByTestId("roster-player-select-1"), { target: { value: "" } });
    fireEvent.change(screen.getByTestId("roster-player-select-0"), { target: { value: "Player_2" } });
    fireEvent.click(screen.getByTestId("roster-team-0-A"));

    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.entries[0].canonical_player_id).toBe("Player_2");
      expect(request.entries[0].anchor_court_xy).toEqual([2, 3]);
    });
    expect((screen.getByTestId("roster-player-select-1") as HTMLSelectElement).value).toBe("");
    expect(screen.getByTestId("roster-player-select-1").querySelector('option[value="Player_2"]')).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("在候选参考帧上叠绘 anchor_bbox 与 P1–P4 标签", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(
      bootstrapResult({
        reference_frame_url: "/bootstrap/reference.jpg",
        candidates: [1, 2, 3, 4].map((index) => ({
          canonical_player_id: `Player_${index}`,
          display_name: `球员${index}`,
          anchor_timestamp_ms: index * 1000,
          anchor_bbox: [index * 100, 20, index * 100 + 60, 180],
          anchor_court_xy: [index, index + 1],
          confidence: 0.8,
        })),
      }),
    );
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" matchFormat="doubles" onChange={onChange} />);

    const image = await screen.findByAltText("候选参考帧（1000ms）");
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: 1920 });
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: 1080 });
    fireEvent.load(image);

    const overlay = await screen.findByTestId("roster-reference-overlay");
    expect(overlay.getAttribute("viewBox")).toBe("0 0 1920 1080");
    expect(screen.getByTestId("roster-anchor-Player_1").textContent).toContain("P1");
    expect(screen.getByTestId("roster-anchor-Player_4").textContent).toContain("P4");
  });

  it("候选不足时给出质量诊断，未识别槽位仍可手工补全", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(
      bootstrapResult({
        status: "insufficient_candidates",
        unavailable_reason: "analysis_roster_insufficient_candidates",
        candidates: [
          {
            canonical_player_id: "Player_1",
            anchor_timestamp_ms: 0,
            anchor_bbox: null,
            anchor_court_xy: null,
            confidence: null,
          },
        ],
        diagnostics: [
          { code: "bootstrap_insufficient_candidates", detail: "仅识别到 1 名候选", severity: "warning" },
        ],
      }),
    );
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation videoId="video-1" matchFormat="doubles" onChange={onChange} />);

    const root = await screen.findByTestId("analysis-roster-confirmation");
    await waitFor(() => expect(root.getAttribute("data-roster-status")).toBe("insufficient_candidates"));
    expect(screen.getByTestId("roster-diagnostic").textContent).toContain("候选不足");
    expect(screen.getByTestId("roster-quality-diagnostics").textContent).toContain(
      "bootstrap_insufficient_candidates",
    );
    expect(screen.getByTestId("roster-candidate-Player_3").getAttribute("data-has-anchor")).toBe("false");
    expect(screen.getByTestId("roster-candidate-Player_1").getAttribute("data-has-anchor")).toBe("false");
  });

  it("无可用产物时显式 unavailable，单打只渲染两个槽位", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(
      bootstrapResult({ status: "unavailable", unavailable_reason: "bootstrap_no_source_job", candidates: [] }),
    );
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-x" matchFormat="singles" onChange={onChange} />);

    const root = await screen.findByTestId("analysis-roster-confirmation");
    await waitFor(() => expect(root.getAttribute("data-roster-status")).toBe("unavailable"));
    expect(root.getAttribute("data-roster-status")).toBe("unavailable");
    await waitFor(() => expect(screen.getByTestId("roster-candidate-Player_1")).toBeTruthy());
    expect(screen.queryByTestId("roster-candidate-Player_4")).toBeNull();
  });

  it("feature gate 关闭时降级为仅提示，且只提交跳过", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapResult({ consumers_enabled: false }));
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" matchFormat="doubles" onChange={onChange} />);

    const root = await screen.findByTestId("analysis-roster-confirmation");
    await waitFor(() => expect(root.getAttribute("data-consumers-enabled")).toBe("false"));
    expect(screen.getByTestId("roster-consumers-disabled").textContent).toContain("未启用分析回合上下文消费");
    expect(root.getAttribute("data-skipped")).toBe("true");

    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.skipped).toBe(true);
      expect(request.entries).toEqual([]);
    });

    // 关闭态下不渲染可编辑槽位，避免把用户误导成"已确认名册"
    expect(screen.queryByTestId("roster-team-0-A")).toBeNull();
  });

  it("预检请求失败不阻断页面，用户仍可继续或跳过", async () => {
    mocks.getPlayerBootstrap.mockRejectedValue(new Error("network down"));
    const onChange = vi.fn();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" matchFormat="doubles" onChange={onChange} />);

    await screen.findByTestId("roster-load-error");
    expect(screen.getByTestId("roster-load-error").textContent).toContain("network down");
    await waitFor(() => expect(lastRequest(onChange).entries).toEqual([]));

    fireEvent.click(screen.getByTestId("roster-skip-toggle"));
    await waitFor(() => expect(lastRequest(onChange).skipped).toBe(true));
  });
});
