import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createRallySegment: vi.fn(),
  getCaptureTake: vi.fn(),
  getFormalSegmentationSummary: vi.fn(),
  getBoundaryReview: vi.fn(),
  getMatchStateCandidates: vi.fn(),
  decideMatchStateCandidate: vi.fn(),
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
  getFormalSegmentationSummary: mocks.getFormalSegmentationSummary,
  getBoundaryReview: mocks.getBoundaryReview,
  getMatchStateCandidates: mocks.getMatchStateCandidates,
  decideMatchStateCandidate: mocks.decideMatchStateCandidate,
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

beforeEach(() => {
  window.history.pushState({}, "", "/");
});

function enableBoundaryReviewMode() {
  window.history.pushState({}, "", "/capture/fs_1/takes/ct_1?mode=boundary-review");
}

describe("SegmentManagerPage 视频源解析", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getVideoStreamUrl.mockImplementation((id?: string) => (id ? `/api/videos/${id}/stream` : ""));
    mocks.listSegments.mockResolvedValue([]);
    mocks.getBoundaryReview.mockResolvedValue(emptyBoundaryReview());
    mocks.getMatchStateCandidates.mockResolvedValue({
      schema_version: "match-state-candidate-review.v1",
      status: "unavailable",
      reason: "candidate_artifact_missing",
      capture_take_id: "ct_1",
      revision: 0,
      candidates: [],
    });
    mocks.listTimelineEvents.mockResolvedValue([]);
  });

  it("单摄使用 video_ids[0] 作为播放源，不使用 source_session_id", async () => {
    mocks.getCaptureTake.mockResolvedValue(
      makeTake({ source_session_id: "rec_20260717_105958_e15240", video_ids: ["video-single-a"] }),
    );
    mocks.getFormalSegmentationSummary.mockResolvedValue({
      capture_take_id: "ct_1", status: "unavailable", run_id: null, model_package_id: null,
      model_version: null, generated_at: null, segment_count: 0, window_plan_hash: null,
      artifact_available: false,
    });

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
    mocks.getFormalSegmentationSummary.mockResolvedValue({
      capture_take_id: "ct_1", status: "unavailable", run_id: null, model_package_id: null,
      model_version: null, generated_at: null, segment_count: 0, window_plan_hash: null,
      artifact_available: false,
    });
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
      expect(document.querySelector("video")?.getAttribute("src")).toBe("/api/videos/video-a/stream");
    });
    expect(screen.queryByText(/创建分析/)).toBeNull();
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
        source: "algorithm", segmentation_run_id: "seg_run_1", is_highlight: false,
      },
    ]);
    mocks.getFormalSegmentationSummary.mockResolvedValue({
      capture_take_id: "ct_1", status: "succeeded", run_id: "seg_run_1", model_package_id: "match_state_v1",
      model_version: "rgb_structured_fusion_v1", generated_at: "2026-07-17T10:01:00Z", segment_count: 1,
      window_plan_hash: "abc", artifact_available: true,
    });
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

  it("生产片段页只读展示模型结果，不渲染编辑和批量分析动作", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    const row = await screen.findByTitle("模型自动结果为只读；如需 QA 复核请使用内部 boundary-review 模式");
    fireEvent.click(row);
    expect(play).toHaveBeenCalledTimes(1);
    expect(row.className).toContain("border-[#2F80ED]");
    expect(document.querySelector('[data-playback-mode="segment"]')).toBeTruthy();
    expect(row.querySelector("input")).toBeNull();
    expect(screen.queryByTitle("拆分")).toBeNull();
    expect(screen.queryByTitle("归档")).toBeNull();
    expect(screen.queryByText(/创建分析/)).toBeNull();
    expect(mocks.patchSegment).not.toHaveBeenCalled();
    expect(mocks.createAnalysisBatch).not.toHaveBeenCalled();
  });

  it("生产片段页在自动回合区域展示正式运行摘要一次", async () => {
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    expect(await screen.findByText("模型 rgb_structured_fusion_v1")).toBeTruthy();
    expect(screen.getByText("1 个回合")).toBeTruthy();
    expect(screen.getAllByText("正式结果")).toHaveLength(1);
  });

  it("生产片段页双击标签也不会打开编辑器", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);

    const label = (await screen.findByTitle("模型自动结果为只读；如需 QA 复核请使用内部 boundary-review 模式")).querySelector("span")!;
    fireEvent.doubleClick(label);
    expect(screen.queryByDisplayValue("第1分")).toBeNull();
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

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
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

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
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

  it("复核队列中选择回合从有效起点播放，并在有效终点自动暂停", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    const row = (await screen.findByTitle("点击从该回合起点播放，到终点自动暂停")).parentElement!;
    const video = document.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 0 });
    fireEvent.loadedMetadata(video);
    fireEvent.click(row);

    expect(play).toHaveBeenCalledTimes(1);
    expect(video.currentTime).toBe(1);
    expect(row.className).toContain("border-[#2F80ED]");

    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 5 });
    fireEvent.timeUpdate(video);
    expect(pause).toHaveBeenCalled();

    play.mockRestore();
    pause.mockRestore();
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

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    const row = await screen.findByTitle("点击从该回合起点播放，到终点自动暂停");
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

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);

    const rows = await screen.findAllByTitle("点击从该回合起点播放，到终点自动暂停");
    fireEvent.click(rows[1].parentElement!);
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 2 分"));

    // 播放头定位到第一分的时间，也不应改变当前正在修改的第二分。
    const video = document.querySelector("video")!;
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 2 });
    fireEvent.timeUpdate(video);
    expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 2 分");

    fireEvent.click(screen.getByRole("button", { name: "下一待复核" }));
    await waitFor(() => expect(screen.getByTestId("active-boundary-review").textContent).toContain("正在修改：第 1 分"));

    fireEvent.click((await screen.findAllByTitle("点击从该回合起点播放，到终点自动暂停"))[1].parentElement!);
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

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole("button", { name: "新增漏记回合" }));
    expect(screen.getByTestId("new-rally-draft").textContent).toContain("正在补录一个漏记的有效回合");

    const video = await waitFor(() => {
      const value = document.querySelector("video");
      expect(value).toBeTruthy();
      return value as HTMLVideoElement;
    });
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

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    const rows = await screen.findAllByTitle("点击从该回合起点播放，到终点自动暂停");
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
    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    const video = await waitFor(() => {
      const value = document.querySelector("video");
      expect(value).toBeTruthy();
      return value as HTMLVideoElement;
    });
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 2 });
    fireEvent.timeUpdate(video);
    fireEvent.click(await screen.findByRole("button", { name: "当前帧设为开始" }));

    expect(reviewCall).not.toHaveBeenCalled();
    expect(await screen.findByText("起点已标定，仍待标定结束时间；当前回合不会算作复核完成。")).toBeTruthy();
    expect((screen.getByRole("button", { name: "确认并下一条" }) as HTMLButtonElement).disabled).toBe(true);
    expect((await screen.findByTitle("点击从该回合起点播放，到终点自动暂停")).parentElement?.textContent).toContain("起点已标");
  });

  it("在现有复核工作台展示并接受模型候选", async () => {
    const available = {
      schema_version: "match-state-candidate-review.v1",
      status: "available",
      capture_take_id: "ct_1",
      revision: 0,
      model: { model_version: "rgb_structured_fusion_v1" },
      unknown_rate: 0.12,
      candidates: [{
        candidate_id: "candidate_0001", segment_index: 1, start_ms: 1000, end_ms: 5000,
        duration_ms: 4000, confidence: 0.93, evidence_window_count: 48, status: "unreviewed",
      }],
    };
    mocks.getMatchStateCandidates.mockResolvedValue(available);
    mocks.decideMatchStateCandidate.mockResolvedValue({
      schema_version: "match-state-candidate-review.v1", capture_take_id: "ct_1",
      record: { candidate_id: "candidate_0001", decision: "accepted" }, segment: null,
    });

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    expect(await screen.findByTestId("model-candidate-review")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "接受原边界" }));

    await waitFor(() => expect(mocks.decideMatchStateCandidate).toHaveBeenCalledWith("ct_1", "candidate_0001", {
      decision: "accepted",
      expected_revision: 0,
    }));
  });

  it("模型候选播放从候选起点开始，并在候选终点自动暂停", async () => {
    mocks.getMatchStateCandidates.mockResolvedValue({
      schema_version: "match-state-candidate-review.v1",
      status: "available",
      capture_take_id: "ct_1",
      revision: 0,
      model: { model_version: "rgb_only_v1" },
      unknown_rate: 0.01,
      candidates: [{
        candidate_id: "candidate-1", segment_index: 1, start_ms: 1000, end_ms: 5000,
        duration_ms: 4000, confidence: 0.99, evidence_window_count: 8, status: "unreviewed",
      }],
    });
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    await screen.findByTestId("model-candidate-review");

    const video = document.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 0 });
    fireEvent.loadedMetadata(video);
    fireEvent.click(screen.getByRole("button", { name: "#1 · 待复核" }));
    expect(video.currentTime).toBe(1);
    expect(play).toHaveBeenCalledTimes(1);
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 5 });
    fireEvent.timeUpdate(video);
    expect(pause).toHaveBeenCalled();

    play.mockRestore();
    pause.mockRestore();
  });
});

