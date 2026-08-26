import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { LibraryItemViewModel } from "../../services/libraryAdapter";
import { LibraryItemWorkspace } from "./LibraryItemWorkspace";

afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
  clearAnalysisResultManifestCache();
  vi.clearAllMocks();
});

vi.mock("../../services/libraryAdapter", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/libraryAdapter")>();
  return { ...actual, resolveLibraryItemByRef: vi.fn() };
});

vi.mock("../../services/analysisClient", () => ({
  deleteAnalysisJob: vi.fn().mockResolvedValue({ job_id: "job-1", status: "deleted" }),
  cancelAnalysisJob: vi.fn().mockResolvedValue({ id: "job-1", status: "processing" }),
  getAnalysisResult: vi.fn().mockResolvedValue(null),
}));

vi.mock("../../pages/VisionPage", () => ({
  VisionPage: ({ jobId, embedded }: { jobId: string; embedded?: boolean }) => (
    <div data-testid="vision-view" data-embedded={embedded ? "true" : "false"}>vision:{jobId}</div>
  ),
}));
vi.mock("../../pages/BallTrajectoryPage", () => ({ BallTrajectoryPage: ({ jobId }: { jobId: string }) => <div>trajectory:{jobId}</div> }));
vi.mock("../report/ReportContent", () => ({ ReportContent: ({ jobId }: { jobId: string }) => <div>report:{jobId}</div> }));
vi.mock("../../pages/MultiviewObservabilityPage", () => ({ MultiviewObservabilityPage: ({ jobId }: { jobId: string }) => <div>multiview-technical:{jobId}</div> }));
vi.mock("../../pages/AnalysisDetailsPage", () => ({ AnalysisDetailsPage: ({ jobId }: { jobId: string }) => <div>single-technical:{jobId}</div> }));

import { resolveLibraryItemByRef } from "../../services/libraryAdapter";
import { deleteAnalysisJob } from "../../services/analysisClient";
import { getAnalysisResult } from "../../services/analysisClient";
import { clearAnalysisResultManifestCache } from "../../services/analysisResultManifestCache";

function item(partial: Partial<LibraryItemViewModel>): LibraryItemViewModel {
  return {
    ref: { kind: "upload", sourceId: "video-1" },
    title: "测试素材",
    sourceType: "upload",
    mediaState: "ready",
    availabilityState: "available",
    analysisState: "not_started",
    displayState: "pending",
    analysisHistoryCount: 0,
    analysisJobs: [],
    ...partial,
  } as LibraryItemViewModel;
}

