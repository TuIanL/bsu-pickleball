import { useCallback, useEffect, useImperativeHandle, useRef, forwardRef, useState } from "react";
import { Play, Pause, SkipForward, SkipBack } from "lucide-react";

export interface SegmentVideoPlayerHandle {
  seekToTakeTime(timestampMs: number): void;
  play(): void;
  pause(): void;
  playSegment(startMs: number, endMs: number): void;
  stepForward(): void;
  stepBackward(): void;
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
  onSegmentPlaybackEnd?: () => void;
  syncQuality?: string;
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
      syncQuality,
    },
    ref,
  ) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [playing, setPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const segmentLoopRef = useRef<{ start: number; end: number } | null>(null);

    const seekVideo = useCallback((ms: number) => {
      const video = videoRef.current;
      if (!video) return;
      const wasPlayingSegment = segmentLoopRef.current !== null;
      segmentLoopRef.current = null;
      const maxSeconds = duration > 0 ? duration / 1000 : Number.POSITIVE_INFINITY;
      const nextMs = Math.max(0, Math.min(ms, maxSeconds * 1000));
      video.currentTime = nextMs / 1000;
      setCurrentTime(nextMs);
      onTimeUpdate?.(nextMs);
      if (wasPlayingSegment) onSegmentPlaybackEnd?.();
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
        onSegmentPlaybackEnd?.();
        return true;
      };

      const onTime = () => {
        const ms = video.currentTime * 1000;
        setCurrentTime(ms);
        onTimeUpdate?.(ms);
        finishSegmentPlayback();
      };
      const onPlay = () => setPlaying(true);
      const onPause = () => setPlaying(false);
      const onEnded = () => {
        if (!finishSegmentPlayback()) onSegmentPlaybackEnd?.();
        setPlaying(false);
      };

      video.addEventListener("loadedmetadata", onLoaded);
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("play", onPlay);
      video.addEventListener("pause", onPause);
      video.addEventListener("ended", onEnded);

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
        video.currentTime = startSeconds;
        void video.play();
      },
      stepForward() {
        const video = videoRef.current;
        if (video) video.currentTime += 1 / fps;
      },
      stepBackward() {
        const video = videoRef.current;
        if (video) video.currentTime -= 1 / fps;
      },
    }), [fps, duration, seekVideo]);

    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        const video = videoRef.current;
        if (video) video.currentTime -= e.shiftKey ? 1 : (1 / fps);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        const video = videoRef.current;
        if (video) video.currentTime += e.shiftKey ? 1 : (1 / fps);
      } else if (e.key === " ") {
        e.preventDefault();
        const video = videoRef.current;
        if (video) {
          if (video.paused) void video.play();
          else video.pause();
        }
      }
    }, [fps]);

    const formatTime = (ms: number) => {
      const s = Math.floor(ms / 1000);
      const m = Math.floor(s / 60);
      const sec = s % 60;
      return `${m}:${String(sec).padStart(2, "0")}`;
    };

    const handleProgressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      seekVideo(Number(e.target.value));
    };

    return (
      <div className="rounded-2xl border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-video,#24302b)] overflow-hidden" onKeyDown={handleKeyDown} tabIndex={0}>
        <video
          ref={videoRef}
          src={videoUrl}
          className="w-full aspect-video bg-black"
          controls={false}
          preload="auto"
        />
        <div className="bg-[#1a1a2e] px-3 pt-2">
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
            className="block h-1.5 w-full cursor-pointer accent-[#22C55E] disabled:cursor-not-allowed disabled:opacity-40"
          />
        </div>
        <div className="flex items-center justify-between px-3 py-2 bg-[#1a1a2e] text-white text-xs">
          <div className="flex items-center gap-2">
            <button
              className="p-1 hover:bg-white/10 rounded"
              onClick={() => videoRef.current && (videoRef.current.currentTime -= 1 / fps)}
              title="后退一帧"
            >
              <SkipBack size={14} />
            </button>
            <button
              className="p-1 hover:bg-white/10 rounded"
              onClick={() => videoRef.current && (videoRef.current.paused ? videoRef.current.play() : videoRef.current.pause())}
              title="播放/暂停"
            >
              {playing ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <button
              className="p-1 hover:bg-white/10 rounded"
              onClick={() => videoRef.current && (videoRef.current.currentTime += 1 / fps)}
              title="前进一帧"
            >
              <SkipForward size={14} />
            </button>
            <span className="tabular-nums ml-2">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
          <div className="flex items-center gap-2">
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
          </div>
        </div>
      </div>
    );
  },
);
