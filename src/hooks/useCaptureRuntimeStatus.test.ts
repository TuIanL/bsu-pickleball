/**
 * useCaptureRuntimeStatus hook 测试。
 *
 * 覆盖场景（spec 2.5）：
 * - 运行状态请求失败：保留最后快照 + error + lastSuccessAt
 * - 部分指标不可用：API 返回 unavailable 字段时正确传递
 * - 过期响应：captureTakeId 切换时旧响应被丢弃
 * - 终态停止轮询：completed 后不再发请求
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, cleanup } from "@testing-library/react";
import { useCaptureRuntimeStatus, POLL_INTERVAL_MS } from "./useCaptureRuntimeStatus";
import type { CaptureTakeRuntimeStatus } from "../types/captureRuntimeStatus";

// 用 vitest 的 spy 模拟后端"运行状态"接口，便于注入成功/失败/过期响应
const mockGetRuntimeStatus = vi.fn();
vi.mock("../services/analysisClient", () => ({
  getCaptureTakeRuntimeStatus: (...args: unknown[]) => mockGetRuntimeStatus(...args),
  // 模拟 isAnalysisApiError：带 _isAnalysisApiError 标记的对象视为后端 API 错误
  isAnalysisApiError: (err: unknown) =>
    err && typeof err === "object" && "_isAnalysisApiError" in err,
}));

/**
 * 构造一份"录制中"的运行状态快照作为测试基准，
 * 允许通过 overrides 覆盖任意字段（如把 phase 改成 completed、注入 unavailable 指标等）。
 */
function makeSnapshot(overrides: Partial<CaptureTakeRuntimeStatus> = {}): CaptureTakeRuntimeStatus {
  const base: CaptureTakeRuntimeStatus = {
    captureTakeId: "ct_test",
    captureMode: "single",
    storage: { state: "ready", totalBytes: 1_000_000, usedBytes: 500_000, freeBytes: 500_000 },
    recording: {
      phase: "recording",
      startedAt: "2026-07-18T00:00:00Z",
      elapsedMs: 5000,
      targetFps: 60,
      targetWidth: 1920,
      targetHeight: 1080,
      fileSizeBytes: { state: "ready", value: 1024 },
      effectiveFps: { state: "collecting" },
      avgBitrateBps: { state: "unavailable", message: "尚无基线" },
    },
    tracks: [
      {
        trackId: "tr_1",
        slot: "cam_1",
        cameraId: "cam-1",
        phase: "recording",
        fileSizeBytes: { state: "ready", value: 1024 },
        effectiveFps: { state: "collecting" },
      },
    ],
    sync: null,
    updatedAt: "2026-07-18T00:00:05Z",
  };
  return { ...base, ...overrides };
}

