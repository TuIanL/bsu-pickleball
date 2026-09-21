import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AUTO_RALLY_CUE_MIN_GAP_MS, AUTO_RALLY_CUE_VISIBLE_MS, SegmentVideoPlayer, type SegmentVideoPlayerHandle } from "./SegmentVideoPlayer";

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

describe("SegmentVideoPlayer 自动回合回放提示", () => {
  afterEach(() => cleanup());

  const cueState = () => document.querySelector("[data-auto-rally-cue]")?.getAttribute("data-auto-rally-cue");
  const cueText = () => document.querySelector("[data-auto-rally-cue]")?.textContent ?? null;
  const bandLayer = () => document.querySelector("[data-auto-rally-bands]");
  const bandStyle = (id: string) => {
    const el = document.querySelector<HTMLElement>(`[data-auto-rally-band="${id}"]`);
    return el ? { left: el.style.left, width: el.style.width } : null;
  };
  const playedWidth = () => document.querySelector<HTMLElement>('[data-auto-rally-played="true"]')?.style.width;

  it("未传入自动回合数据时保持原有渲染（可选启用契约）", () => {
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);

    expect(container.querySelector("[data-auto-rally-cue]")).toBeNull();
    expect(container.querySelector("[data-auto-rally-bands]")).toBeNull();
    const slider = screen.getByRole("slider", { name: "视频播放进度" });
    expect(slider.className).toContain("accent-[#22C55E]");
    expect(slider.className).not.toContain("rally-band-progress");
    // 不传区间时也不应出现叠加层与遮罩
    expect(container.querySelector('[data-auto-rally-played="true"]')).toBeNull();
  });

  it("进入新自动回合时闪现「第X回合」，到时淡出，同回合不重复", () => {
    vi.useFakeTimers();
    try {
      const cue = { id: "rally-1", ordinal: 1 };
      const { container, rerender } = render(
        <SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={cue} />,
      );

      expect(cueText()).toContain("第1回合");
      expect(cueState()).toBe("visible");

      act(() => {
        vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS);
      });
      expect(cueState()).toBe("hidden");

      // 同一回合内父组件重渲染不应重复提示
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "rally-1", ordinal: 1 }} />);
      expect(cueState()).toBe("hidden");

      // 离开自动回合后再次进入同一回合，仍应提示一次
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={null} />);
      expect(container.querySelector("[data-auto-rally-cue]")).toBeNull();
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "rally-1", ordinal: 1 }} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第1回合");

      // 切换到另一个回合同样重新提示
      act(() => {
        vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS);
      });
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "rally-2", ordinal: 2 }} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第2回合");
    } finally {
      vi.useRealTimers();
    }
  });

  it("叠加层不接收指针事件，不遮挡播放器交互", () => {
    const { container } = render(
      <SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "rally-1", ordinal: 2 }} />,
    );
    const overlay = container.querySelector<HTMLElement>("[data-auto-rally-cue]")!;
    expect(overlay.className).toContain("pointer-events-none");
    expect(overlay.getAttribute("aria-hidden")).toBe("true");
    // 播放/暂停按钮仍然可点
    expect(screen.getByTitle("播放/暂停")).toBeTruthy();
    expect(screen.getByTitle("前进一帧")).toBeTruthy();
  });

  it("按媒体时长把自动回合区间映射到进度条，并保留已播放读数", () => {
    const { container } = render(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        autoRallyBands={[
          { id: "rally-1", startMs: 1000, endMs: 3000 },
          { id: "rally-2", startMs: 6000, endMs: 8000 },
        ]}
      />,
    );
    const video = container.querySelector("video")!;

    // 时长未就绪时不启用配色
    expect(bandLayer()).toBeNull();
    expect(screen.getByRole("slider", { name: "视频播放进度" }).className).toContain("accent-[#22C55E]");

    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    fireEvent.loadedMetadata(video);

    expect(bandLayer()).toBeTruthy();
    expect(screen.getByRole("slider", { name: "视频播放进度" }).className).toContain("rally-band-progress");
    // 1000ms–3000ms / 10000ms → left 10%，宽 20%
    expect(bandStyle("rally-1")).toEqual({ left: "10%", width: "20%" });
    expect(bandStyle("rally-2")).toEqual({ left: "60%", width: "20%" });
    expect(playedWidth()).toBe("0%");

    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 4 });
    fireEvent.timeUpdate(video);
    expect(playedWidth()).toBe("40%");
  });

  it("裁剪越界区间并丢弃退化区间", () => {
    const { container } = render(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        autoRallyBands={[
          { id: "overflow", startMs: -500, endMs: 20000 },
          { id: "degenerate", startMs: 5000, endMs: 5000 },
          { id: "open", startMs: 9000, endMs: null },
        ]}
      />,
    );
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    fireEvent.loadedMetadata(video);

    expect(bandStyle("overflow")).toEqual({ left: "0%", width: "100%" });
    expect(bandStyle("degenerate")).toBeNull();
    // 终点为 null 视为延伸到媒体末尾
    expect(bandStyle("open")).toEqual({ left: "90%", width: "10%" });
  });

  it("区间为空或媒体时长缺失时不启用配色", () => {
    const { container, rerender } = render(
      <SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyBands={[]} />,
    );
    expect(bandLayer()).toBeNull();
    expect(screen.getByRole("slider", { name: "视频播放进度" }).className).toContain("accent-[#22C55E]");

    rerender(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        autoRallyBands={[{ id: "rally-1", startMs: 1000, endMs: 2000 }]}
      />,
    );
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 0 });
    fireEvent.loadedMetadata(video);

    expect(bandLayer()).toBeNull();
    const slider = screen.getByRole("slider", { name: "视频播放进度" });
    expect(slider.className).toContain("accent-[#22C55E]");
    expect(slider.className).not.toContain("rally-band-progress");
    expect((slider as HTMLInputElement).disabled).toBe(true);
  });
});

