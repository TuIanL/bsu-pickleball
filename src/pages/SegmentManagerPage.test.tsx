import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getCaptureTake: vi.fn(),
  listSegments: vi.fn(),
  listTimelineEvents: vi.fn(),
  getVideoStreamUrl: vi.fn(),
  patchSegment: vi.fn(),
  splitSegment: vi.fn(),
  mergeSegments: vi.fn(),
  archiveSegment: vi.fn(),
  restoreSegment: vi.fn(),
  createAnalysisBatch: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  getCaptureTake: mocks.getCaptureTake,
  listSegments: mocks.listSegments,
  listTimelineEvents: mocks.listTimelineEvents,
  getVideoStreamUrl: mocks.getVideoStreamUrl,
  patchSegment: mocks.patchSegment,
  splitSegment: mocks.splitSegment,
  mergeSegments: mocks.mergeSegments,
  archiveSegment: mocks.archiveSegment,
  restoreSegment: mocks.restoreSegment,
  createAnalysisBatch: mocks.createAnalysisBatch,
}));

import { SegmentManagerPage } from "./SegmentManagerPage";

const baseTake = {
  id: "ct_1",
  field_session_id: "fs_1",
  capture_mode: "single",
  display_mode: "standard",
  source_session_type: "recording",
  source_session_id: "rec_20260717_105958_e15240",
  status: "completed",
  started_at: "2026-07-17T10:00:00Z",
  revision: 0,
};

function makeTake(overrides: Record<string, unknown> = {}) {
  return { ...baseTake, ...overrides };
}

const onNavigate = vi.fn();

describe("SegmentManagerPage 视频源解析", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getVideoStreamUrl.mockImplementation((id?: string) => (id ? `/api/videos/${id}/stream` : ""));
    mocks.listSegments.mockResolvedValue([]);
    mocks.listTimelineEvents.mockResolvedValue([]);
  });

  it("单摄使用 video_ids[0] 作为播放源，不使用 source_session_id", async () => {
    mocks.getCaptureTake.mockResolvedValue(
      makeTake({ source_session_id: "rec_20260717_105958_e15240", video_ids: ["video-single-a"] }),
    );

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    await waitFor(() => {
      expect(mocks.getVideoStreamUrl).toHaveBeenCalledWith("video-single-a");
    });
    const video = document.querySelector("video");
    await waitFor(() => expect(video?.getAttribute("src")).toBe("/api/videos/video-single-a/stream"));
    // 绝不用采集会话 ID 拼流地址
    expect(mocks.getVideoStreamUrl).not.toHaveBeenCalledWith("rec_20260717_105958_e15240");
  });

  it("双摄生成多机位选项，默认选中机位1", async () => {
    mocks.getCaptureTake.mockResolvedValue(
      makeTake({
        capture_mode: "dual",
        source_session_type: "sync_recording",
        source_session_id: "sync_1",
        video_ids: ["video-sync-a", "video-sync-b"],
      }),
    );

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeTruthy();
    });
    const options = screen.getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["机位1", "机位2"]);
    const video = document.querySelector("video");
    expect(video?.getAttribute("src")).toBe("/api/videos/video-sync-a/stream");
  });

  it("video_ids 为空时显示暂无可用视频回放", async () => {
    mocks.getCaptureTake.mockResolvedValue(makeTake({ video_ids: [] }));

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    await waitFor(() => {
      expect(screen.getByText("暂无可用视频回放")).toBeTruthy();
    });
    expect(document.querySelector("video")).toBeNull();
  });
});

describe("SegmentManagerPage 数据加载独立兜底", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getVideoStreamUrl.mockImplementation((id?: string) => (id ? `/api/videos/${id}/stream` : ""));
    mocks.listSegments.mockResolvedValue([]);
    mocks.listTimelineEvents.mockResolvedValue([]);
  });

  it("take 详情失败展示错误态与重试", async () => {
    mocks.getCaptureTake.mockRejectedValue(new Error("404"));

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_missing" onNavigate={onNavigate} embedded />);

    await waitFor(() => {
      expect(screen.getByText("片段数据加载失败，请重试")).toBeTruthy();
    });
    expect(screen.queryByText("加载中...")).toBeNull();
  });

  it("片段/事件源失败不影响 take 正常渲染与播放", async () => {
    mocks.getCaptureTake.mockResolvedValue(makeTake({ video_ids: ["video-a"] }));
    mocks.listSegments.mockRejectedValue(new Error("segments offline"));
    mocks.listTimelineEvents.mockRejectedValue(new Error("events offline"));

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    await waitFor(() => {
      expect(screen.getByText("创建分析 (0)")).toBeTruthy();
    });
    expect(screen.queryByText("片段数据加载失败，请重试")).toBeNull();
    const video = document.querySelector("video");
    await waitFor(() => expect(video?.getAttribute("src")).toBe("/api/videos/video-a/stream"));
  });
});
