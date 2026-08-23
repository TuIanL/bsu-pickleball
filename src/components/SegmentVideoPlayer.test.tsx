import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SegmentVideoPlayer, type SegmentVideoPlayerHandle } from "./SegmentVideoPlayer";

afterEach(() => cleanup());

describe("SegmentVideoPlayer 片段回放", () => {
  it("播放片段到终点后自动暂停并通知页面", async () => {
    const ref = { current: null as SegmentVideoPlayerHandle | null };
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    const onTimeUpdate = vi.fn();
    const onSegmentPlaybackEnd = vi.fn();
    const onDurationReady = vi.fn();

    const { container } = render(
      <SegmentVideoPlayer
        ref={ref}
        videoUrl="/video.mp4"
        onTimeUpdate={onTimeUpdate}
        onDurationReady={onDurationReady}
        onSegmentPlaybackEnd={onSegmentPlaybackEnd}
      />,
    );
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    fireEvent.loadedMetadata(video);
    expect(onDurationReady).toHaveBeenCalledWith(10000);

    await act(async () => {
      ref.current?.playSegment(1000, 3000);
    });
    expect(play).toHaveBeenCalledTimes(1);

    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 3 });
    fireEvent.timeUpdate(video);
    expect(onTimeUpdate).toHaveBeenLastCalledWith(3000);
    expect(pause).toHaveBeenCalledTimes(1);
    expect(onSegmentPlaybackEnd).toHaveBeenCalledTimes(1);

    play.mockRestore();
    pause.mockRestore();
  });

  it("seek 会清除片段播放范围，但不会隐式发起新的播放", async () => {
    const ref = { current: null as SegmentVideoPlayerHandle | null };
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const { container } = render(<SegmentVideoPlayer ref={ref} videoUrl="/video.mp4" />);
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    fireEvent.loadedMetadata(video);

    await act(async () => {
      ref.current?.playSegment(1000, 3000);
      ref.current?.seekToTakeTime(7000);
    });
    expect(video.currentTime).toBe(7);
    expect(play).toHaveBeenCalledTimes(1);
    play.mockRestore();
  });

  it("底部进度条拖拽会 seek 并同步时间回调", () => {
    const onTimeUpdate = vi.fn();
    const { container } = render(
      <SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" onTimeUpdate={onTimeUpdate} />,
    );
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 0 });
    fireEvent.loadedMetadata(video);

    fireEvent.change(screen.getByRole("slider", { name: "视频播放进度" }), { target: { value: "4500" } });

    expect(video.currentTime).toBe(4.5);
    expect(onTimeUpdate).toHaveBeenLastCalledWith(4500);
  });
});
