import { useCallback, useEffect, useImperativeHandle, useRef, forwardRef, useState } from "react";
import { Play, Pause, SkipForward, SkipBack, ChevronLeft, ChevronRight } from "lucide-react";

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
  syncQuality?: string;
}

export const SegmentVideoPlayer = forwardRef<SegmentVideoPlayerHandle, SegmentVideoPlayerProps>(
  function SegmentVideoPlayer(
    { videoUrl, fps = 30, segmentStartMs, segmentEndMs, trackLabel, trackOptions, onTrackChange, onTimeUpdate, onDurationReady, syncQuality },
    ref,
  ) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [playing, setPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const segmentLoopRef = useRef<{ start: number; end: number } | null>(null);

    useEffect(() => {
      const video = videoRef.current;
      if (!video) return;

      const onLoaded = () => {
        setDuration(video.duration * 1000);
        onDurationReady?.(video.duration * 1000);
      };
      const onTime = () => {
        const ms = video.currentTime * 1000;
        setCurrentTime(ms);
        onTimeUpdate?.(ms);
        // Segment loop mode
        const loop = segmentLoopRef.current;
        if (loop && ms >= loop.end) {
          video.pause();
          segmentLoopRef.current = null;
          setPlaying(false);
        }
      };
      const onPlay = () => setPlaying(true);
      const onPause = () => setPlaying(false);

      video.addEventListener("loadedmetadata", onLoaded);
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("play", onPlay);
      video.addEventListener("pause", onPause);

      return () => {
        video.removeEventListener("loadedmetadata", onLoaded);
        video.removeEventListener("timeupdate", onTime);
        video.removeEventListener("play", onPlay);
        video.removeEventListener("pause", onPause);
      };
    }, [videoUrl, onTimeUpdate, onDurationReady]);

    useImperativeHandle(ref, () => ({
      seekToTakeTime(ms: number) {
        const video = videoRef.current;
        if (video && duration > 0) {
          video.currentTime = Math.max(0, Math.min(ms / 1000, duration / 1000));
        }
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
        segmentLoopRef.current = { start: startMs / 1000, end: endMs / 1000 };
        video.currentTime = startMs / 1000;
        video.play();
      },
      stepForward() {
        const video = videoRef.current;
        if (video) video.currentTime += 1 / fps;
      },
      stepBackward() {
        const video = videoRef.current;
        if (video) video.currentTime -= 1 / fps;
      },
    }), [fps, duration]);

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
        if (video) video.paused ? video.play() : video.pause();
      }
    }, [fps]);

    const formatTime = (ms: number) => {
      const s = Math.floor(ms / 1000);
      const m = Math.floor(s / 60);
      const sec = s % 60;
      return `${m}:${String(sec).padStart(2, "0")}`;
    };

    return (
      <div className="rounded-2xl border border-[#DDE9D6] bg-black overflow-hidden" onKeyDown={handleKeyDown} tabIndex={0}>
        <video
          ref={videoRef}
          src={videoUrl}
          className="w-full aspect-video bg-black"
          controls={false}
          preload="auto"
        />
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