describe("LibraryItemWorkspace 分析入口", () => {
  it("未分析的单摄录制显示「开始分析」且跳转到分析创建页（不落入结果空态）", async () => {
    const onNavigate = vi.fn();
    const target = item({
      ref: { kind: "recording", sourceId: "rec-1" },
      sourceType: "recording",
      videoId: "video-rec",
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    render(<LibraryItemWorkspace kind="recording" sourceId="rec-1" view="overview" onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByText("开始分析"));
    const called = onNavigate.mock.calls[0][0];
    expect(called).toContain("/analysis/new?videoId=video-rec");
    expect(called).toContain("return=");
    expect(called).not.toContain("view=analysis");
  });

  it("媒体未就绪（无可用路径）时不显示「开始分析」，显示待分析提示", async () => {
    const target = item({
      ref: { kind: "recording", sourceId: "rec-x" },
      sourceType: "recording",
      videoId: undefined,
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    render(<LibraryItemWorkspace kind="recording" sourceId="rec-x" view="overview" onNavigate={vi.fn()} />);
    expect(await screen.findByText("视频就绪后即可开始分析")).toBeTruthy();
    expect(screen.queryByText("开始分析")).toBeNull();
  });

  it("已分析的双摄素材显示「再次分析」多类入口（双摄协同 / A / B 机位）", async () => {
    const target = item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "job-1",
      captureTakeId: "take-9",
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="overview" onNavigate={vi.fn()} />);
    expect(await screen.findByText("双摄协同分析")).toBeTruthy();
    expect(screen.getByText("A 机位分析")).toBeTruthy();
    expect(screen.getByText("B 机位分析")).toBeTruthy();
  });

  it("比赛库素材标题区不显示突出的评分校准入口", async () => {
    (resolveLibraryItemByRef as Mock).mockResolvedValue(item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      fieldSessionId: "session-1",
      captureTakeId: "take-1",
    }));
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="overview" onNavigate={vi.fn()} />);

    await screen.findByText("测试素材");
    expect(screen.queryByRole("button", { name: "评分校准" })).toBeNull();
  });

  it("概览列出历史分析任务，并可删除已完成任务（保留视频）", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const target = item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "job-1",
      captureTakeId: "take-9",
      analysisJobs: [
        { id: "job-1", status: "completed", analysisKind: "multiview", createdAt: "2026-08-01T00:00:00Z" },
        { id: "job-0", status: "processing", analysisKind: "single_view", createdAt: "2026-08-02T00:00:00Z" },
      ],
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="overview" onNavigate={vi.fn()} />);

    // 历史任务两个：完成（删除）与分析中（取消）
    expect(await screen.findByText("历史分析任务")).toBeTruthy();
    expect(screen.getAllByText("双摄协同分析").length).toBeGreaterThan(0);
    expect(screen.getAllByText("删除").length).toBeGreaterThan(0);
    expect(screen.getAllByText("取消").length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByText("删除")[0]);
    expect(deleteAnalysisJob).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("历史 completed/failed 任务分别精确进入结果与技术详情", async () => {
    window.history.replaceState({}, "", "/library/sync_recording/sync-1?view=overview&t=4");
    const target = item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "new",
      primaryResultAnalysisJobId: "new",
      analysisJobs: [
        { id: "new", status: "completed", analysisKind: "multiview", createdAt: "2026-08-03T00:00:00Z" },
        { id: "old", status: "completed", analysisKind: "single_view", executionMode: "late_fusion_v1", createdAt: "2026-08-02T00:00:00Z", clipStartMs: 0, clipEndMs: 60_000 },
        { id: "bad", status: "failed", analysisKind: "multiview", createdAt: "2026-08-01T00:00:00Z" },
      ],
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    const onNavigate = vi.fn();
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="overview" onNavigate={onNavigate} />);

    const resultButtons = await screen.findAllByRole("button", { name: "查看结果" });
    fireEvent.click(resultButtons[1]);
    expect(onNavigate).toHaveBeenLastCalledWith(expect.stringMatching(/view=analysis.*analysisJob=old|analysisJob=old.*view=analysis/), { replace: true });
    expect(onNavigate.mock.calls.at(-1)?.[0]).toContain("t=4");

    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));
    expect(onNavigate).toHaveBeenLastCalledWith(expect.stringMatching(/view=technical.*analysisJob=bad|analysisJob=bad.*view=technical/), { replace: true });
  });

  it("显式历史版本显示选中态与查看最新版本入口", async () => {
    window.history.replaceState({}, "", "/library/sync_recording/sync-1?view=overview&analysisJob=old");
    (resolveLibraryItemByRef as Mock).mockResolvedValue(item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "new",
      primaryResultAnalysisJobId: "new",
      analysisJobs: [
        { id: "new", status: "completed", analysisKind: "multiview", createdAt: "2026-08-03T00:00:00Z" },
        { id: "old", status: "completed", analysisKind: "multiview", createdAt: "2026-08-02T00:00:00Z" },
      ],
    }));
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="overview" onNavigate={vi.fn()} />);
    expect(await screen.findByText("当前版本")).toBeTruthy();
    expect(screen.getByRole("button", { name: "查看最新版本" })).toBeTruthy();
  });

  it("伪造跨素材 analysisJob 不请求产物并 replace 清理参数", async () => {
    window.history.replaceState({}, "", "/library/sync_recording/sync-1?view=analysis&analysisJob=foreign&t=7&foo=bar");
    (resolveLibraryItemByRef as Mock).mockResolvedValue(item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "new",
      primaryResultAnalysisJobId: "new",
      analysisJobs: [{ id: "new", status: "completed", analysisKind: "multiview", createdAt: "2026-08-03T00:00:00Z" }],
    }));
    const onNavigate = vi.fn();
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="analysis" onNavigate={onNavigate} />);
    await waitFor(() => expect(onNavigate).toHaveBeenCalled());
    expect(getAnalysisResult).not.toHaveBeenCalled();
    expect(onNavigate).toHaveBeenCalledWith(expect.stringContaining("view=analysis&t=7&foo=bar"), { replace: true });
    expect(onNavigate.mock.calls.flat().join(" ")).not.toContain("analysisJob=foreign");
  });

  it("四个结果 Content 与 Tab 跳转始终绑定同一个显式历史 Job", async () => {
    const target = item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "new",
      primaryResultAnalysisJobId: "new",
      analysisJobs: [
        { id: "new", status: "completed", analysisKind: "multiview", createdAt: "2026-08-03T00:00:00Z" },
        { id: "old", status: "completed", analysisKind: "single_view", createdAt: "2026-08-02T00:00:00Z" },
      ],
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    vi.mocked(getAnalysisResult).mockResolvedValue({
      job_id: "old",
      status: "completed",
      tracks: [{ track_id: "Player_1", court_point: { x: 10, y: 20 } }],
      metrics: { distances: [], speeds: [], kitchen_dwell: [] },
      artifacts: { ball_trajectory_url: "/old/ball.json" },
    } as never);
    const onNavigate = vi.fn();

    for (const [selectedView, expected] of [
      ["analysis", "vision:old"],
      ["trajectory", "trajectory:old"],
      ["report", "report:old"],
      ["technical", "single-technical:old"],
    ] as const) {
      window.history.replaceState({}, "", `/library/sync_recording/sync-1?view=${selectedView}&analysisJob=old&t=9`);
      const rendered = render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view={selectedView} onNavigate={onNavigate} />);
      expect(await screen.findByText(expected)).toBeTruthy();
      rendered.unmount();
    }

    window.history.replaceState({}, "", "/library/sync_recording/sync-1?view=analysis&analysisJob=old&t=9");
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="analysis" onNavigate={onNavigate} />);
    await screen.findByText("vision:old");
    fireEvent.click(screen.getByRole("button", { name: "球路" }));
    expect(onNavigate).toHaveBeenLastCalledWith(expect.stringMatching(/analysisJob=old/), { replace: true });
    expect(onNavigate.mock.calls.at(-1)?.[0]).toContain("t=9");
  });

  it("刷新恢复 displayView，并在嵌入式 Tab 跳转中保留机位参数", async () => {
    window.history.replaceState({}, "", "/library/sync_recording/sync-1?view=analysis&analysisJob=old&displayView=cam_2");
    const target = item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "old",
      primaryResultAnalysisJobId: "old",
      analysisJobs: [{ id: "old", status: "completed", analysisKind: "multiview", createdAt: "2026-08-02T00:00:00Z" }],
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    const onNavigate = vi.fn();
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="analysis" onNavigate={onNavigate} />);

    expect((await screen.findByTestId("vision-view")).getAttribute("data-embedded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "球路" }));
    expect(onNavigate).toHaveBeenLastCalledWith(expect.stringContaining("displayView=cam_2"), { replace: true });
    expect(onNavigate.mock.calls.at(-1)?.[0]).toContain("analysisJob=old");
  });

  it("completed 但没有有效报告证据时报告 Tab 置灰，点击不会导航", async () => {
    const target = item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "empty",
      primaryResultAnalysisJobId: "empty",
      analysisJobs: [{ id: "empty", status: "completed", analysisKind: "single_view", createdAt: "2026-08-02T00:00:00Z" }],
    });
    (resolveLibraryItemByRef as Mock).mockResolvedValue(target);
    vi.mocked(getAnalysisResult).mockResolvedValue({
      job_id: "empty", status: "completed", tracks: [],
      metrics: { distances: [], speeds: [], kitchen_dwell: [] }, artifacts: {},
    } as never);
    const onNavigate = vi.fn();
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="overview" onNavigate={onNavigate} />);

    const reportTab = await screen.findByRole("button", { name: "报告" });
    expect((reportTab as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(reportTab);
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("删除当前 selected Job 后 replace 清理版本参数并定向刷新", async () => {
    window.history.replaceState({}, "", "/library/sync_recording/sync-1?view=overview&analysisJob=old&t=3");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    (resolveLibraryItemByRef as Mock).mockResolvedValue(item({
      ref: { kind: "sync_recording", sourceId: "sync-1" },
      sourceType: "sync_recording",
      analysisState: "succeeded",
      primaryAnalysisJobId: "new",
      primaryResultAnalysisJobId: "new",
      analysisJobs: [
        { id: "new", status: "completed", analysisKind: "multiview", createdAt: "2026-08-03T00:00:00Z" },
        { id: "old", status: "completed", analysisKind: "multiview", createdAt: "2026-08-02T00:00:00Z" },
      ],
    }));
    const onNavigate = vi.fn();
    render(<LibraryItemWorkspace kind="sync_recording" sourceId="sync-1" view="overview" onNavigate={onNavigate} />);
    await screen.findByText("当前版本");
    fireEvent.click(screen.getAllByRole("button", { name: "删除" })[1]);
    await waitFor(() => expect(deleteAnalysisJob).toHaveBeenCalledWith("old"));
    expect(onNavigate).toHaveBeenCalledWith(expect.stringContaining("view=overview&t=3"), { replace: true });
    expect(onNavigate.mock.calls.flat().join(" ")).not.toContain("analysisJob=old");
  });
});
