import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SegmentVideoPlayer, type SegmentVideoPlayerHandle } from "./SegmentVideoPlayer";

afterEach(() => cleanup());

describe("SegmentVideoPlayer 片段回放", () => {
  it("挂载时媒体元数据已就绪也会同步时长", () => {
    const readyState = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "readyState");
    const duration = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "duration");
    Object.defineProperty(HTMLMediaElement.prototype, "readyState", { configurable: true, get: () => 1 });
    Object.defineProperty(HTMLMediaElement.prototype, "duration", { configurable: true, get: () => 12.5 });
    const onDurationReady = vi.fn();

    render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" onDurationReady={onDurationReady} />);

    expect(onDurationReady).toHaveBeenCalledWith(12500);
    if (readyState) Object.defineProperty(HTMLMediaElement.prototype, "readyState", readyState);
    if (duration) Object.defineProperty(HTMLMediaElement.prototype, "duration", duration);
  });

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

  it("提供同步控制回调时，播放、逐帧和拖动都交给共享控制器", () => {
    const onPlaybackToggle = vi.fn();
    const onSeekRequest = vi.fn();
    const onFrameStepRequest = vi.fn();
    const { container } = render(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        onPlaybackToggle={onPlaybackToggle}
        onSeekRequest={onSeekRequest}
        onFrameStepRequest={onFrameStepRequest}
      />,
    );
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 2.5 });
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    fireEvent.loadedMetadata(video);

    fireEvent.click(screen.getByTitle("播放/暂停"));
    fireEvent.click(screen.getByTitle("后退一帧"));
    fireEvent.click(screen.getByTitle("前进一帧"));
    fireEvent.change(screen.getByRole("slider", { name: "视频播放进度" }), { target: { value: "4500" } });

    expect(onPlaybackToggle).toHaveBeenCalledWith(2500, false);
    expect(onFrameStepRequest).toHaveBeenNthCalledWith(1, "backward", 2500);
    expect(onFrameStepRequest).toHaveBeenNthCalledWith(2, "forward", 2500);
    expect(onSeekRequest).toHaveBeenCalledWith(4500);
  });
});