/** jsdom 不实现 Fullscreen API：fullscreenEnabled / fullscreenElement / requestFullscreen / exitFullscreen 都不存在。
 *  这里按需 stub，并且绝不改动生产代码里的 fullscreenEnabled 守卫。 */
let stubbedFullscreenElement: Element | null = null;

function stubDocumentFullscreen() {
  Object.defineProperty(document, "fullscreenEnabled", { configurable: true, value: true });
  Object.defineProperty(document, "fullscreenElement", {
    configurable: true,
    get: () => stubbedFullscreenElement,
  });
  const exit = vi.fn(() => {
    stubbedFullscreenElement = null;
    return Promise.resolve();
  });
  Object.defineProperty(document, "exitFullscreen", { configurable: true, writable: true, value: exit });
  return { exit };
}

/**
 * 只把 requestFullscreen 挂在待断言的那一个元素上。
 * 这样「全屏对象是哪一块」本身就是被断言的：如果生产代码改去调用 <video> 或根节点，
 * 那些元素上没有这个 stub，调用会抛 TypeError 并被组件的 catch 吞掉，断言随即失败。
 */
function stubElementRequestFullscreen(element: Element, options: { reject?: boolean } = {}) {
  const request = vi.fn(() => {
    if (options.reject) return Promise.reject(new Error("denied"));
    stubbedFullscreenElement = element;
    return Promise.resolve();
  });
  Object.defineProperty(element, "requestFullscreen", { configurable: true, writable: true, value: request });
  return request;
}

function unstubFullscreenApi() {
  delete (document as unknown as Record<string, unknown>).fullscreenEnabled;
  delete (document as unknown as Record<string, unknown>).fullscreenElement;
  delete (document as unknown as Record<string, unknown>).exitFullscreen;
  stubbedFullscreenElement = null;
}

function fireFullscreenChange() {
  document.dispatchEvent(new Event("fullscreenchange"));
}

