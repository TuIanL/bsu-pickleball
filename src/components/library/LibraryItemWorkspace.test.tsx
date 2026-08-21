import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { LibraryItemViewModel } from "../../services/libraryAdapter";
import { LibraryItemWorkspace } from "./LibraryItemWorkspace";

afterEach(() => cleanup());

vi.mock("../../services/libraryAdapter", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/libraryAdapter")>();
  return { ...actual, resolveLibraryItemByRef: vi.fn() };
});

vi.mock("../../services/analysisClient", () => ({
  deleteAnalysisJob: vi.fn().mockResolvedValue({ job_id: "job-1", status: "deleted" }),
  cancelAnalysisJob: vi.fn().mockResolvedValue({ id: "job-1", status: "processing" }),
}));

import { resolveLibraryItemByRef } from "../../services/libraryAdapter";
import { deleteAnalysisJob } from "../../services/analysisClient";

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
});