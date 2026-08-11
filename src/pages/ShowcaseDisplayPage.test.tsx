import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCameraPreviewUrl, getShowcaseRuntimeStatus } from "../services/analysisClient";
import { ShowcaseDisplayPage } from "./ShowcaseDisplayPage";

vi.mock("../services/analysisClient", () => ({
  getCameraPreviewUrl: vi.fn((cameraId?: string) => cameraId ? `/api/cameras/${cameraId}/preview` : undefined),
  getShowcaseRuntimeStatus: vi.fn(),
  getShowcaseStreamUrl: vi.fn((runtimeId: string, slot: string) => `/api/showcase-runtimes/${runtimeId}/streams/${slot}`),
}));

const mockedGetStatus = vi.mocked(getShowcaseRuntimeStatus);

afterEach(() => {
  cleanup();
  mockedGetStatus.mockReset();
});

const status = {
  runtime_id: "showcase-1",
  capture_take_id: "take-1",
  status: "running",
  recording_status: "recording",
  target_inference_fps: 8,
  processing_width: 960,
  jpeg_quality: 78,
  ball_enabled: false,
  degradation_reasons: [],
  started_at: "2026-01-01T00:00:00Z",
  cameras: {
    cam_1: { slot: "cam_1", camera_id: "camera-a", connection_status: "connected", actual_inference_fps: 7.5, actual_output_fps: 7.5, track_count: 2, person_status: "available", ball_status: "disabled", frame_sequence: 3 },
    cam_2: { slot: "cam_2", camera_id: "camera-b", connection_status: "connected", actual_inference_fps: 7.4, actual_output_fps: 7.4, track_count: 1, person_status: "available", ball_status: "disabled", frame_sequence: 3 },
  },
};

describe("ShowcaseDisplayPage", () => {
  it("opens both task-scoped streams and falls back to ordinary preview per slot", async () => {
    mockedGetStatus.mockResolvedValue(status);
    render(<ShowcaseDisplayPage runtimeId="showcase-1" onNavigate={vi.fn()} />);

    const cam1 = await screen.findByAltText("cam_1 实时展示");
    const cam2 = await screen.findByAltText("cam_2 实时展示");
    expect(cam1.getAttribute("src")).toBe("/api/showcase-runtimes/showcase-1/streams/cam_1");
    expect(cam2.getAttribute("src")).toBe("/api/showcase-runtimes/showcase-1/streams/cam_2");

    fireEvent.error(cam1);
    await waitFor(() => expect(cam1.getAttribute("src")).toBe("/api/cameras/camera-a/preview"));
    expect(getCameraPreviewUrl).toHaveBeenCalledWith("camera-a");
  });

  it("shows an explanatory error when the runtime status is unavailable", async () => {
    mockedGetStatus.mockRejectedValue(new Error("展示旁路已停止"));
    render(<ShowcaseDisplayPage runtimeId="missing" onNavigate={vi.fn()} />);

    expect(await screen.findByText(/展示流不可用：展示旁路已停止/)).toBeTruthy();
  });
});
