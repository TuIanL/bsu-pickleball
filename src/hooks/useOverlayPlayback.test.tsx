import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useOverlayPlayback } from "./useOverlayPlayback";
import { requestJson } from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({ requestJson: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const artifact = {
  reference_view_id: "cam_1", frames: [], views: { cam_1: { frames: [] }, cam_2: { frames: [] } },
  playback: { schema_version: "overlay-playback.v1" as const, url: "/overlay", generation: "one",
    chunk_seconds: 20, chunks: { cam_1: [0,1,2,3,4,5], cam_2: [0,1,2,3,4,5] } },
};

it("loads only the selected camera and window, reuses prefetch, and never shows the previous camera", async () => {
  vi.mocked(requestJson).mockImplementation(async (url) => ({ frames: [url] }));
  const { result, rerender } = renderHook(({ view, seconds }) => useOverlayPlayback(artifact, view, seconds),
    { initialProps: { view: "cam_1", seconds: 5 } });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.artifact?.frames[0]).toContain("view_id=cam_1");
  expect(vi.mocked(requestJson).mock.calls).toHaveLength(2);
  rerender({ view: "cam_1", seconds: 21 });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.artifact?.frames[0]).toContain("chunk=1");
  expect(vi.mocked(requestJson).mock.calls).toHaveLength(3);
  rerender({ view: "cam_2", seconds: 21 });
  expect(result.current.artifact?.frames).toEqual([]);
  expect(result.current.artifact?.views?.cam_2.frames).toEqual([]);
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.artifact?.frames).toEqual([]);
  expect(result.current.artifact?.views?.cam_2.frames[0]).toContain("view_id=cam_2");
});

it("does not publish late results after a seek and reports the current window failure", async () => {
  let finish: (value: unknown) => void = () => undefined;
  vi.mocked(requestJson).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  const { result, rerender } = renderHook(({ seconds }) => useOverlayPlayback(artifact, "cam_1", seconds),
    { initialProps: { seconds: 5 } });
  vi.mocked(requestJson).mockRejectedValue(new Error("window unavailable"));
  rerender({ seconds: 45 });
  await waitFor(() => expect(result.current.error).toBe("window unavailable"));
  await act(async () => { finish({ frames: ["stale"] }); });
  expect(result.current.artifact?.frames).toEqual([]);
  expect(result.current.error).toBe("window unavailable");
});

it("passes through older in-memory artifacts without requesting shards", () => {
  const old = { frames: [{ timestamp_seconds: 30 }] };
  const { result } = renderHook(() => useOverlayPlayback(old, undefined, 30));
  expect(result.current.artifact).toBe(old);
  expect(requestJson).not.toHaveBeenCalled();
});
