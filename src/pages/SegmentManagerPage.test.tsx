import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createRallySegment: vi.fn(),
  getCaptureTake: vi.fn(),
  getBoundaryReview: vi.fn(),
  listSegments: vi.fn(),
  listTimelineEvents: vi.fn(),
  getVideoStreamUrl: vi.fn(),
  patchSegment: vi.fn(),
  reviewSegmentBoundary: vi.fn(),
  splitSegment: vi.fn(),
  mergeSegments: vi.fn(),
  archiveSegment: vi.fn(),
  restoreSegment: vi.fn(),
  createAnalysisBatch: vi.fn(),
  renumberRallyOrdinals: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  createRallySegment: mocks.createRallySegment,
  getCaptureTake: mocks.getCaptureTake,
  getBoundaryReview: mocks.getBoundaryReview,
  listSegments: mocks.listSegments,
  listTimelineEvents: mocks.listTimelineEvents,
  getVideoStreamUrl: mocks.getVideoStreamUrl,
  patchSegment: mocks.patchSegment,
  reviewSegmentBoundary: mocks.reviewSegmentBoundary,
  splitSegment: mocks.splitSegment,
  mergeSegments: mocks.mergeSegments,
  archiveSegment: mocks.archiveSegment,
  restoreSegment: mocks.restoreSegment,
  createAnalysisBatch: mocks.createAnalysisBatch,
  renumberRallyOrdinals: mocks.renumberRallyOrdinals,
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
    mocks.getBoundaryReview.mockResolvedValue(emptyBoundaryReview());
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
    mocks.getBoundaryReview.mockResolvedValue(emptyBoundaryReview());
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