describe("SegmentVideoPlayer 全屏与静音", () => {
  afterEach(() => {
    cleanup();
    unstubFullscreenApi();
  });

  const fullscreenContainer = (container: HTMLElement) =>
    container.querySelector<HTMLElement>("[data-fullscreen]")!;

  it("环境不支持全屏时控件禁用，其余能力仍可用", () => {
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);

    const fullscreenButton = screen.getByRole("button", { name: "全屏播放" }) as HTMLButtonElement;
    expect(fullscreenButton.disabled).toBe(true);

    // 播放/暂停、逐帧、进度条与静音不受影响
    expect(screen.getByTitle("播放/暂停")).toBeTruthy();
    expect(screen.getByTitle("后退一帧")).toBeTruthy();
    expect(screen.getByTitle("前进一帧")).toBeTruthy();
    expect(screen.getByRole("slider", { name: "视频播放进度" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "静音视频" })).toBeTruthy();
    expect(fullscreenContainer(container).dataset.fullscreen).toBe("false");
  });

  it("全屏控件申请全屏并随 fullscreenchange 切换状态", async () => {
    stubDocumentFullscreen();
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);
    const target = fullscreenContainer(container);
    const request = stubElementRequestFullscreen(target);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "全屏播放" }));
    });
    expect(request).toHaveBeenCalledTimes(1);
    // 全屏对象是「视频 + 进度条 + 控制条」这一整块
    expect(stubbedFullscreenElement).toBe(target);
    expect(target.contains(container.querySelector("video")!)).toBe(true);

    await act(async () => {
      fireFullscreenChange();
    });
    expect(target.dataset.fullscreen).toBe("true");
    expect(screen.getByRole("button", { name: "退出全屏" })).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "退出全屏" }));
    });
    expect(document.exitFullscreen).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireFullscreenChange();
    });
    expect(target.dataset.fullscreen).toBe("false");
    expect(screen.getByRole("button", { name: "全屏播放" })).toBeTruthy();
  });

  it("由 Esc 或浏览器行为退出全屏时控件状态自行回退", async () => {
    stubDocumentFullscreen();
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);
    const target = fullscreenContainer(container);
    stubElementRequestFullscreen(target);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "全屏播放" }));
      fireFullscreenChange();
    });
    expect(target.dataset.fullscreen).toBe("true");

    // 模拟用户按 Esc：浏览器清空 fullscreenElement 并派发事件，控件不得停留在「退出全屏」
    await act(async () => {
      stubbedFullscreenElement = null;
      fireFullscreenChange();
    });
    expect(target.dataset.fullscreen).toBe("false");
    expect(screen.getByRole("button", { name: "全屏播放" })).toBeTruthy();
  });

  it("全屏请求被拒绝时保持非全屏且不抛出未处理异常", async () => {
    stubDocumentFullscreen();
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);
    stubElementRequestFullscreen(fullscreenContainer(container), { reject: true });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "全屏播放" }));
    });
    expect(fullscreenContainer(container).dataset.fullscreen).toBe("false");
    expect(screen.getByRole("button", { name: "全屏播放" })).toBeTruthy();
  });

  it("全屏容器包住进度条与控制条，画面按原比例填充", () => {
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);
    const target = fullscreenContainer(container);

    // 进度条与控制条都在全屏容器内部
    expect(target.contains(screen.getByRole("slider", { name: "视频播放进度" }))).toBe(true);
    expect(target.contains(screen.getByTitle("播放/暂停"))).toBe(true);
    expect(target.contains(screen.getByRole("button", { name: "全屏播放" }))).toBe(true);
    expect(target.className).toContain("data-[fullscreen=true]:h-screen");
    expect(target.className).toContain("data-[fullscreen=true]:flex-col");

    // 画面按原比例居中，不裁切不拉伸
    const video = container.querySelector("video")!;
    expect(video.className).toContain("object-contain");
    expect(video.className).toContain("absolute");
    expect(video.className).toContain("inset-0");
  });

  it("静音控件翻转元素状态，并随 volumechange 回同步", async () => {
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);
    const video = container.querySelector("video")!;
    expect(video.muted).toBe(false);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "静音视频" }));
    });
    expect(video.muted).toBe(true);
    expect(screen.getByRole("button", { name: "打开声音" })).toBeTruthy();

    // 元素被外部改回有声：控件必须跟随元素，而不是反向覆盖
    await act(async () => {
      video.muted = false;
      video.dispatchEvent(new Event("volumechange"));
    });
    expect(video.muted).toBe(false);
    expect(screen.getByRole("button", { name: "静音视频" })).toBeTruthy();
  });

  it("F / M 快捷键生效且大小写不敏感", async () => {
    stubDocumentFullscreen();
    const { container } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);
    const root = container.firstElementChild as HTMLElement;
    const video = container.querySelector("video")!;
    stubElementRequestFullscreen(fullscreenContainer(container));

    fireEvent.keyDown(root, { key: "m" });
    expect(video.muted).toBe(true);
    fireEvent.keyDown(root, { key: "M" });
    expect(video.muted).toBe(false);

    await act(async () => {
      fireEvent.keyDown(root, { key: "f" });
    });
    expect(stubbedFullscreenElement).toBe(fullscreenContainer(container));

    await act(async () => {
      fireEvent.keyDown(root, { key: "F" });
    });
    expect(document.exitFullscreen).toHaveBeenCalledTimes(1);
  });

  it("焦点在可输入控件内时字母快捷键不误触发", () => {
    const { container } = render(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        trackOptions={[
          { label: "机位1", url: "/video.mp4" },
          { label: "机位2", url: "/video-2.mp4" },
        ]}
      />,
    );
    const video = container.querySelector("video")!;
    const select = screen.getByRole("combobox");

    fireEvent.keyDown(select, { key: "m" });
    expect(video.muted).toBe(false);

    // 焦点不在可输入控件内时同一按键仍然生效
    const root = container.firstElementChild as HTMLElement;
    fireEvent.keyDown(root, { key: "m" });
    expect(video.muted).toBe(true);
  });
});

