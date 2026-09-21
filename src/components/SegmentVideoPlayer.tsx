import { useCallback, useEffect, useImperativeHandle, useRef, forwardRef, useState } from "react";
import { Play, Pause, SkipForward, SkipBack, Maximize2, Minimize2, Volume2, VolumeX } from "lucide-react";

export interface SegmentVideoPlayerHandle {
  seekToTakeTime(timestampMs: number): void;
  syncToTakeTime(timestampMs: number, toleranceMs?: number): void;
  getCurrentTimeMs(): number;
  play(): void;
  pause(): void;
  playSegment(startMs: number, endMs: number): void;
  stepForward(): void;
  stepBackward(): void;
}

/** 播放头当前所属的自动回合，用于中央瞬时提示。 */
export interface AutoRallyCue {
  id: string;
  ordinal: number;
  /**
   * 回合变化的来源。省略时按「用户主动」处理（最保守：永远提示、不受节流）。
   * `autoAdvance` 表示变化由自动续播引起，受最小静默间隔约束。
   */
  cause?: "user" | "autoAdvance";
}

/** 一次性片段播放窗口结束的原因。 */
export type SegmentPlaybackEndReason = "completed" | "interrupted";

/** 「自动跳过非比赛时间」开关的控件数据。三者齐备才渲染；不传则控件不出现。 */
export interface AutoSkipControl {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  /** 不可用原因；非空时控件禁用。 */
  disabledReason?: string | null;
}

/** 一个自动回合区间，用于播放进度条的回合/非回合配色。`endMs` 为 null 表示延伸到媒体末尾。 */
export interface AutoRallyBand {
  id: string;
  startMs: number;
  endMs: number | null;
}

/** 中央回合提示的停留时长（毫秒）。 */
export const AUTO_RALLY_CUE_VISIBLE_MS = 2000;
/** 两次独立提示淡入之间的最小静默间隔（毫秒）。只约束自动续播来源，用户主动导航不受节流。 */
export const AUTO_RALLY_CUE_MIN_GAP_MS = 1000;

/** 进度条区间配色：自动回合 / 非回合 / 已播放遮罩。回合色与时间线「分」轨保持一致。 */
const RALLY_BAND_COLOR = "#22C55E";
const NON_RALLY_BAND_COLOR = "#334155";
const PLAYED_MASK_COLOR = "rgba(255,255,255,0.28)";

/** 字母快捷键（F/M）是否应被忽略：焦点位于可输入控件内时不响应，避免与控件自身的键盘行为冲突。 */
function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target.isContentEditable === true;
}

interface SegmentVideoPlayerProps {
  videoUrl: string;
  fps?: number;
  segmentStartMs?: number;
  segmentEndMs?: number;
  trackLabel?: string;
  trackOptions?: { label: string; url: string }[];
  onTrackChange?: (index: number) => void;
  onTimeUpdate?: (takeTimeMs: number) => void;
  onDurationReady?: (durationMs: number) => void;
  onSegmentPlaybackEnd?: (reason: SegmentPlaybackEndReason) => void;
  onPlaybackToggle?: (currentTimeMs: number, playing: boolean) => void;
  onSeekRequest?: (takeTimeMs: number) => void;
  onFrameStepRequest?: (direction: "forward" | "backward", currentTimeMs: number, stepMs?: number) => void;
  syncQuality?: string;
  preload?: "none" | "metadata" | "auto";
  /** 播放头当前所属的自动回合；未传入或为 null 时不渲染中央提示。 */
  autoRallyCue?: AutoRallyCue | null;
  /** 自动回合区间；未传入或为空数组时不改变进度条现有外观。 */
  autoRallyBands?: AutoRallyBand[];
  /** 「自动跳过非比赛时间」开关；不传则控件不出现，行为与引入前一致。 */
  autoSkip?: AutoSkipControl;
}

