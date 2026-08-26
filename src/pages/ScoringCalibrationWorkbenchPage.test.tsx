import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getCaptureTake: vi.fn(),
  listSegments: vi.fn(),
  listScoringCalibrationPackages: vi.fn(),
  getScoringCalibrationPackage: vi.fn(),
  createScoringCalibrationPackage: vi.fn(),
  createScoringCalibrationAnnotation: vi.fn(),
  updateScoringCalibrationAnnotation: vi.fn(),
  decideScoringCalibrationCandidate: vi.fn(),
  getVideoStreamUrl: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  AnalysisApiError: class MockAnalysisApiError extends Error {},
  getCaptureTake: mocks.getCaptureTake,
  listSegments: mocks.listSegments,
  listScoringCalibrationPackages: mocks.listScoringCalibrationPackages,
  getScoringCalibrationPackage: mocks.getScoringCalibrationPackage,
  createScoringCalibrationPackage: mocks.createScoringCalibrationPackage,
  getVideoStreamUrl: mocks.getVideoStreamUrl,
  createScoringCalibrationAnnotation: mocks.createScoringCalibrationAnnotation,
  createScoringCalibrationRevision: vi.fn(),
  decideScoringCalibrationCandidate: mocks.decideScoringCalibrationCandidate,
  lockScoringCalibrationPackage: vi.fn(),
  revokeScoringCalibrationAnnotation: vi.fn(),
  reviewScoringCalibrationPackage: vi.fn(),
  updateScoringCalibrationAnnotation: mocks.updateScoringCalibrationAnnotation,
}));

import { sampleRallySegments, ScoringCalibrationWorkbenchPage } from "./ScoringCalibrationWorkbenchPage";

const take = {
  id: "take-1", field_session_id: "fs-1", capture_mode: "single", source_session_type: "recording",
  source_session_id: "rec-1", status: "completed", started_at: "2026-01-01T00:00:00Z", revision: 0,
  duration_ms: 5000, video_ids: ["video-1"],
};

const emptyPackage = {
  id: "revision-1", package_id: "package-1", capture_take_id: "take-1", revision: 1,
  schema_version: "scoring-calibration-annotation.v1", status: "draft", quality: {
    total_count: 0, confirmed_count: 0, unknown_or_unobservable_count: 0, unmatched_candidate_count: 0,
    conflict_count: 0, evidence_complete_rate: 0, blocking_error_count: 0, warning_count: 0,
  }, validation_issues: [], annotations: [], candidates: [], created_at: "", updated_at: "",
};

const onNavigate = vi.fn();
const rally = {
  id: "rally-1", capture_take_id: "take-1", segment_type: "rally" as const, ordinal: 1, label: "第1分",
  start_ms: 1000, end_ms: 3000, effective_start_ms: 1000, effective_end_ms: 3000, edit_version: 1,
  edit_status: "active" as const, status: "closed" as const, source: "manual", is_highlight: false,
};

describe("ScoringCalibrationWorkbenchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getCaptureTake.mockResolvedValue(take);
    mocks.listSegments.mockResolvedValue([]);
    mocks.listScoringCalibrationPackages.mockResolvedValue([]);
    mocks.getVideoStreamUrl.mockImplementation((id: string) => `/api/videos/${id}/stream`);
  });

  afterEach(() => cleanup());

  it("没有标注包时提供创建 draft 入口并复用 CaptureTake 视频", async () => {
    mocks.createScoringCalibrationPackage.mockResolvedValue(emptyPackage);
    render(<ScoringCalibrationWorkbenchPage fieldSessionId="fs-1" takeId="take-1" onNavigate={onNavigate} />);

    const createButton = await screen.findByRole("button", { name: /创建 draft 标注包/ });
    fireEvent.click(createButton);
    await waitFor(() => expect(mocks.createScoringCalibrationPackage).toHaveBeenCalledWith("take-1", { annotator: "本地标注者" }));
    fireEvent.click(await screen.findByRole("button", { name: "补充字段" }));
    expect(await screen.findByText("人工事实")).toBeTruthy();
    expect(document.querySelector("video")?.getAttribute("src")).toBe("/api/videos/video-1/stream");
  });

  it("locked revision 显示只读状态并提供创建修订入口", async () => {
    const locked = { ...emptyPackage, status: "locked", locked_at: "2026-01-01T00:00:00Z" };
    mocks.listScoringCalibrationPackages.mockResolvedValue([locked]);
    mocks.getScoringCalibrationPackage.mockResolvedValue(locked);
    render(<ScoringCalibrationWorkbenchPage fieldSessionId="fs-1" takeId="take-1" onNavigate={onNavigate} />);

    expect(await screen.findByText("已锁定 · r1")).toBeTruthy();
    expect(screen.getByRole("button", { name: /创建修订/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "补充字段" }));
    expect((screen.getByRole("button", { name: /保存并下一条/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("默认展示回合快速校准并用最小事实复用现有标注 API", async () => {
    const draft = { ...emptyPackage };
    const saved = {
      ...draft,
      annotations: [{
        id: "annotation-1", package_revision_id: draft.id, source: "manual", event_ms: 1500,
        evidence_start_ms: 1000, evidence_end_ms: 2200, video_id: "video-1", rally_segment_id: "rally-1",
        stage: "serve", opportunity_status: "eligible", outcome: "in_play", landing_status: "unobservable",
        landing_zone: "unknown", decision: "accepted", revoked: false, created_at: "", updated_at: "",
      }],
    };
    mocks.listSegments.mockResolvedValue([rally]);
    mocks.listScoringCalibrationPackages.mockResolvedValue([draft]);
    mocks.getScoringCalibrationPackage.mockResolvedValue(draft);
    mocks.createScoringCalibrationAnnotation.mockResolvedValue(saved);

    render(<ScoringCalibrationWorkbenchPage fieldSessionId="fs-1" takeId="take-1" onNavigate={onNavigate} />);

    expect(await screen.findByText("快速校准")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "发球入界" }));
    await waitFor(() => expect(mocks.createScoringCalibrationAnnotation).toHaveBeenCalledWith("revision-1", expect.objectContaining({
      stage: "serve", opportunity_status: "eligible", outcome: "in_play", rally_segment_id: "rally-1",
    })));
    expect(await screen.findByText("快速事实已保存")).toBeTruthy();
  });

  it("抽样队列在回合过多时均匀取 12 条且不重复首尾", () => {
    const rallies = Array.from({ length: 38 }, (_, index) => ({ ...rally, id: `rally-${index}`, ordinal: index + 1 }));
    const sampled = sampleRallySegments(rallies);
    expect(sampled).toHaveLength(12);
    expect(sampled[0].id).toBe("rally-0");
    expect(sampled.at(-1)?.id).toBe("rally-37");
    expect(new Set(sampled.map((item) => item.id)).size).toBe(12);
  });

  it("接发不可观察保存为 unknown，跳过只移动队列不创建事实", async () => {
    const secondRally = { ...rally, id: "rally-2", ordinal: 2, label: "第2分", start_ms: 3500, end_ms: 4800, effective_start_ms: 3500, effective_end_ms: 4800 };
    const draft = { ...emptyPackage };
    const saved = {
      ...draft,
      annotations: [{
        id: "annotation-return", package_revision_id: draft.id, source: "manual", event_ms: 1500,
        evidence_start_ms: 1000, evidence_end_ms: 2200, video_id: "video-1", rally_segment_id: "rally-1",
        stage: "return", opportunity_status: "unobservable", outcome: "unknown", landing_status: "unobservable",
        landing_zone: "unknown", decision: "accepted", revoked: false, created_at: "", updated_at: "",
      }],
    };
    mocks.listSegments.mockResolvedValue([rally, secondRally]);
    mocks.listScoringCalibrationPackages.mockResolvedValue([draft]);
    mocks.getScoringCalibrationPackage.mockResolvedValue(draft);
    mocks.createScoringCalibrationAnnotation.mockResolvedValue(saved);

    render(<ScoringCalibrationWorkbenchPage fieldSessionId="fs-1" takeId="take-1" onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole("button", { name: "接发不可观察" }));
    await waitFor(() => expect(mocks.createScoringCalibrationAnnotation).toHaveBeenCalledWith("revision-1", expect.objectContaining({
      stage: "return", opportunity_status: "unobservable", outcome: "unknown", landing_status: "unobservable", landing_zone: "unknown",
    })));
    expect(screen.getByText("快速事实已保存")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "跳过当前回合" }));
    await waitFor(() => expect(screen.getByText(/当前第 2 条/)).toBeTruthy());
    expect(mocks.createScoringCalibrationAnnotation).toHaveBeenCalledTimes(1);
  });
});