describe("SegmentVideoPlayer 播放结束原因与自动跳过", () => {
  afterEach(() => {
    cleanup();
    unstubFullscreenApi();
  });

  function renderPlayer(props: Partial<Parameters<typeof SegmentVideoPlayer>[0]> = {}) {
    const handle = { current: null as SegmentVideoPlayerHandle | null };
    const onSegmentPlaybackEnd = vi.fn();
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    const view = render(
      <SegmentVideoPlayer ref={handle} videoUrl="/video.mp4" onSegmentPlaybackEnd={onSegmentPlaybackEnd} {...props} />,
    );
    const video = view.container.querySelector("video")!;
    Object.defineProperty(video, "duration", { configurable: true, value: 10 });
    fireEvent.loadedMetadata(video);
    return { ...view, video, onSegmentPlaybackEnd, handle, play, pause };
  }

  it("自然播放到区间终点报告 completed", () => {
    const { video, onSegmentPlaybackEnd, handle, play } = renderPlayer();

    act(() => {
      handle.current?.playSegment(1000, 5000);
    });
    expect(video.currentTime).toBe(1);

    // 不经过任何 seek/逐帧，仅靠 timeupdate 推进到终点 —— 模拟自然播放。
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 5 });
    fireEvent.timeUpdate(video);

    expect(onSegmentPlaybackEnd).toHaveBeenCalledTimes(1);
    expect(onSegmentPlaybackEnd).toHaveBeenCalledWith("completed");
    play.mockRestore();
  });

  it("seek 中断分段播放报告 interrupted", () => {
    const { video, onSegmentPlaybackEnd, handle } = renderPlayer();

    act(() => {
      handle.current?.playSegment(1000, 5000);
    });
    fireEvent.change(screen.getByRole("slider", { name: "视频播放进度" }), { target: { value: "3000" } });

    expect(onSegmentPlaybackEnd).toHaveBeenCalledTimes(1);
    expect(onSegmentPlaybackEnd).toHaveBeenCalledWith("interrupted");
  });

  it("逐帧越过区间终点报告 interrupted，不算自然播完", () => {
    const { video, onSegmentPlaybackEnd, handle } = renderPlayer({ fps: 10 });

    act(() => {
      handle.current?.playSegment(1000, 5000);
    });
    // 必须走播放器自己的逐帧路径（stepForward 会置中断标记），直接改 currentTime 不会置位。
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 4.96 });
    act(() => {
      handle.current?.stepForward();
    });
    expect(video.currentTime).toBeCloseTo(5.06, 5);
    fireEvent.timeUpdate(video);

    // 被钳制回区间终点，并按「被中断」上报
    expect(video.currentTime).toBe(5);
    expect(onSegmentPlaybackEnd).toHaveBeenCalledTimes(1);
    expect(onSegmentPlaybackEnd).toHaveBeenCalledWith("interrupted");
  });

  it("中断标记不泄漏到下一个播放窗口", () => {
    const { video, onSegmentPlaybackEnd, handle } = renderPlayer();

    act(() => {
      handle.current?.playSegment(1000, 5000);
    });
    // 区间播放期间拖动 → 该区间按「被中断」上报，页面由此停止续播链。
    fireEvent.change(screen.getByRole("slider", { name: "视频播放进度" }), { target: { value: "2000" } });
    expect(onSegmentPlaybackEnd).toHaveBeenCalledTimes(1);
    expect(onSegmentPlaybackEnd).toHaveBeenLastCalledWith("interrupted");

    // 之后用户重新点击一个区间：新窗口会清掉中断标记，自然播完应恢复为 completed。
    act(() => {
      handle.current?.playSegment(2000, 5000);
    });
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 5 });
    fireEvent.timeUpdate(video);
    expect(onSegmentPlaybackEnd).toHaveBeenCalledTimes(2);
    expect(onSegmentPlaybackEnd).toHaveBeenLastCalledWith("completed");
  });

  it("自动跳过控件：不传不渲染，传入可见，不可用时禁用并带原因", () => {
    const { container, rerender } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" />);
    expect(screen.queryByRole("button", { name: "自动跳过" })).toBeNull();

    rerender(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        autoSkip={{ enabled: true, onToggle: vi.fn() }}
      />,
    );
    const button = screen.getByRole("button", { name: "自动跳过" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(button.getAttribute("aria-pressed")).toBe("true");

    rerender(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        autoSkip={{ enabled: true, onToggle: vi.fn(), disabledReason: "无正式切分结果" }}
      />,
    );
    expect((screen.getByRole("button", { name: "自动跳过" }) as HTMLButtonElement).disabled).toBe(true);
    expect(container).toBeTruthy();
  });

  it("自动跳过控件点击切换并上报新取值", () => {
    const onToggle = vi.fn();
    let enabled = true;
    const { rerender } = render(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        autoSkip={{ enabled, onToggle: (next) => { enabled = next; onToggle(next); } }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "自动跳过" }));
    expect(onToggle).toHaveBeenCalledWith(false);

    rerender(
      <SegmentVideoPlayer
        ref={{ current: null }}
        videoUrl="/video.mp4"
        autoSkip={{ enabled: false, onToggle }}
      />,
    );
    expect(screen.getByRole("button", { name: "自动跳过" }).getAttribute("aria-pressed")).toBe("false");
  });
});