describe("SegmentManagerPage 自动回合回放提示", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const autoRallyFixtures = [
    {
      id: "auto-1", segment_type: "rally", ordinal: 1, label: "第1回合", start_ms: 1000, end_ms: 5000,
      effective_start_ms: 1000, effective_end_ms: 5000, edit_version: 1, edit_status: "active", status: "inferred",
      source: "algorithm", segmentation_run_id: "seg_run_1", is_highlight: false,
    },
    {
      id: "auto-2", segment_type: "rally", ordinal: 2, label: "第2回合", start_ms: 7000, end_ms: 9000,
      effective_start_ms: 7000, effective_end_ms: 9000, edit_version: 1, edit_status: "active", status: "inferred",
      source: "algorithm", segmentation_run_id: "seg_run_1", is_highlight: false,
    },
    {
      id: "manual-1", segment_type: "rally", ordinal: 3, label: "人工标记回合", start_ms: 9500, end_ms: 10500,
      effective_start_ms: 9500, effective_end_ms: 10500, edit_version: 1, edit_status: "active", status: "closed",
      source: "manual", segmentation_run_id: null, is_highlight: false,
    },
  ];

  const succeededSummary = {
    capture_take_id: "ct_1", status: "succeeded", run_id: "seg_run_1", model_package_id: "match_state_v1",
    model_version: "rgb_structured_fusion_v1", generated_at: "2026-07-17T10:01:00Z", segment_count: 2,
    window_plan_hash: "abc", artifact_available: true,
  };

  function primePage(segments: unknown[] = autoRallyFixtures, summary: unknown = succeededSummary) {
    mocks.getVideoStreamUrl.mockImplementation((id?: string) => (id ? `/api/videos/${id}/stream` : ""));
    mocks.getCaptureTake.mockResolvedValue(makeTake({ video_ids: ["video-a"], duration_ms: 12000 }));
    mocks.listSegments.mockResolvedValue(segments);
    mocks.getFormalSegmentationSummary.mockResolvedValue(summary);
    mocks.listTimelineEvents.mockResolvedValue([]);
    mocks.getBoundaryReview.mockResolvedValue(emptyBoundaryReview());
    mocks.getMatchStateCandidates.mockResolvedValue({
      schema_version: "match-state-candidate-review.v1",
      status: "unavailable",
      reason: "candidate_artifact_missing",
      capture_take_id: "ct_1",
      revision: 0,
      candidates: [],
    });
  }

  async function renderAndLoadVideo() {
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);
    await waitFor(() => expect(mocks.getVideoStreamUrl).toHaveBeenCalledWith("video-a"));
    const video = document.querySelector("video")!;
    await waitFor(() => expect(video.getAttribute("src")).toBe("/api/videos/video-a/stream"));
    Object.defineProperty(video, "duration", { configurable: true, value: 12 });
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 0 });
    fireEvent.loadedMetadata(video);
    return video;
  }

  function seekTo(video: Element, seconds: number) {
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: seconds });
    fireEvent.timeUpdate(video);
  }

  const cueElement = () => document.querySelector("[data-auto-rally-cue]");
  const modelRows = () => screen.queryAllByTitle("模型自动结果为只读；如需 QA 复核请使用内部 boundary-review 模式");

  it("播放头进入不同自动回合时中央提示序号随之变化，人工片段不触发", async () => {
    primePage();
    const video = await renderAndLoadVideo();
    await waitFor(() => expect(screen.getByText("2 个回合")).toBeTruthy());

    seekTo(video, 2);
    expect(cueElement()?.textContent).toContain("第1回合");
    expect(cueElement()?.getAttribute("data-auto-rally-cue")).toBe("visible");

    seekTo(video, 8);
    expect(cueElement()?.textContent).toContain("第2回合");

    // 人工标记区间（9.5s–10.5s）不属于自动回合：不显示中央提示
    seekTo(video, 10);
    expect(cueElement()).toBeNull();

    // 回合之间的间歇同样不显示
    seekTo(video, 6);
    expect(cueElement()).toBeNull();

    // 只读回放约束：整个过程不发起任何写操作
    expect(mocks.patchSegment).not.toHaveBeenCalled();
    expect(mocks.reviewSegmentBoundary).not.toHaveBeenCalled();
    expect(mocks.createAnalysisBatch).not.toHaveBeenCalled();
  });

  it("进度条区间配色覆盖全部自动回合，且不随列表筛选器变化", async () => {
    primePage();
    await renderAndLoadVideo();
    await waitFor(() => expect(screen.getByText("2 个回合")).toBeTruthy());

    expect(document.querySelector("[data-auto-rally-bands]")).toBeTruthy();
    const bandSnapshot = () =>
      [...document.querySelectorAll<HTMLElement>("[data-auto-rally-band]")]
        .map((el) => `${el.dataset.autoRallyBand}:${el.style.left}/${el.style.width}`);
    const before = bandSnapshot();
    expect(before).toHaveLength(2);
    expect(modelRows()).toHaveLength(2);

    // 切到「盘」筛选：模型列表被过滤清空，但进度条配色不受影响
    fireEvent.click(screen.getByRole("button", { name: "盘" }));
    expect(modelRows()).toHaveLength(0);
    expect(bandSnapshot()).toEqual(before);

    fireEvent.click(screen.getByRole("button", { name: "全部" }));
    expect(modelRows()).toHaveLength(2);
    expect(bandSnapshot()).toEqual(before);
  });

  it("无正式切分结果时不显示中央提示也不启用配色", async () => {
    primePage(autoRallyFixtures, {
      capture_take_id: "ct_1", status: "unavailable", run_id: null, model_package_id: null,
      model_version: null, generated_at: null, segment_count: 0, window_plan_hash: null,
      artifact_available: false,
    });
    const video = await renderAndLoadVideo();
    // 人工行渲染即代表 segments 已应用（summary 与 segments 在同一次批处理中提交）
    await waitFor(() => expect(screen.getByTitle("点击播放该片段")).toBeTruthy());

    expect(modelRows()).toHaveLength(0);
    expect(document.querySelector("[data-auto-rally-bands]")).toBeNull();
    expect(screen.getByRole("slider", { name: "视频播放进度" }).className).toContain("accent-[#22C55E]");

    seekTo(video, 2);
    expect(cueElement()).toBeNull();
  });

  it("边界复核隔离模式不启用回放提示，且复核流程不受影响", async () => {
    primePage();
    mocks.getBoundaryReview.mockResolvedValue({
      ...emptyBoundaryReview(),
      total_count: 1,
      pending_count: 1,
      segments: [{
        id: "auto-1", segment_type: "rally", ordinal: 1, label: "第1回合", start_ms: 1000, end_ms: 5000,
        effective_start_ms: 1000, effective_end_ms: 5000, edit_version: 1, edit_status: "active", status: "inferred",
        source: "algorithm", is_highlight: false, boundary_review_status: "pending",
      }],
    });
    mocks.getCaptureTake.mockResolvedValue(makeTake({
      capture_mode: "dual",
      video_ids: ["video-a", "video-b"],
      duration_ms: 12000,
    }));

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(2));
    expect(await screen.findByTestId("active-boundary-review")).toBeTruthy();

    // 两个机位都不携带回放提示数据
    expect(document.querySelectorAll("[data-auto-rally-bands]")).toHaveLength(0);

    const videos = document.querySelectorAll("video");
    seekTo(videos[0], 2);
    seekTo(videos[1], 2);
    expect(document.querySelectorAll("[data-auto-rally-cue]")).toHaveLength(0);
    expect(mocks.patchSegment).not.toHaveBeenCalled();
  });

  it("双摄复核下两个播放器各自独立持有全屏容器与控件", async () => {
    primePage();
    mocks.getCaptureTake.mockResolvedValue(makeTake({
      capture_mode: "dual",
      video_ids: ["video-a", "video-b"],
      duration_ms: 12000,
    }));

    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(2));

    // 每个播放器一个独立的全屏容器，不共享状态
    const containers = document.querySelectorAll("[data-fullscreen]");
    expect(containers).toHaveLength(2);
    expect(containers[0]).not.toBe(containers[1]);
    expect(containers[0].getAttribute("data-fullscreen")).toBe("false");
    expect(containers[1].getAttribute("data-fullscreen")).toBe("false");

    // 每个播放器各有一个全屏控件与一个静音控件（本环境不支持全屏 → 全屏控件禁用）
    const fullscreenButtons = screen.getAllByRole("button", { name: "全屏播放" }) as HTMLButtonElement[];
    expect(fullscreenButtons).toHaveLength(2);
    expect(fullscreenButtons.every((button) => button.disabled)).toBe(true);
    expect(screen.getAllByRole("button", { name: "静音视频" })).toHaveLength(2);
  });
});

