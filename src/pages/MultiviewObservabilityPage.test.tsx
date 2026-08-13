import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary } from "../types/report";
import type { MultiviewObservabilitySummary, RecoveryEpisodePage } from "../types/multiviewObservability";
import { MultiviewObservabilityPage } from "./MultiviewObservabilityPage";
import * as analysisClient from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({
  getAnalysisJob: vi.fn(),
  getMultiviewObservability: vi.fn(),
  getMultiviewRecoveryEpisodes: vi.fn(),
  getMultiviewDebugVideoUrl: vi.fn((jobId: string) => `/api/analysis/jobs/${jobId}/multiview/debug-video`),
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

function renderPage(summary: MultiviewObservabilitySummary | null, job = makeJob(), recoveryPage?: RecoveryEpisodePage) {
  vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(job);
  vi.mocked(analysisClient.getMultiviewObservability).mockResolvedValue(summary);
  if (recoveryPage) {
    vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).mockResolvedValue(recoveryPage);
  } else if (!vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).getMockImplementation()) {
    vi.mocked(analysisClient.getMultiviewRecoveryEpisodes).mockResolvedValue({ items: [], total_estimate: 0, availability: "available" });
  }
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
    expect(screen.getByText("authoritative")).toBeTruthy();
    expect(screen.getAllByText("source_pts")).toHaveLength(2);
    expect(screen.getAllByText("rejected_by_safety_gate")).toHaveLength(1);
    expect(screen.getByText("精修已完成")).toBeTruthy();
    expect(screen.getByText("发布被安全门拒绝")).toBeTruthy();
    expect(screen.getByText("F0")).toBeTruthy();
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
    expect(await screen.findAllByText("degraded")).toHaveLength(2);
    expect(screen.getAllByText("部分可用").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/没有可分页的 recovery episode/)).toBeTruthy();
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
    expect(screen.getByText("F0")).toBeTruthy();

    cleanup();
    renderPage(makeSummary({
      sections: {
        ...makeSummary().sections,
        refinement: section("available", "completed", { execution_status: "completed", candidate_f1: { available: true }, publication_decision: "passed", final_source: "refined_f1" }),
      },
    }));
    expect(await screen.findByText("安全门通过，发布 F1")).toBeTruthy();
    expect(screen.getByText("F1")).toBeTruthy();
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
