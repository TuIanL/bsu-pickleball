import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary, PlayerDisplayDiagnosticsResponse } from "../types/report";
import type { MultiviewObservabilitySummary, RecoveryEpisodePage } from "../types/multiviewObservability";
import { MultiviewObservabilityPage } from "./MultiviewObservabilityPage";
import * as analysisClient from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({
  getAnalysisJob: vi.fn(),
  getMultiviewObservability: vi.fn(),
  getMultiviewRecoveryEpisodes: vi.fn(),
  getMultiviewDebugVideoUrl: vi.fn((jobId: string) => `/api/analysis/jobs/${jobId}/multiview/debug-video`),
  getPlayerDisplayDiagnostics: vi.fn(),
  isAnalysisApiError: vi.fn(() => false),
}));

function makeJob(kind: "multiview" | "single_view" = "multiview"): AnalysisJobSummary {
  return {
    id: "job-observe-ui",
    status: "completed",
    stage: "report",
    progress: 100,
    createdAt: "2026-08-13T00:00:00.000Z",
    updatedAt: "2026-08-13T00:00:00.000Z",
    analysisKind: kind,
    analysisMode: "real",
    executionMode: "joint_tracking_v2",
    metadata: {
      fileName: "joint.mp4",
      matchTitle: "UI test",
      venue: "Test court",
      matchDate: "2026-08-13",
      matchFormat: "doubles",
      cameraAngle: "elevated",
      athleteLabel: "Players",
      level: "MVP",
    },
    stages: [],
  } as unknown as AnalysisJobSummary;
}

function section<T>(availability: "available" | "partial" | "unavailable" | "not_applicable", status: string, data?: T) {
  return { availability, status, data };
}

function makeSummary(overrides: Partial<MultiviewObservabilitySummary> = {}): MultiviewObservabilitySummary {
  const summary = {
    schema_version: "multiview_observability_summary.v1",
    job_id: "job-observe-ui",
    run_id: "run-ui",
    analysis_kind: "multiview",
    requested_mode: "joint_tracking_v2",
    execution_mode: "joint_tracking_v2",
    effective_mode: "multiview_fused",
    sections: {
      sync: section("available", "authoritative", { sync_quality: "good", execution_mode: "joint_authoritative", authoritative_joint_eligible: true, per_view_authority: { cam_1: "source_pts", cam_2: "source_pts" } }),
      fusion: section("available", "completed", { status_counts: { dual_observed: 8, single_view_fallback: 2 }, metric_eligible_count: 8, sample_count: 10 }),
      recovery: section("available", "completed", { funnel: { recovery_opportunity_count: 2, guidance_generated_count: 2, guided_recovery_success_count: 1, base_recovered_count: 1 }, episode_availability: "available" }),
      refinement: section("available", "rejected_by_safety_gate", { execution_status: "completed", candidate_f1: { available: true }, publication_decision: "rejected_by_safety_gate", final_source: "first_pass_f0", safety_gate: { reason: "conflicts_increased" } }),
      debug: section("unavailable", "disabled", { debug_trace_enabled: false, video_available: false }),
    },
  } satisfies MultiviewObservabilitySummary;
  return { ...summary, ...overrides, sections: { ...summary.sections, ...(overrides.sections ?? {}) } };
}

function renderPage(summary: MultiviewObservabilitySummary | null, job = makeJob(), recoveryPage?: RecoveryEpisodePage, diagResponse?: PlayerDisplayDiagnosticsResponse) {
  vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(job);
  vi.mocked(analysisClient.getMultiviewObservability).mockResolvedValue(summary);
  if (recoveryPage) {
    vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).mockResolvedValue(recoveryPage);
  } else if (!vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).getMockImplementation()) {
    vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).mockResolvedValue({ items: [], total_estimate: 0, availability: "available" });
  }
  const emptyDiag: PlayerDisplayDiagnosticsResponse = {
    job_id: job.id,
    player_id: "Player_1",
    timestamp_ms: 0,
    window_ms: 2000,
    status: "available",
    detail: "",
    rows: [],
  };
  // 热力图分段拉取：首段返回 diagResponse（若提供），后续段返回空以提前停止
  vi.mocked(analysisClient.getPlayerDisplayDiagnostics).mockImplementation((_jobId, _playerId, timestampMs) =>
    Promise.resolve(diagResponse && timestampMs === 0 ? diagResponse : emptyDiag),
  );
  return render(<MultiviewObservabilityPage jobId={job.id} onNavigate={vi.fn()} />);
}