describe("SegmentManagerPage 自动跳过非比赛时间", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // 三个区间：auto-1（1–2s）、人工补录（3–4s）、auto-2（5–7s）。2–5s 与 7s 之后是回合间隙。
  const skipFixtures = [
    {
      id: "auto-1", segment_type: "rally", ordinal: 1, label: "第1回合", start_ms: 1000, end_ms: 2000,
      effective_start_ms: 1000, effective_end_ms: 2000, edit_version: 1, edit_status: "active", status: "inferred",
      source: "algorithm", segmentation_run_id: "seg_run_1", is_highlight: false,
    },
    {
      id: "manual-1", segment_type: "rally", ordinal: 2, label: "人工补录", start_ms: 3000, end_ms: 4000,
      effective_start_ms: 3000, effective_end_ms: 4000, edit_version: 1, edit_status: "active", status: "closed",
      source: "manual", segmentation_run_id: null, is_highlight: false,
    },
    {
      id: "auto-2", segment_type: "rally", ordinal: 3, label: "第3回合", start_ms: 5000, end_ms: 7000,
      effective_start_ms: 5000, effective_end_ms: 7000, edit_version: 1, edit_status: "active", status: "inferred",
      source: "algorithm", segmentation_run_id: "seg_run_1", is_highlight: false,
    },
  ];

  function primePageForSkip(segments: unknown[] = skipFixtures, summary: unknown = {
    capture_take_id: "ct_1", status: "succeeded", run_id: "seg_run_1", model_package_id: "match_state_v1",
    model_version: "rgb_structured_fusion_v1", generated_at: "2026-07-17T10:01:00Z", segment_count: 2,
    window_plan_hash: "abc", artifact_available: true,
  }) {
    mocks.getVideoStreamUrl.mockImplementation((id?: string) => (id ? `/api/videos/${id}/stream` : ""));
    mocks.getCaptureTake.mockResolvedValue(makeTake({ video_ids: ["video-a"], duration_ms: 8000 }));
    mocks.listSegments.mockResolvedValue(segments);
    mocks.getFormalSegmentationSummary.mockResolvedValue(summary);
    mocks.listTimelineEvents.mockResolvedValue([]);
    mocks.getBoundaryReview.mockResolvedValue(emptyBoundaryReview());
    mocks.getMatchStateCandidates.mockResolvedValue({
      schema_version: "match-state-candidate-review.v1",
      status: "unavailable",
      reason: "candidate_artifact_missing",
      capture_take_id: "ct_1",
      revision: 0,
      candidates: [],
    });
  }

  async function renderAndReady() {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} embedded />);
    await waitFor(() => expect(mocks.getVideoStreamUrl).toHaveBeenCalledWith("video-a"));
    const video = document.querySelector("video")!;
    await waitFor(() => expect(video.getAttribute("src")).toBe("/api/videos/video-a/stream"));
    Object.defineProperty(video, "duration", { configurable: true, value: 8 });
    fireEvent.loadedMetadata(video);
    return { play, pause, video };
  }

  function seekTo(video: Element, seconds: number) {
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: seconds });
    fireEvent.timeUpdate(video);
  }

  const modelRows = () => screen.getAllByTitle("模型自动结果为只读；如需 QA 复核请使用内部 boundary-review 模式");
  const skipButton = () => screen.getByRole("button", { name: "自动跳过" }) as HTMLButtonElement;
  const playbackMode = () => document.querySelector("[data-playback-mode]")?.getAttribute("data-playback-mode");

  it("默认开启：区间自然播完后自动续播到下一个回合并跳过中间内容", async () => {
    primePageForSkip();
    const { play, video } = await renderAndReady();

    await waitFor(() => expect(modelRows()).toHaveLength(2));
    const rows = modelRows();
    fireEvent.click(rows[0]);                                    // auto-1：1000–2000
    expect(video.currentTime).toBe(1);

    seekTo(video, 2);                                            // 自然播到终点

    expect(video.currentTime).toBe(5);                           // 跳过 2–5s，续播 auto-2 起点
    expect(play).toHaveBeenCalledTimes(2);
    expect(playbackMode()).toBe("segment");
    expect(mocks.patchSegment).not.toHaveBeenCalled();
  });

  it("末段播完后停在终点，不循环回第一个区间", async () => {
    primePageForSkip();
    const { play, video } = await renderAndReady();

    await waitFor(() => expect(modelRows()).toHaveLength(2));
    fireEvent.click(modelRows()[1]);                             // auto-2：5000–7000（最后一个区间）
    seekTo(video, 7);

    expect(video.currentTime).toBe(7);
    expect(play).toHaveBeenCalledTimes(1);
    expect(playbackMode()).toBe("idle");
  });

  it("关闭开关后回到「播到终点自动暂停」的既有行为", async () => {
    primePageForSkip();
    const { play, video } = await renderAndReady();

    await waitFor(() => expect(modelRows()).toHaveLength(2));
    fireEvent.click(skipButton());
    expect(skipButton().getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(modelRows()[0]);
    seekTo(video, 2);

    expect(video.currentTime).toBe(2);
    expect(play).toHaveBeenCalledTimes(1);
    expect(playbackMode()).toBe("idle");
  });

  it("拖动进度条中断当前区间，不触发续播", async () => {
    primePageForSkip();
    const { play, video } = await renderAndReady();

    await waitFor(() => expect(modelRows()).toHaveLength(2));
    fireEvent.click(modelRows()[0]);                             // auto-1：1000–2000
    // 拖到 3s（人工补录区间内）：seekVideo 视为中断，链路停止
    fireEvent.change(screen.getByRole("slider", { name: "视频播放进度" }), { target: { value: "3000" } });
    expect(playbackMode()).toBe("idle");

    // 之后时间推进到 5s：窗口已清，不存在「播完」判定，不续播
    seekTo(video, 5);
    expect(video.currentTime).toBe(5);
    expect(play).toHaveBeenCalledTimes(1);
    expect(playbackMode()).toBe("idle");
  });

  it("人工片段播完后续播其后的第一个自动回合", async () => {
    primePageForSkip();
    const { video } = await renderAndReady();

    await waitFor(() => expect(screen.getByTitle("点击播放该片段")).toBeTruthy());
    fireEvent.click(screen.getByTitle("点击播放该片段"));          // 人工补录：3000–4000
    seekTo(video, 4);

    // 起点 ≥ 4000 的第一个 algorithm 回合是 auto-2（5–7s），证明没有按下标递推
    expect(video.currentTime).toBe(5);
    expect(playbackMode()).toBe("segment");
  });

  it("无正式切分结果时开关禁用并给出原因；复核隔离模式下不出现", async () => {
    primePageForSkip([], {
      capture_take_id: "ct_1", status: "unavailable", run_id: null, model_package_id: null,
      model_version: null, generated_at: null, segment_count: 0, window_plan_hash: null,
      artifact_available: false,
    });
    await renderAndReady();

    await waitFor(() => expect(screen.getByRole("button", { name: "自动跳过" })).toBeTruthy());
    expect(skipButton().disabled).toBe(true);
    expect(skipButton().title).toBe("无正式切分结果");
    expect(playbackMode()).toBe("idle");

    // 复核隔离模式：开关不出现，复核流程不受影响
    cleanup();
    vi.restoreAllMocks();
    primePageForSkip();
    mocks.getCaptureTake.mockResolvedValue(makeTake({ capture_mode: "dual", video_ids: ["video-a", "video-b"], duration_ms: 12000 }));
    enableBoundaryReviewMode();
    render(<SegmentManagerPage fieldSessionId="fs_1" takeId="ct_1" onNavigate={onNavigate} />);
    await waitFor(() => expect(document.querySelectorAll("video")).toHaveLength(2));
    expect(screen.queryByRole("button", { name: "自动跳过" })).toBeNull();
    expect(await screen.findByTestId("active-boundary-review")).toBeTruthy();
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