export const SegmentVideoPlayer = forwardRef<SegmentVideoPlayerHandle, SegmentVideoPlayerProps>(
  function SegmentVideoPlayer(
    {
      videoUrl,
      fps = 30,
      trackLabel,
      trackOptions,
      onTrackChange,
      onTimeUpdate,
      onDurationReady,
      onSegmentPlaybackEnd,
      onPlaybackToggle,
      onSeekRequest,
      onFrameStepRequest,
      syncQuality,
      preload = "auto",
      autoRallyCue = null,
      autoRallyBands,
      autoSkip,
    },
    ref,
  ) {
    const videoRef = useRef<HTMLVideoElement>(null);
    // 全屏对象是「视频画面 + 进度条 + 控制条」这一整块，作用在根节点与视频之间的内层容器上：
    // 根节点带圆角/边框/底色，整屏显示会在屏幕四周画出一圈边框，覆盖它的反向变体会把本特性
    // 与根的当前样式耦死；而只全屏 <video> 会走浏览器原生视频全屏，丢掉应用自己的控制面。
    const containerRef = useRef<HTMLDivElement>(null);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [isMuted, setIsMuted] = useState(false);
    const [playing, setPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const segmentLoopRef = useRef<{ start: number; end: number } | null>(null);
    // 一次性片段播放窗口被 seek/逐帧打断的标记。只有未被置位时到达终点才算「自然播完」，
    // 否则报「被中断」——这是「弱约束」（拖动仍可自由定位、不弹回）能成立的唯一方式。
    const interruptionRef = useRef(false);
    const [cueVisible, setCueVisible] = useState(false);
    // 中央提示就地更新时显示的序号：可能与最新 prop 不同（窗口未开启且被静默间隔抑制时）。
    const [cueOrdinal, setCueOrdinal] = useState<number | null>(null);
    const cueTimerRef = useRef<number | null>(null);
    // 提示显示窗口的状态：是否开启、窗口结束时刻（供最小静默间隔判定）、以及已提示过的回合。
    const cueWindowOpenRef = useRef(false);
    const cueWindowEndRef = useRef<number | null>(null);
    const announcedCueIdRef = useRef<string | null>(null);

    // 与 VideoAnalysisCard 一致的既有约定：能力探测 + fullscreenchange 事件同步。
    // 不维护「意图是否全屏」的独立 state —— Esc、浏览器控件、其它元素抢先全屏都会让意图与事实分叉。
    const fullscreenSupported = typeof document !== "undefined" && Boolean(document.fullscreenEnabled);
    useEffect(() => {
      if (typeof document === "undefined") return;
      const handleFullscreenChange = () => {
        setIsFullscreen(document.fullscreenElement === containerRef.current);
      };
      document.addEventListener("fullscreenchange", handleFullscreenChange);
      return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
    }, []);

    const toggleFullscreen = useCallback(async () => {
      const container = containerRef.current;
      if (!container || !fullscreenSupported) return;
      try {
        if (document.fullscreenElement === container) await document.exitFullscreen();
        else await container.requestFullscreen();
      } catch {
        // 浏览器拒绝时不改状态：真实的成败由 fullscreenchange 事件给出。
      }
    }, [fullscreenSupported]);

    // 静音以 <video>.muted 为唯一真源，state 只做镜像，避免「图标已静音但元素仍在出声」的分叉。
    // 依赖留空：<video> 元素在切换机位时不会被重建，muted 由浏览器保留，无需重新绑定。
    useEffect(() => {
      const video = videoRef.current;
      if (!video) return;
      const handleVolumeChange = () => setIsMuted(video.muted);
      video.addEventListener("volumechange", handleVolumeChange);
      setIsMuted(video.muted);
      return () => video.removeEventListener("volumechange", handleVolumeChange);
    }, []);

    const toggleMuted = useCallback(() => {
      const video = videoRef.current;
      if (!video) return;
      video.muted = !video.muted;
      setIsMuted(video.muted);
    }, []);

    // 中央回合提示状态机：
    // ① 显示窗口开启期间的回合变化 → 只就地更新序号，不重新淡入、不延长窗口（窗口到点仍淡出）；
    // ② 窗口未开启时——用户主动来源立即开新窗（保证既有「暂停与定位同样触发」不被节流）；
    //    自动续播来源须距上次窗口结束 ≥ 最小静默间隔才开窗，否则抑制（避免「刚淡出又淡入」的双闪）。
    // 依赖用 cue 对象本身而非其 id：窗口开启期间需要读到最新 ordinal 就地更新，
    // 且回合 id 不变时该 effect 会提前返回，不会造成状态抖动。
    useEffect(() => {
      if (!autoRallyCue) {
        if (cueTimerRef.current !== null) {
          window.clearTimeout(cueTimerRef.current);
          cueTimerRef.current = null;
        }
        cueWindowOpenRef.current = false;
        cueWindowEndRef.current = Date.now();
        announcedCueIdRef.current = null;
        setCueOrdinal(null);
        setCueVisible(false);
        return;
      }
      if (announcedCueIdRef.current === autoRallyCue.id) return;
      announcedCueIdRef.current = autoRallyCue.id;

      if (cueWindowOpenRef.current) {
        // 窗口内就地更新：**保留原定时器**（不延长窗口），只换文字。
        // 这里若清掉定时器，窗口将永不淡出 —— 「合并为一块」就变成了「一直挂着」。
        setCueOrdinal(autoRallyCue.ordinal);
        return;
      }
      // 开新窗前先清掉任何遗留定时器，避免旧定时器把新窗口提前关掉。
      if (cueTimerRef.current !== null) {
        window.clearTimeout(cueTimerRef.current);
        cueTimerRef.current = null;
      }
      const cause = autoRallyCue.cause ?? "user";
      if (cause === "autoAdvance" && cueWindowEndRef.current !== null) {
        const sinceLastWindowEnd = Date.now() - cueWindowEndRef.current;
        if (sinceLastWindowEnd < AUTO_RALLY_CUE_MIN_GAP_MS) return;
      }
      cueWindowOpenRef.current = true;
      setCueOrdinal(autoRallyCue.ordinal);
      setCueVisible(true);
      cueTimerRef.current = window.setTimeout(() => {
        cueTimerRef.current = null;
        cueWindowOpenRef.current = false;
        cueWindowEndRef.current = Date.now();
        setCueVisible(false);
      }, AUTO_RALLY_CUE_VISIBLE_MS);
    }, [autoRallyCue]);

    useEffect(() => () => {
      if (cueTimerRef.current !== null) window.clearTimeout(cueTimerRef.current);
    }, []);

    const seekVideo = useCallback((ms: number) => {
      const video = videoRef.current;
      if (!video) return;
      // 任何 seek 都把当前窗口标记为被中断：即使之后自然播到终点，也不算「自然播完」。
      interruptionRef.current = true;
      const wasPlayingSegment = segmentLoopRef.current !== null;
      segmentLoopRef.current = null;
      const maxSeconds = duration > 0 ? duration / 1000 : Number.POSITIVE_INFINITY;
      const nextMs = Math.max(0, Math.min(ms, maxSeconds * 1000));
      video.currentTime = nextMs / 1000;
      setCurrentTime(nextMs);
      onTimeUpdate?.(nextMs);
      if (wasPlayingSegment) onSegmentPlaybackEnd?.("interrupted");
    }, [duration, onSegmentPlaybackEnd, onTimeUpdate]);

    useEffect(() => {
      const video = videoRef.current;
      if (!video) return;

      const onLoaded = () => {
        setDuration(video.duration * 1000);
        onDurationReady?.(video.duration * 1000);
      };
      const finishSegmentPlayback = () => {
        const loop = segmentLoopRef.current;
        if (!loop) return false;
        const endSeconds = loop.end;
        if (video.currentTime < endSeconds - 0.03) return false;

        // Keep the final frame inside the requested range before pausing.
        if (video.currentTime > endSeconds) video.currentTime = endSeconds;
        segmentLoopRef.current = null;
        video.pause();
        setPlaying(false);
        // 到达终点的原因由 interruptionRef 决定：seek/逐帧期间被置位则视为被中断，
        // 否则才是自然播完。页面据此决定是否自动续播到下一个比赛时间区间。
        const reason: SegmentPlaybackEndReason = interruptionRef.current ? "interrupted" : "completed";
        interruptionRef.current = false;
        onSegmentPlaybackEnd?.(reason);
        return true;
      };

      const onTime = () => {
        const ms = video.currentTime * 1000;
        setCurrentTime(ms);
        onTimeUpdate?.(ms);
        finishSegmentPlayback();
      };
      const onPlay = () => {
        // 重新开始播放意味着接下来是一段新的自然播放，清除此前遗留的中断标记。
        interruptionRef.current = false;
        setPlaying(true);
      };
      const onPause = () => setPlaying(false);
      const onEnded = () => {
        if (!finishSegmentPlayback()) {
          // 媒体先于片段终点结束：没有可续播的后续区间，按自然播完处理。
          interruptionRef.current = false;
          onSegmentPlaybackEnd?.("completed");
        }
        setPlaying(false);
      };

      video.addEventListener("loadedmetadata", onLoaded);
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("play", onPlay);
      video.addEventListener("pause", onPause);
      video.addEventListener("ended", onEnded);
      if (video.readyState >= HTMLMediaElement.HAVE_METADATA) onLoaded();

      return () => {
        video.removeEventListener("loadedmetadata", onLoaded);
        video.removeEventListener("timeupdate", onTime);
        video.removeEventListener("play", onPlay);
        video.removeEventListener("pause", onPause);
        video.removeEventListener("ended", onEnded);
      };
    }, [videoUrl, onTimeUpdate, onDurationReady, onSegmentPlaybackEnd]);

    useImperativeHandle(ref, () => ({
      seekToTakeTime(ms: number) {
        seekVideo(ms);
      },
      syncToTakeTime(ms: number, toleranceMs = 12) {
        const video = videoRef.current;
        if (!video) return;
        const maxMs = duration > 0 ? duration : Number.POSITIVE_INFINITY;
        const nextMs = Math.max(0, Math.min(ms, maxMs));
        if (Math.abs(video.currentTime * 1000 - nextMs) <= toleranceMs) return;
        // 与 seekVideo 同理：对齐式跳转不代表自然播完。
        if (segmentLoopRef.current !== null) interruptionRef.current = true;
        video.currentTime = nextMs / 1000;
        setCurrentTime(nextMs);
      },
      getCurrentTimeMs() {
        return (videoRef.current?.currentTime ?? currentTime / 1000) * 1000;
      },
      play() {
        videoRef.current?.play();
      },
      pause() {
        videoRef.current?.pause();
      },
      playSegment(startMs: number, endMs: number) {
        const video = videoRef.current;
        if (!video) return;
        const maxSeconds = duration > 0 ? duration / 1000 : Number.POSITIVE_INFINITY;
        const startSeconds = Math.min(maxSeconds, Math.max(0, startMs / 1000));
        const endSeconds = Math.min(maxSeconds, Math.max(startSeconds, endMs / 1000));
        segmentLoopRef.current = { start: startSeconds, end: endSeconds };
        // 新窗口即一段新的自然播放，清掉此前遗留的中断标记。
        interruptionRef.current = false;
        video.currentTime = startSeconds;
        void video.play();
      },
      stepForward() {
        const video = videoRef.current;
        if (video) {
          interruptionRef.current = true;
          video.currentTime += 1 / fps;
        }
      },
      stepBackward() {
        const video = videoRef.current;
        if (video) {
          interruptionRef.current = true;
          video.currentTime -= 1 / fps;
        }
      },
    }), [currentTime, duration, fps, seekVideo]);

    const getLiveCurrentTimeMs = () => (videoRef.current?.currentTime ?? currentTime / 1000) * 1000;

    const handleFrameStep = (direction: "forward" | "backward") => {
      const liveTimeMs = getLiveCurrentTimeMs();
      // 逐帧推进不代表自然播完，先置中断标记再改时间。
      interruptionRef.current = true;
      if (onFrameStepRequest) {
        onFrameStepRequest(direction, liveTimeMs);
        return;
      }
      const video = videoRef.current;
      if (video) video.currentTime += direction === "forward" ? 1 / fps : -(1 / fps);
    };

    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        interruptionRef.current = true;
        if (onFrameStepRequest) {
          onFrameStepRequest("backward", getLiveCurrentTimeMs(), e.shiftKey ? 1000 : (1000 / fps));
        } else {
          const video = videoRef.current;
          if (video) video.currentTime -= e.shiftKey ? 1 : (1 / fps);
        }
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        interruptionRef.current = true;
        if (onFrameStepRequest) {
          onFrameStepRequest("forward", getLiveCurrentTimeMs(), e.shiftKey ? 1000 : (1000 / fps));
        } else {
          const video = videoRef.current;
          if (video) video.currentTime += e.shiftKey ? 1 : (1 / fps);
        }
      } else if (e.key === " ") {
        e.preventDefault();
        const video = videoRef.current;
        if (video) {
          if (onPlaybackToggle) {
            onPlaybackToggle(getLiveCurrentTimeMs(), !video.paused);
          } else if (video.paused) void video.play();
          else video.pause();
        }
      } else if (!isTextEntryTarget(e.target)) {
        // 字母快捷键只在焦点不位于可输入控件内时生效：控制条里的机位选择下拉聚焦时，
        // 按 M 会与浏览器的选项首字母跳转打架。守卫只作用于这两个新增字母键，
        // 既有的方向键与空格语义（含 preventDefault）保持不变。
        const key = e.key.toLowerCase();
        if (key === "f") {
          e.preventDefault();
          void toggleFullscreen();
        } else if (key === "m") {
          e.preventDefault();
          toggleMuted();
        }
      }
    }, [fps, onFrameStepRequest, onPlaybackToggle, toggleFullscreen, toggleMuted]);

    const formatTime = (ms: number) => {
      const s = Math.floor(ms / 1000);
      const m = Math.floor(s / 60);
      const sec = s % 60;
      return `${m}:${String(sec).padStart(2, "0")}`;
    };

    const handleProgressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const nextMs = Number(e.target.value);
      if (onSeekRequest) onSeekRequest(nextMs);
      else seekVideo(nextMs);
    };

    // 进度条区间配色只在「已知媒体时长 + 存在自动回合区间」时启用；
    // 其余情况（含 jsdom 下 duration 为 NaN）保持原生 accent 外观，避免 NaN 宽度与对「无数据」的误读。
    const bandLayerEnabled = duration > 0 && (autoRallyBands?.length ?? 0) > 0;
    const bandScale = (ms: number) => `${duration > 0 ? (Math.max(0, Math.min(ms, duration)) / duration) * 100 : 0}%`;

    return (
      <div className="rounded-2xl border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-video,#24302b)] overflow-hidden" onKeyDown={handleKeyDown} tabIndex={0}>
        {/* 全屏容器：包住视频区、进度条与控制条三块，使全屏后仍可拖进度、逐帧、切机位、切静音。
            全屏时切为纵向 flex，视频区 flex-1 占据剩余高度，另两行固定在底部。 */}
        <div
          ref={containerRef}
          data-fullscreen={isFullscreen}
          className="data-[fullscreen=true]:flex data-[fullscreen=true]:h-screen data-[fullscreen=true]:w-screen data-[fullscreen=true]:flex-col"
        >
        <div className="relative aspect-video data-[fullscreen=true]:aspect-auto data-[fullscreen=true]:min-h-0 data-[fullscreen=true]:flex-1">
          <video
            ref={videoRef}
            src={videoUrl}
            className="absolute inset-0 h-full w-full bg-black object-contain"
            controls={false}
            preload={preload}
          />
          {autoRallyCue && (
            // 叠加层只做视觉提示：不接收指针事件，因此不遮挡播放器既有的点击与快捷键行为；
            // 同时不进无障碍树（2 秒即消失，内容与右侧片段列表高亮重复，进树会导致反复播报）。
            <div
              className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden"
              aria-hidden="true"
              data-auto-rally-cue={cueVisible ? "visible" : "hidden"}
            >
              <span className={`auto-rally-cue${cueVisible ? " auto-rally-cue--visible" : ""}`}>
                第{cueOrdinal ?? autoRallyCue.ordinal}回合
              </span>
            </div>
          )}
        </div>
        <div className="bg-[#1a1a2e] px-3 pt-2">
          <div className="relative">
            {bandLayerEnabled && (
              // 色带层与原生 range 同盒模型（absolute inset-0，flow 内只有 range 一个子元素），
              // 因此不需要额外同步尺寸；range 的 min/max 与这里的归一化基准同为 duration。
              <div
                className="pointer-events-none absolute inset-0 overflow-hidden rounded-full"
                aria-hidden="true"
                data-auto-rally-bands="true"
              >
                <div className="absolute inset-0" style={{ backgroundColor: NON_RALLY_BAND_COLOR }} />
                {autoRallyBands!.map((band) => {
                  const start = Math.max(0, Math.min(band.startMs, duration));
                  const end = Math.max(0, Math.min(band.endMs ?? duration, duration));
                  // 裁剪后长度为零的退化区间直接丢弃，不影响其余区间渲染。
                  if (end <= start) return null;
                  return (
                    <div
                      key={band.id}
                      data-auto-rally-band={band.id}
                      className="absolute inset-y-0"
                      style={{
                        left: bandScale(start),
                        width: bandScale(end - start),
                        backgroundColor: RALLY_BAND_COLOR,
                      }}
                    />
                  );
                })}
                {/* 已播放读数：接管原生轨道后用它补回「已播放 / 未播放」的区分。 */}
                <div
                  data-auto-rally-played="true"
                  className="absolute inset-y-0 left-0"
                  style={{ width: bandScale(Math.min(currentTime, duration)), backgroundColor: PLAYED_MASK_COLOR }}
                />
              </div>
            )}
            <input
              type="range"
              min={0}
              max={Math.max(duration, 1)}
              step={1}
              value={Math.min(currentTime, duration || 1)}
              disabled={duration <= 0}
              onChange={handleProgressChange}
              aria-label="视频播放进度"
              title="拖拽调整视频播放位置"
              className={`relative block h-1.5 w-full cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 ${bandLayerEnabled ? "rally-band-progress" : "accent-[#22C55E]"}`}
            />
          </div>
        </div>
        <div className="flex items-center justify-between px-3 py-2 bg-[#1a1a2e] text-white text-xs">
          <div className="flex items-center gap-2">
            <button
              className="p-1 hover:bg-white/10 rounded"
              onClick={() => handleFrameStep("backward")}
              title="后退一帧"
              type="button"
            >
              <SkipBack size={14} />
            </button>
            <button
              className="p-1 hover:bg-white/10 rounded"
              onClick={() => {
                const video = videoRef.current;
                if (!video) return;
                if (onPlaybackToggle) onPlaybackToggle(getLiveCurrentTimeMs(), !video.paused);
                else if (video.paused) void video.play();
                else video.pause();
              }}
              title="播放/暂停"
              type="button"
            >
              {playing ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <button
              className="p-1 hover:bg-white/10 rounded"
              onClick={() => handleFrameStep("forward")}
              title="前进一帧"
              type="button"
            >
              <SkipForward size={14} />
            </button>
            <button
              className="p-1 hover:bg-white/10 rounded"
              onClick={toggleMuted}
              title={isMuted ? "打开声音（M）" : "静音视频（M）"}
              aria-label={isMuted ? "打开声音" : "静音视频"}
              type="button"
            >
              {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>
            <span className="tabular-nums ml-2">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {autoSkip && (
              <button
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold transition disabled:cursor-not-allowed disabled:opacity-40 ${autoSkip.enabled ? "bg-[#22C55E]/25 text-[#8ef0b4]" : "bg-white/10 text-white/70"} hover:bg-white/20`}
                onClick={() => autoSkip.onToggle(!autoSkip.enabled)}
                aria-pressed={autoSkip.enabled}
                title={autoSkip.disabledReason ?? (autoSkip.enabled ? "自动跳过非比赛时间：已开启" : "自动跳过非比赛时间：已关闭")}
                disabled={Boolean(autoSkip.disabledReason)}
                type="button"
              >
                自动跳过
              </button>
            )}
            {syncQuality === "degraded" && (
              <span className="text-yellow-400 text-[10px]" title="同步质量可能不佳">⚠ 同步降级</span>
            )}
            {trackOptions && trackOptions.length > 0 && (
              <select
                className="bg-white/10 border border-white/20 rounded px-2 py-0.5 text-xs"
                onChange={(e) => onTrackChange?.(Number(e.target.value))}
                value={trackOptions.findIndex(t => t.url === videoUrl)}
              >
                {trackOptions.map((t, i) => (
                  <option key={i} value={i}>{t.label}</option>
                ))}
              </select>
            )}
            {trackLabel && !trackOptions && (
              <span className="text-white/60">{trackLabel}</span>
            )}
            <button
              className="p-1 hover:bg-white/10 rounded disabled:cursor-not-allowed disabled:opacity-40"
              onClick={() => void toggleFullscreen()}
              title={isFullscreen ? "退出全屏（F）" : "全屏播放（F）"}
              aria-label={isFullscreen ? "退出全屏" : "全屏播放"}
              disabled={!fullscreenSupported}
              type="button"
            >
              {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          </div>
        </div>
        </div>
      </div>
    );
  },
);
