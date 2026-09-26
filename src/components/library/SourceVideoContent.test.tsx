import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SourceVideoContent } from "./SourceVideoContent";

vi.mock("../../services/analysisClient", () => ({ getVideoStreamUrl: () => "/api/videos/video-1/stream" }));

describe("SourceVideoContent", () => {
  it("seeks to the millisecond workspace timestamp after metadata loads", () => {
    const { container } = render(<SourceVideoContent videoId="video-1" seekToMs={3800} />);
    const video = container.querySelector("video")!;
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(3.8);
  });
});