describe("SegmentVideoPlayer 自动续播时的中央提示合并", () => {
  afterEach(() => {
    cleanup();
    unstubFullscreenApi();
  });

  const cueState = () => document.querySelector("[data-auto-rally-cue]")?.getAttribute("data-auto-rally-cue");
  const cueText = () => document.querySelector("[data-auto-rally-cue]")?.textContent ?? null;

  it("显示窗口内的多次回合变化只就地更新文字，不重新淡入", () => {
    vi.useFakeTimers();
    try {
      const cue = { id: "r1", ordinal: 1, cause: "autoAdvance" as const };
      const { rerender } = render(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={cue} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第1回合");

      // 窗口内连续两次跨段：文字就地跳数，data 状态始终保持 visible（没有出现第二次淡入）
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r2", ordinal: 2, cause: "autoAdvance" }} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第2回合");

      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r3", ordinal: 3, cause: "autoAdvance" }} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第3回合");

      // 窗口到点淡出一次
      act(() => {
        vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS);
      });
      expect(cueState()).toBe("hidden");
    } finally {
      vi.useRealTimers();
    }
  });

  it("自动续播来源受最小静默间隔约束，用户主动来源不受约束", () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(
        <SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r1", ordinal: 1, cause: "user" }} />,
      );
      expect(cueState()).toBe("visible");
      act(() => {
        vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS);
      });
      expect(cueState()).toBe("hidden");

      // 窗口刚结束就发生自动续播变化：静默期内抑制
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r2", ordinal: 2, cause: "autoAdvance" }} />);
      expect(cueState()).toBe("hidden");

      // 静默期仍未满足
      act(() => {
        vi.advanceTimersByTime(AUTO_RALLY_CUE_MIN_GAP_MS - 100);
      });
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r3", ordinal: 3, cause: "autoAdvance" }} />);
      expect(cueState()).toBe("hidden");

      // 静默期满足后重新开窗
      act(() => {
        vi.advanceTimersByTime(200);
      });
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r4", ordinal: 4, cause: "autoAdvance" }} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第4回合");
    } finally {
      vi.useRealTimers();
    }
  });

  it("用户主动导航引起的回合变化永远提示，不受静默间隔抑制", () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(
        <SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r1", ordinal: 1, cause: "user" }} />,
      );
      expect(cueState()).toBe("visible");
      act(() => {
        vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS);
      });
      expect(cueState()).toBe("hidden");

      // 同一时刻（静默期内）用户拖动进入另一回合：必须立即提示
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r2", ordinal: 2, cause: "user" }} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第2回合");

      // 省略 cause 时按「用户主动」处理（最保守）
      act(() => {
        vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS);
      });
      rerender(<SegmentVideoPlayer ref={{ current: null }} videoUrl="/video.mp4" autoRallyCue={{ id: "r3", ordinal: 3 }} />);
      expect(cueState()).toBe("visible");
      expect(cueText()).toContain("第3回合");
    } finally {
      vi.useRealTimers();
    }
  });
});