describe("MultiviewObservabilityPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows authoritative sync, independent fusion and refinement rejection semantics", async () => {
    renderPage(makeSummary());
    expect(await screen.findByText("联合运行状态")).toBeTruthy();
    expect((await screen.findAllByText("authoritative")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("source_pts").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("rejected_by_safety_gate").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("精修已完成")).toBeTruthy();
    expect(screen.getByText("发布被安全门拒绝")).toBeTruthy();
    expect(screen.getAllByText("F0").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/本任务未开启/)).toBeTruthy();
    expect(analysisClient.getMultiviewDebugVideoUrl).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("joint_debug_trace.v1.json");
  });

  it("keeps degraded joint and partial historical data visible", async () => {
    renderPage(makeSummary({
      effective_mode: "multiview_degraded",
      sections: {
        ...makeSummary().sections,
        sync: section("partial", "degraded", { sync_quality: "degraded", authoritative_joint_eligible: false }),
        recovery: section("partial", "completed", { funnel: { recovery_opportunity_count: 3 }, episode_availability: "partial" }),
      },
    }));
    expect((await screen.findAllByText("degraded")).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("部分可用").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/没有可分页的 recovery episode/)).toBeTruthy();
  });

  it("auto-loads debug replay when the canonical MP4 is available and supports unload/reload", async () => {
    const summary = makeSummary({
      sections: {
        ...makeSummary().sections,
        debug: section("available", "ready", { debug_trace_enabled: true, video_available: true }),
      },
    });
    renderPage(summary);
    await screen.findByText("Debug Replay");
    // 资源可用时自动加载，无需手动点击
    await waitFor(() => expect(analysisClient.getMultiviewDebugVideoUrl).toHaveBeenCalledWith("job-observe-ui"));
    expect(document.querySelector("video")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "加载 canonical MP4" })).toBeNull();
    // 卸载 → 重新加载
    fireEvent.click(screen.getByRole("button", { name: "卸载视频" }));
    expect(document.querySelector("video")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重新加载 MP4" }));
    expect(document.querySelector("video")).toBeTruthy();
  });

  it("shows unavailable hint when the debug MP4 is not generated", async () => {
    const summary = makeSummary({
      sections: {
        ...makeSummary().sections,
        debug: section("unavailable", "missing", { debug_trace_enabled: true, video_available: false }),
      },
    });
    renderPage(summary);
    expect(await screen.findByText("canonical debug MP4 尚未生成。")).toBeTruthy();
    expect(document.querySelector("video")).toBeNull();
    expect(analysisClient.getMultiviewDebugVideoUrl).not.toHaveBeenCalled();
  });

  it("marks late fusion recovery and refinement as not applicable", async () => {
    const summary = makeSummary({
      execution_mode: "late_fusion_v1",
      effective_mode: "multiview_fused",
      sections: {
        ...makeSummary().sections,
        recovery: section("not_applicable", "not_applicable"),
        refinement: section("not_applicable", "not_applicable"),
      },
    });
    renderPage(summary);
    expect((await screen.findAllByText("不适用")).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("当前执行模式不适用在线恢复。")).toBeTruthy();
  });

  it("renders single-view as a not-applicable state", async () => {
    renderPage(null, makeJob("single_view"));
    expect(await screen.findByText("该任务不适用双摄协同详情")).toBeTruthy();
    expect(analysisClient.getMultiviewObservability).toHaveBeenCalledWith("job-observe-ui");
  });

  it("keeps refinement execution, publication and final source independent", async () => {
    renderPage(makeSummary({
      sections: {
        ...makeSummary().sections,
        refinement: section("available", "failed_fallback", { execution_status: "failed_fallback", candidate_f1: { available: false }, publication_decision: "failed_fallback", final_source: "first_pass_f0" }),
      },
    }));
    expect(await screen.findByText("精修执行异常，已回退 F0")).toBeTruthy();
    expect(screen.getByText("未发布（执行异常）")).toBeTruthy();
    expect(screen.getAllByText("F0").length).toBeGreaterThanOrEqual(1);

    cleanup();
    renderPage(makeSummary({
      sections: {
        ...makeSummary().sections,
        refinement: section("available", "completed", { execution_status: "completed", candidate_f1: { available: true }, publication_decision: "passed", final_source: "refined_f1" }),
      },
    }));
    expect(await screen.findByText("安全门通过，发布 F1")).toBeTruthy();
    expect(screen.getAllByText("F1").length).toBeGreaterThanOrEqual(1);
  });

  it("supports episode filtering, cursor continuation, expand and backend seek", async () => {
    const episode = { recovery_episode_id: "re_1", start_ms: 100, end_ms: 200, global_player_id: "global_1", donor_view: "cam_1", target_view: "cam_2", outcome: "guided_recovery_success", guidance_attempts: 2, pre_gate_rejections: 1, lock_rejections: 0, debug_video_seek_ms: 125 } as const;
    const first: RecoveryEpisodePage = { items: [episode], next_cursor: "cursor-2", total_estimate: 2, availability: "available" };
    const second: RecoveryEpisodePage = { items: [], total_estimate: 2, availability: "available" };
    vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).mockResolvedValue(first);
    const job = makeJob();
    vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(job);
    vi.mocked(analysisClient.getMultiviewObservability).mockResolvedValue(makeSummary());
    render(<MultiviewObservabilityPage jobId={job.id} onNavigate={vi.fn()} />);
    await waitFor(() => expect(analysisClient.getMultiviewRecoveryEpisodes).toHaveBeenCalled());
    expect(await screen.findByText(/global_1/)).toBeTruthy();
    fireEvent.click(screen.getByText(/global_1/).closest("button") as HTMLElement);
    expect(screen.getAllByText("前置门拒绝").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("125 ms")).toBeTruthy();
    expect((screen.getByRole("button", { name: "定位到 Debug Replay" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("目标视角"), { target: { value: "cam_2" } });
    await waitFor(() => expect(analysisClient.getMultiviewRecoveryEpisodes).toHaveBeenCalledWith("job-observe-ui", expect.objectContaining({ target_view: "cam_2" })));
    vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).mockResolvedValue(second);
    fireEvent.click(screen.getByRole("button", { name: /加载下一页/ }));
    await waitFor(() => expect(analysisClient.getMultiviewRecoveryEpisodes).toHaveBeenCalledWith("job-observe-ui", expect.objectContaining({ cursor: "cursor-2" })));
  });
});

describe("PlayerDisplayDiagnosticsPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders a display diagnostics heatmap from segmented window queries", async () => {
    const diagResponse: PlayerDisplayDiagnosticsResponse = {
      job_id: "job-observe-ui",
      player_id: "Player_1",
      timestamp_ms: 0,
      window_ms: 2000,
      status: "available",
      detail: "",
      rows: [
        {
          canonical_tick: 210,
          timestamp_ms: 7000,
          player_id: "Player_1",
          view_id: "cam_1",
          frame_status: "available",
          expected_region_status: "available",
          expected_image_position: [100, 200],
          eligible_detections_in_expected_gate: 1,
          eligible_detection_present: true,
          position_present: false,
          court_position_present: false,
          projection_status: null,
          projection_confidence: null,
          formal_observation_emitted: false,
          formal_local_observation: false,
          local_player_id: "Player_1",
          tracking_status: null,
          global_associated: false,
          association_reason: "no_association_input",
          binding_visibility: "observed",
          available_miss_streak: 1,
          guidance_status: "not_eligible",
          guidance_skip_reason: "donor_low_quality",
          guidance_trigger_source: "available_miss",
          overlay_evidence_type: null,
          overlay_bbox_source: null,
        },
      ],
    };
    renderPage(makeSummary(), makeJob(), undefined, diagResponse);
    expect(await screen.findByText("球员显示诊断")).toBeTruthy();
    // 热力图分段拉取：首段携带 windowMs=2000
    await waitFor(() => expect(analysisClient.getPlayerDisplayDiagnostics).toHaveBeenCalledWith("job-observe-ui", "Player_1", 0, 2000));
    // 热力图容器渲染（jsdom 无 canvas 时降级为占位，但容器与图例仍在）
    expect(screen.getByTestId("display-diagnostics-heatmap")).toBeTruthy();
    expect(screen.getByText("通过")).toBeTruthy();
    expect(screen.getByText("卡住")).toBeTruthy();
  });

  it("shows empty-state when the player has no diagnostics rows", async () => {
    renderPage(makeSummary());
    await screen.findByText("球员显示诊断");
    expect(await screen.findByText(/该球员没有可用的显示诊断行/)).toBeTruthy();
  });
});