describe("SegmentManagerPage 片段回放与交互同步", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getVideoStreamUrl.mockImplementation((id?: string) => (id ? `/api/videos/${id}/stream` : ""));
    mocks.getCaptureTake.mockResolvedValue(makeTake({ video_ids: ["video-a"], duration_ms: 10000 }));
    mocks.listSegments.mockResolvedValue([
      {
        id: "rally-1", segment_type: "rally", ordinal: 1, label: "第1分", start_ms: 1000, end_ms: 5000,
        effective_start_ms: 1000, effective_end_ms: 5000, edit_version: 2, edit_status: "active", status: "closed",
        source: "algorithm", is_highlight: false,
      },
    ]);
    mocks.listTimelineEvents.mockResolvedValue([{ id: "event-1", event_type: "rally_start", timestamp_ms: 1200 }]);
    mocks.getBoundaryReview.mockResolvedValue({
      ...emptyBoundaryReview(),
      total_count: 1,
      pending_count: 1,
      segments: [{
        id: "rally-1", segment_type: "rally", ordinal: 1, label: "第1分", start_ms: 1000, end_ms: 5000,
        effective_start_ms: 1000, effective_end_ms: 5000, edit_version: 2, edit_status: "active", status: "closed",
        source: "algorithm", is_highlight: false, boundary_review_status: "pending",
      }],
    });
  });

  it("点击片段开始播放并同步高亮，选择框不触发播放", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    const label = await screen.findByTitle("单击播放；双击编辑标签");
    const row = label.parentElement!;
    fireEvent.click(row);
    expect(play).toHaveBeenCalledTimes(1);
    expect(row.className).toContain("border-[#2F80ED]");
    expect(document.querySelector('[data-playback-mode="segment"]')).toBeTruthy();

    play.mockClear();
    fireEvent.click(row.querySelector("input")!);
    expect(play).not.toHaveBeenCalled();
  });

  it("双击标签只进入编辑，不启动片段播放", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    const label = await screen.findByTitle("单击播放；双击编辑标签");
    fireEvent.doubleClick(label);
    expect(screen.getByDisplayValue("第1分")).toBeTruthy();
    expect(play).not.toHaveBeenCalled();
  });

  it("复用片段管理进入双摄边界复核，并保存确认决定", async () => {
    mocks.getCaptureTake.mockResolvedValue(makeTake({
      capture_mode: "dual",
      video_ids: ["video-a", "video-b"],
      duration_ms: 10000,
    }));
    mocks.reviewSegmentBoundary.mockResolvedValue({
      ...(await mocks.getBoundaryReview()).segments[0],
      edit_version: 3,
      boundary_review_status: "confirmed",
    });

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));
    expect(await screen.findByText("有效回合边界复核")).toBeTruthy();
    expect(document.querySelectorAll("video")).toHaveLength(2);
    const activeBoundaryReview = await screen.findByTestId("active-boundary-review");
    expect(activeBoundaryReview.textContent).toContain("正在修改：第 1 分");
    expect(activeBoundaryReview.textContent).toContain("下方标定按钮只会作用于当前这一分");
    fireEvent.click(screen.getByRole("button", { name: /确认并下一条/ }));
    await waitFor(() => expect(mocks.reviewSegmentBoundary).toHaveBeenCalledWith("rally-1", {
      decision: "confirmed",
      expected_version: 2,
      start_ms: 1000,
      end_ms: 5000,
    }));
  });

  it("双摄复核中点击任意视角的播放按钮都会同步控制两个视频", async () => {
    mocks.getCaptureTake.mockResolvedValue(makeTake({
      capture_mode: "dual",
      video_ids: ["video-a", "video-b"],
      duration_ms: 10000,
    }));
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));
    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(2));
    play.mockClear();
    pause.mockClear();
    const playbackButtons = screen.getAllByTitle("播放/暂停");
    fireEvent.click(playbackButtons[1]);
    expect(play).toHaveBeenCalledTimes(2);

    const videos = document.querySelectorAll("video");
    Object.defineProperty(videos[1], "paused", { configurable: true, get: () => false });
    Object.defineProperty(videos[1], "currentTime", { configurable: true, writable: true, value: 1.25 });
    fireEvent.click(playbackButtons[1]);
    expect(pause).toHaveBeenCalledTimes(2);

    play.mockRestore();
    pause.mockRestore();
  });

  it("复核队列中选中回合只定位，不自动播放", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));
    const row = (await screen.findByTitle("点击播放边界前后 3 秒")).parentElement!;
    fireEvent.click(row);

    expect(play).not.toHaveBeenCalled();
    expect(row.className).toContain("border-[#2F80ED]");
    play.mockRestore();
  });

  it("边界倒置的回合仍可选中，并可通过当前帧重新修正结束时间", async () => {
    const invalidRally = {
      id: "rally-invalid", segment_type: "rally", ordinal: 8, label: "第8分", start_ms: 119000, end_ms: 63000,
      effective_start_ms: 119000, effective_end_ms: 63000, edit_version: 2, edit_status: "active", status: "closed",
      source: "algorithm", is_highlight: false, boundary_review_status: "pending",
    };
    const repairedRally = {
      ...invalidRally,
      corrected_start_ms: 119000,
      corrected_end_ms: 124000,
      effective_end_ms: 124000,
      edit_version: 3,
      boundary_review_status: "corrected",
    };
    mocks.listSegments.mockResolvedValue([invalidRally]);
    mocks.getBoundaryReview.mockReset();
    mocks.getBoundaryReview
      .mockResolvedValueOnce({ ...emptyBoundaryReview(), total_count: 1, pending_count: 1, segments: [invalidRally] })
      .mockResolvedValueOnce({ ...emptyBoundaryReview(), total_count: 1, corrected_count: 1, segments: [repairedRally] });
    mocks.reviewSegmentBoundary.mockResolvedValue(repairedRally);

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));
    const row = await screen.findByTitle("点击播放边界前后 3 秒");
    fireEvent.click(row.parentElement!);
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 8 分"));

    const video = document.querySelector("video")!;
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 124 });
    fireEvent.timeUpdate(video);
    fireEvent.click(screen.getByRole("button", { name: "当前帧设为结束" }));

    await waitFor(() => expect(mocks.reviewSegmentBoundary).toHaveBeenCalledWith("rally-invalid", {
      decision: "corrected",
      expected_version: 2,
      start_ms: 119000,
      end_ms: 124000,
    }));
  });

  it("复核模式下明确选择的回合不会被播放头、下一待复核或确认流程改回第一分", async () => {
    const rallyOne = {
      id: "rally-1", segment_type: "rally", ordinal: 1, label: "第1分", start_ms: 1000, end_ms: 5000,
      effective_start_ms: 1000, effective_end_ms: 5000, edit_version: 2, edit_status: "active", status: "closed",
      source: "algorithm", is_highlight: false, boundary_review_status: "pending",
    };
    const rallyTwo = {
      id: "rally-2", segment_type: "rally", ordinal: 2, label: "第2分", start_ms: 6000, end_ms: 9000,
      effective_start_ms: 6000, effective_end_ms: 9000, edit_version: 1, edit_status: "active", status: "closed",
      source: "algorithm", is_highlight: false, boundary_review_status: "pending",
    };
    mocks.listSegments.mockResolvedValue([rallyOne, rallyTwo]);
    mocks.getBoundaryReview.mockResolvedValue({
      ...emptyBoundaryReview(),
      total_count: 2,
      pending_count: 2,
      segments: [rallyOne, rallyTwo],
    });
    mocks.reviewSegmentBoundary.mockResolvedValue({ ...rallyTwo, boundary_review_status: "confirmed" });

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));

    const rows = await screen.findAllByTitle("点击播放边界前后 3 秒");
    fireEvent.click(rows[1].parentElement!);
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 2 分"));

    // 播放头定位到第一分的时间，也不应改变当前正在修改的第二分。
    const video = document.querySelector("video")!;
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 2 });
    fireEvent.timeUpdate(video);
    expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 2 分");

    fireEvent.click(screen.getByRole("button", { name: "下一待复核" }));
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 1 分"));

    fireEvent.click((await screen.findAllByTitle("点击播放边界前后 3 秒"))[1].parentElement!);
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 2 分"));
    fireEvent.click(screen.getByRole("button", { name: /确认并下一条/ }));
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 1 分"));
  });

  it("可以用共享播放头补录漏记回合，并将新回合加入待复核", async () => {
    const rallyOne = {
      id: "rally-1", segment_type: "rally", ordinal: 1, label: "第1分", start_ms: 1000, end_ms: 5000,
      effective_start_ms: 1000, effective_end_ms: 5000, edit_version: 2, edit_status: "active", status: "closed",
      source: "algorithm", is_highlight: false, boundary_review_status: "confirmed",
    };
    const createdRally = {
      id: "rally-new", segment_type: "rally", ordinal: 2, label: "第2分", start_ms: 6000, end_ms: 8000,
      effective_start_ms: 6000, effective_end_ms: 8000, edit_version: 0, edit_status: "active", status: "closed",
      source: "manual", is_highlight: false, boundary_review_status: "pending",
    };
    const initialReview = {
      ...emptyBoundaryReview(),
      total_count: 1,
      confirmed_count: 1,
      segments: [rallyOne],
    };
    const afterCreateReview = {
      ...emptyBoundaryReview(),
      total_count: 2,
      pending_count: 1,
      confirmed_count: 1,
      segments: [rallyOne, createdRally],
    };
    mocks.listSegments.mockResolvedValue([rallyOne]);
    mocks.getBoundaryReview.mockReset();
    mocks.getBoundaryReview.mockResolvedValueOnce(initialReview).mockResolvedValueOnce(afterCreateReview);
    mocks.createRallySegment.mockResolvedValue(createdRally);

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));
    fireEvent.click(screen.getByRole("button", { name: "新增漏记回合" }));
    expect(screen.getByTestId("new-rally-draft").textContent).toContain("正在补录一个漏记的有效回合");

    const video = document.querySelector("video")!;
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 6 });
    fireEvent.timeUpdate(video);
    fireEvent.click(screen.getByRole("button", { name: "当前帧设为新增开始" }));
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 8 });
    fireEvent.timeUpdate(video);
    fireEvent.click(screen.getByRole("button", { name: "当前帧设为新增结束" }));
    fireEvent.click(screen.getByRole("button", { name: "创建回合并加入待复核" }));

    await waitFor(() => expect(mocks.createRallySegment).toHaveBeenCalledWith("ct_1", {
      start_ms: 6000,
      end_ms: 8000,
    }));
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 2 分"));
  });

  it("可以从当前分开始连续修正后续分序号", async () => {
    const rallyOne = {
      id: "rally-1", segment_type: "rally", ordinal: 1, label: "第1分", start_ms: 1000, end_ms: 5000,
      effective_start_ms: 1000, effective_end_ms: 5000, edit_version: 2, edit_status: "active", status: "closed",
      source: "algorithm", is_highlight: false, boundary_review_status: "confirmed",
    };
    const rallyTwo = {
      id: "rally-2", segment_type: "rally", ordinal: 1, label: "第1分", start_ms: 6000, end_ms: 9000,
      effective_start_ms: 6000, effective_end_ms: 9000, edit_version: 3, edit_status: "active", status: "closed",
      source: "algorithm", is_highlight: false, boundary_review_status: "confirmed",
    };
    const renumberedRallyTwo = { ...rallyTwo, ordinal: 2, label: "第2分", edit_version: 4 };
    mocks.listSegments.mockResolvedValue([rallyOne, rallyTwo]);
    mocks.getBoundaryReview.mockReset();
    mocks.getBoundaryReview
      .mockResolvedValueOnce({ ...emptyBoundaryReview(), total_count: 2, confirmed_count: 2, segments: [rallyOne, rallyTwo] })
      .mockResolvedValueOnce({ ...emptyBoundaryReview(), total_count: 2, confirmed_count: 2, segments: [rallyOne, renumberedRallyTwo] });
    mocks.renumberRallyOrdinals.mockResolvedValue({
      schema_version: "manual-rally-ordinal.v1",
      capture_take_id: "ct_1",
      operation_id: "op-ordinal",
      mode: "from_anchor",
      start_ordinal: 2,
      segments: [rallyOne, renumberedRallyTwo],
    });

    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));
    const rows = await screen.findAllByTitle("点击播放边界前后 3 秒");
    fireEvent.click(rows[1].parentElement!);
    fireEvent.click(await screen.findByRole("button", { name: "调整分序号" }));

    expect(screen.getByTestId("rally-ordinal-editor").textContent).toContain("正在调整：第 1 分");
    const input = screen.getByLabelText(/当前所选这一分应为第/);
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "从当前分开始连续编号" }));

    await waitFor(() => expect(mocks.renumberRallyOrdinals).toHaveBeenCalledWith("ct_1", {
      mode: "from_anchor",
      anchor_segment_id: "rally-2",
      start_ordinal: 2,
    }));
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 2 分"));
  });

  it("只标定开始时间时保持待复核，不提交完整复核决定", async () => {
    const reviewCall = mocks.reviewSegmentBoundary;
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: /有效回合复核/ }));
    const video = document.querySelector("video")!;
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 2 });
    fireEvent.timeUpdate(video);
    fireEvent.click(await screen.findByRole("button", { name: "当前帧设为开始" }));

    expect(reviewCall).not.toHaveBeenCalled();
    expect(await screen.findByText("起点已标定，仍待标定结束时间；当前回合不会算作复核完成。")).toBeTruthy();
    expect((screen.getByRole("button", { name: "确认并下一条" }) as HTMLButtonElement).disabled).toBe(true);
    expect((await screen.findByTitle("点击播放边界前后 3 秒")).parentElement?.textContent).toContain("起点已标");
  });
});

function emptyBoundaryReview() {
  return {
    schema_version: "match-state-boundary-review.v1",
    capture_take_id: "ct_1",
    total_count: 0,
    pending_count: 0,
    confirmed_count: 0,
    corrected_count: 0,
    excluded_count: 0,
    segments: [],
  };
}