describe("useCaptureRuntimeStatus", () => {
  beforeEach(() => {
    mockGetRuntimeStatus.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    cleanup(); // 卸载所有渲染的组件，清除 effect 和 interval
  });

  it("首次请求 loading，成功后返回快照", async () => {
    const snapshot = makeSnapshot();
    mockGetRuntimeStatus.mockResolvedValue(snapshot);

    const { result } = renderHook(() =>
      useCaptureRuntimeStatus({ captureTakeId: "ct_test", phase: "recording" }),
    );

    expect(result.current.state.isLoading).toBe(true);
    expect(result.current.state.snapshot).toBeNull();

    await waitFor(() => {
      expect(result.current.state.snapshot).not.toBeNull();
    });

    expect(result.current.state.snapshot).toEqual(snapshot);
    expect(result.current.state.isLoading).toBe(false);
    expect(result.current.state.error).toBeNull();
    expect(result.current.state.lastSuccessAt).not.toBeNull();
    expect(result.current.isPolling).toBe(true);
  });

  it("部分指标 unavailable 时快照正确传递", async () => {
    const snapshot = makeSnapshot({
      recording: {
        ...makeSnapshot().recording,
        effectiveFps: { state: "unavailable", message: "无诊断来源" },
        avgBitrateBps: { state: "error", message: "读取失败" },
      },
    });
    mockGetRuntimeStatus.mockResolvedValue(snapshot);

    const { result } = renderHook(() =>
      useCaptureRuntimeStatus({ captureTakeId: "ct_test", phase: "recording" }),
    );

    await waitFor(() => {
      expect(result.current.state.snapshot).not.toBeNull();
    });

    const fps = result.current.state.snapshot!.recording.effectiveFps;
    expect(fps.state).toBe("unavailable");
    expect(fps.message).toBe("无诊断来源");

    const bitrate = result.current.state.snapshot!.recording.avgBitrateBps;
    expect(bitrate.state).toBe("error");
    expect(bitrate.message).toBe("读取失败");
  });

  it("captureTakeId 切换时丢弃旧响应", async () => {
    const newSnapshot = makeSnapshot({ captureTakeId: "ct_new" });

    // 旧 take 的请求永不 resolve（模拟过期）
    mockGetRuntimeStatus.mockImplementationOnce(
      () => new Promise(() => { /* never resolves */ }),
    );
    mockGetRuntimeStatus.mockResolvedValue(newSnapshot);

    const { result, rerender } = renderHook(
      ({ takeId, phase }) => useCaptureRuntimeStatus({ captureTakeId: takeId, phase }),
      { initialProps: { takeId: "ct_old", phase: "recording" } },
    );

    // 立即切换到新 take（旧请求尚未返回）
    rerender({ takeId: "ct_new", phase: "recording" });

    await waitFor(() => {
      expect(result.current.state.snapshot?.captureTakeId).toBe("ct_new");
    });
  });

  it("请求失败时保留最后快照并设置 error", async () => {
    const firstSnapshot = makeSnapshot();
    mockGetRuntimeStatus
      .mockResolvedValueOnce(firstSnapshot)
      .mockRejectedValueOnce(new Error("网络错误"));

    const { result } = renderHook(() =>
      useCaptureRuntimeStatus({ captureTakeId: "ct_test", phase: "recording" }),
    );

    // 首次成功
    await waitFor(() => {
      expect(result.current.state.snapshot).toEqual(firstSnapshot);
    });
    const firstSuccessAt = result.current.state.lastSuccessAt;

    // 等待第二次轮询失败（需要超过一个轮询周期）
    await waitFor(
      () => {
        expect(result.current.state.error).toBe("网络错误");
      },
      { timeout: POLL_INTERVAL_MS + 2000 },
    );

    expect(result.current.state.snapshot).toEqual(firstSnapshot);
    expect(result.current.state.lastSuccessAt).toBe(firstSuccessAt);
  });

  it("终态停止轮询：completed 后不再发请求", async () => {
    const snapshot = makeSnapshot({
      recording: { ...makeSnapshot().recording, phase: "completed", durationMs: 60000 },
    });
    mockGetRuntimeStatus.mockResolvedValue(snapshot);

    const { result, rerender } = renderHook(
      ({ takeId, phase }) => useCaptureRuntimeStatus({ captureTakeId: takeId, phase }),
      { initialProps: { takeId: "ct_test", phase: "recording" } },
    );

    await waitFor(() => {
      expect(result.current.state.snapshot).not.toBeNull();
    });
    expect(result.current.isPolling).toBe(true);

    // 短暂等待让首次请求后的状态稳定
    await new Promise((r) => setTimeout(r, 50));
    const callsAfterRecording = mockGetRuntimeStatus.mock.calls.length;

    // 切换到终态
    rerender({ takeId: "ct_test", phase: "completed" });
    expect(result.current.isPolling).toBe(false);

    // 等待超过一个完整轮询周期，确认不再发新请求
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS + 400));
    expect(mockGetRuntimeStatus.mock.calls.length).toBe(callsAfterRecording);

    // 终态保留最后快照
    expect(result.current.state.snapshot).not.toBeNull();
  });

  it("captureTakeId 为 null 时重置状态且不轮询", async () => {
    mockGetRuntimeStatus.mockResolvedValue(makeSnapshot());

    const { result, rerender } = renderHook(
      ({ takeId, phase }) => useCaptureRuntimeStatus({ captureTakeId: takeId, phase }),
      { initialProps: { takeId: null as string | null, phase: "idle" as string } },
    );

    expect(result.current.state.snapshot).toBeNull();
    expect(result.current.isPolling).toBe(false);
    expect(mockGetRuntimeStatus).not.toHaveBeenCalled();

    rerender({ takeId: "ct_test", phase: "recording" });
    await waitFor(() => {
      expect(result.current.state.snapshot).not.toBeNull();
    });
  });
});
