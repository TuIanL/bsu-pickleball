import { Bone, Box, CircleDot, CirclePause, Diamond, Map, Maximize2, Minimize2, Pause, Play, Route, Volume2, VolumeX } from "lucide-react";
import React, { useEffect, useMemo, useRef, useState, type CSSProperties, type ChangeEvent } from "react";
import type {
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  FusedPlayerOverlayArtifact,
  FusedPlayerOverlayEntity,
  MatchSummary,
  PipelineTrackPoint,
  PlayerMarker,
  PoseOverlayArtifact,
  ServeEventsArtifact,
  TimelineMarker,
  TrackingOverlayArtifact,
  VideoOverlayLabel,
} from "../../types/report";
import { resolveDetectionFrame, resolveFusedPlayerOverlayFrame, resolvePoseFrame } from "./videoOverlayPlayback";
import { CourtMinimap } from "./CourtMinimap";
import { formatPlayerId } from "../../utils/analysisHelpers";

const BOUNCE_MARKER_WINDOW_SECONDS = 0.35;
const MAX_VISIBLE_BOUNCE_MARKERS = 3;
const BALL_TRAIL_SECONDS = 1.2;
const BALL_PATH_GAP_SECONDS = 0.7;
const MAX_BALL_PATH_POINTS = 84;

interface VideoAnalysisCardProps {
  compact?: boolean;
  labels: VideoOverlayLabel[];
  ballTrajectory?: BallTrajectoryArtifact | null;
  ballTrajectoryDetail?: string;
  ballTrajectoryLoadState?: OverlayLoadState;
  ballTrajectoryStatus?: string;
  bounceEvents?: BounceEventsArtifact | null;
  bounceEventsDetail?: string;
  bounceEventsLoadState?: OverlayLoadState;
  bounceEventsStatus?: string;
  match: MatchSummary;
  players: PlayerMarker[];
  poseOverlayDetail?: string;
  poseOverlayLoadState?: OverlayLoadState;
  poseOverlayStatus?: string;
  poseOverlay?: PoseOverlayArtifact | null;
  serveEvents?: ServeEventsArtifact | null;
  serveEventsDetail?: string;
  serveEventsLoadState?: OverlayLoadState;
  serveEventsStatus?: string;
  timeline: TimelineMarker[];
  trackingOverlayDetail?: string;
  trackingOverlayLoadState?: OverlayLoadState;
  trackingOverlayStatus?: string;
  trackingOverlay?: TrackingOverlayArtifact | null;
  /** joint 模式正式球员叠加层（multiview-fused-player-overlay.v1），优先于 trackingOverlay */
  fusedPlayerOverlay?: FusedPlayerOverlayArtifact | null;
  fusedPlayerOverlayDetail?: string;
  fusedPlayerOverlayLoadState?: OverlayLoadState;
  fusedPlayerOverlayStatus?: string;
  videoSrc?: string;
  /** H.264 源视频兜底：当 videoSrc（overlay 视频）编码不被浏览器支持时自动回退 */
  fallbackVideoSrc?: string;
  /** 管线轨迹点（含 court_point 球场坐标），用于实时小地图 */
  pipelineTracks?: PipelineTrackPoint[];
}

type OverlayLoadState = "idle" | "loading" | "available" | "unavailable" | "failed";

type ServeMarker = ReturnType<typeof resolveServeMarkers>[number];

const toneClass = {
  advantage: "border-[#22C55E]/40 bg-[#22C55E]/15 text-[#DCFCE7]",
  risk: "border-[#FF9500]/40 bg-[#FF9500]/15 text-[#FFD7A0]",
  error: "border-[#FF4D4F]/40 bg-[#FF4D4F]/15 text-[#FFC2C3]",
  training: "border-[#2F80ED]/40 bg-[#2F80ED]/15 text-[#BBD8FF]",
};

const markerClass = {
  advantage: "bg-[#22C55E]",
  risk: "bg-[#FF9500]",
  error: "bg-[#FF4D4F]",
  training: "bg-[#2F80ED]",
};

export function VideoAnalysisCard({
  compact = false,
  labels,
  ballTrajectory,
  ballTrajectoryDetail,
  ballTrajectoryLoadState = "idle",
  ballTrajectoryStatus,
  bounceEvents,
  bounceEventsDetail,
  bounceEventsLoadState = "idle",
  bounceEventsStatus,
  match,
  players,
  poseOverlayDetail,
  poseOverlayLoadState = "idle",
  poseOverlayStatus,
  poseOverlay,
  serveEvents,
  serveEventsDetail,
  serveEventsLoadState = "idle",
  serveEventsStatus,
  timeline,
  trackingOverlayDetail,
  trackingOverlayLoadState = "idle",
  trackingOverlayStatus,
  trackingOverlay,
  fusedPlayerOverlay,
  fusedPlayerOverlayDetail,
  fusedPlayerOverlayLoadState = "idle",
  fusedPlayerOverlayStatus,
  videoSrc,
  fallbackVideoSrc,
  pipelineTracks,
}: VideoAnalysisCardProps) {
  if (videoSrc) {
    return (
      <article className="sport-card overflow-hidden">
        <VideoCardHeader match={match} />
        <RealVideoOverlay
          match={match}
          ballTrajectory={ballTrajectory}
          ballTrajectoryDetail={ballTrajectoryDetail}
          ballTrajectoryLoadState={ballTrajectoryLoadState}
          ballTrajectoryStatus={ballTrajectoryStatus}
          bounceEvents={bounceEvents}
          bounceEventsDetail={bounceEventsDetail}
          bounceEventsLoadState={bounceEventsLoadState}
          bounceEventsStatus={bounceEventsStatus}
          poseOverlay={poseOverlay}
          poseOverlayDetail={poseOverlayDetail}
          poseOverlayLoadState={poseOverlayLoadState}
          poseOverlayStatus={poseOverlayStatus}
          serveEvents={serveEvents}
          serveEventsDetail={serveEventsDetail}
          serveEventsLoadState={serveEventsLoadState}
          serveEventsStatus={serveEventsStatus}
          trackingOverlay={trackingOverlay}
          trackingOverlayDetail={trackingOverlayDetail}
          trackingOverlayLoadState={trackingOverlayLoadState}
          trackingOverlayStatus={trackingOverlayStatus}
          fusedPlayerOverlay={fusedPlayerOverlay}
          fusedPlayerOverlayDetail={fusedPlayerOverlayDetail}
          fusedPlayerOverlayLoadState={fusedPlayerOverlayLoadState}
          fusedPlayerOverlayStatus={fusedPlayerOverlayStatus}
          videoSrc={videoSrc}
          fallbackVideoSrc={fallbackVideoSrc}
          pipelineTracks={pipelineTracks}
        />
      </article>
    );
  }

  return (
    <article className="sport-card overflow-hidden">
      <VideoCardHeader match={match} />

      <div className="relative aspect-video overflow-hidden bg-[#091016]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_45%,rgba(34,197,94,0.1),transparent_35%),linear-gradient(135deg,rgba(47,128,237,0.22),transparent_42%),linear-gradient(180deg,#151A1F,#080C10)]" />
        <div className="absolute inset-4 rounded-[1.75rem] border border-white/10 bg-black/20 shadow-[inset_0_0_80px_rgba(0,0,0,0.5)]" />

        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 100 56"
          role="img"
          aria-label="模拟匹克球视频分析，包含场地线和人员移动位置"
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur result="blur" stdDeviation="1.2" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect x="12" y="7" width="76" height="42" rx="1.5" fill="rgba(47,128,237,0.14)" />
          <rect x="12" y="7" width="76" height="42" rx="1.5" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="0.55" />
          <line x1="50" x2="50" y1="7" y2="49" stroke="rgba(255,255,255,0.55)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="28" y2="28" stroke="rgba(255,255,255,0.7)" strokeWidth="0.55" />
          <line x1="12" x2="88" y1="21.5" y2="21.5" stroke="rgba(34,197,94,0.62)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="34.5" y2="34.5" stroke="rgba(34,197,94,0.62)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="7" y2="7" stroke="rgba(255,255,255,0.55)" strokeWidth="0.45" />
          <line x1="12" x2="88" y1="49" y2="49" stroke="rgba(255,255,255,0.55)" strokeWidth="0.45" />
          <rect x="12" y="21.5" width="76" height="13" fill="rgba(34,197,94,0.045)" />

          <polyline
            fill="none"
            filter="url(#glow)"
            points="28,42 36,39 45,34 57,36 65,41 54,46 48,45"
            stroke="#22C55E"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.1"
          />
          <circle cx="28" cy="42" r="2.1" fill="#D9FF3F" stroke="#071008" strokeWidth="0.35" />
          <circle cx="54" cy="46" r="2.1" fill="#2F80ED" stroke="#071008" strokeWidth="0.35" />
          <circle cx="66" cy="41" r="5.6" fill="rgba(34,197,94,0.12)" />
          <circle cx="35" cy="39" r="4.8" fill="rgba(255,149,0,0.1)" />
          <circle cx="63" cy="38" r="4.2" fill="rgba(255,77,79,0.1)" />
        </svg>

        {players.map((player) => (
          <div
            className="absolute grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white/70 text-xs font-black text-[#071008] shadow-[0_8px_28px_rgba(0,0,0,0.42)]"
            key={player.id}
            style={
              {
                left: `${player.x}%`,
                top: `${player.y}%`,
                backgroundColor: player.color,
              } as CSSProperties
            }
          >
            {player.label}
          </div>
        ))}

        {labels.map((label) => (
          <span
            className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border px-3 py-1 text-[0.68rem] font-black shadow-[0_12px_32px_rgba(0,0,0,0.35)] backdrop-blur ${toneClass[label.tone]}`}
            key={label.id}
            style={{ left: `${label.x}%`, top: `${label.y}%` }}
          >
            {label.label}
          </span>
        ))}

        <div className="absolute left-4 top-4 rounded-2xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur">
          <p className="text-xs font-semibold text-slate-400">{match.teams}</p>
          <strong className="text-sm text-white">{match.venue}</strong>
        </div>

        <div className="absolute bottom-4 left-4 rounded-2xl border border-white/10 bg-black/50 px-3 py-2 backdrop-blur">
          <p className="text-xs font-semibold text-slate-400">{match.currentTime}</p>
          <strong className="text-sm text-white">{match.currentRally}</strong>
        </div>

        <button
          className="absolute left-1/2 top-1/2 grid size-16 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-[#22C55E]/35 bg-[#22C55E]/20 text-[#22C55E] shadow-[0_0_48px_rgba(34,197,94,0.22)] transition hover:scale-105 hover:bg-[#22C55E] hover:text-[#071008]"
          type="button"
          aria-label="播放演示视频"
        >
          <Play size={28} fill="currentColor" aria-hidden="true" />
        </button>
      </div>

      {!compact ? (
        <div className="border-t border-[#DDE9D6] bg-white/70 px-4 py-4 sm:px-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3 text-slate-600">
              <CirclePause size={18} aria-hidden="true" />
              <Volume2 size={18} aria-hidden="true" />
              <span className="text-xs font-bold">{match.currentTime} / {match.duration}</span>
            </div>
            <div className="relative h-2 flex-1 rounded-full bg-[#DFEADA]">
              <span className="absolute inset-y-0 left-0 rounded-full bg-[#22C55E]" style={{ width: "69%" }} />
              {timeline.map((marker) => (
                <span
                  className={`group absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#071008] ${markerClass[marker.tone]}`}
                  key={marker.id}
                  style={{ left: `${marker.position}%` }}
                  tabIndex={0}
                >
                  <span className="pointer-events-none absolute bottom-6 left-1/2 z-10 w-48 -translate-x-1/2 rounded-xl border border-white/10 bg-[#111318] px-3 py-2 text-xs font-semibold text-white opacity-0 shadow-2xl transition group-hover:opacity-100 group-focus:opacity-100">
                    {marker.time} · {marker.label}
                  </span>
                </span>
              ))}
            </div>
            <Maximize2 size={18} className="text-slate-600" aria-hidden="true" />
          </div>
        </div>
      ) : null}
    </article>
  );
}

/** 轻量错误边界：防止 CourtMinimap 内部异常导致整个视频卡片白屏 */
class CourtMinimapErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return null;
    return this.props.children;
  }
}

function VideoCardHeader({ match }: { match: MatchSummary }) {
  const hasScore = Boolean(match.score) && match.score !== "MVP";
  return (
    <div className="flex items-center justify-between border-b border-[#DDE9D6] px-4 py-3 sm:px-5">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">实时智能标注</p>
        <h2 className="mt-1 text-lg font-black text-[#14241B] sm:text-xl">视频回放 · {match.currentRally}</h2>
      </div>
      {hasScore ? (
        <div className="rounded-full border border-[#DDE9D6] bg-[#17231D] px-3 py-1 text-sm font-black text-white">
          {match.score}
        </div>
      ) : null}
    </div>
  );
}

function RealVideoOverlay({
  match,
  ballTrajectory,
  ballTrajectoryDetail,
  ballTrajectoryLoadState = "idle",
  ballTrajectoryStatus,
  bounceEvents,
  bounceEventsDetail,
  bounceEventsLoadState = "idle",
  bounceEventsStatus,
  poseOverlay,
  poseOverlayDetail,
  poseOverlayLoadState = "idle",
  poseOverlayStatus,
  serveEvents,
  serveEventsDetail,
  serveEventsLoadState = "idle",
  serveEventsStatus,
  trackingOverlay,
  trackingOverlayDetail,
  trackingOverlayLoadState = "idle",
  trackingOverlayStatus,
  fusedPlayerOverlay,
  fusedPlayerOverlayDetail,
  fusedPlayerOverlayLoadState = "idle",
  fusedPlayerOverlayStatus,
  videoSrc,
  fallbackVideoSrc,
  pipelineTracks,
}: {
  match: MatchSummary;
  ballTrajectory?: BallTrajectoryArtifact | null;
  ballTrajectoryDetail?: string;
  ballTrajectoryLoadState?: OverlayLoadState;
  ballTrajectoryStatus?: string;
  bounceEvents?: BounceEventsArtifact | null;
  bounceEventsDetail?: string;
  bounceEventsLoadState?: OverlayLoadState;
  bounceEventsStatus?: string;
  poseOverlay?: PoseOverlayArtifact | null;
  poseOverlayDetail?: string;
  poseOverlayLoadState?: OverlayLoadState;
  poseOverlayStatus?: string;
  serveEvents?: ServeEventsArtifact | null;
  serveEventsDetail?: string;
  serveEventsLoadState?: OverlayLoadState;
  serveEventsStatus?: string;
  trackingOverlay?: TrackingOverlayArtifact | null;
  trackingOverlayDetail?: string;
  trackingOverlayLoadState?: OverlayLoadState;
  trackingOverlayStatus?: string;
  fusedPlayerOverlay?: FusedPlayerOverlayArtifact | null;
  fusedPlayerOverlayDetail?: string;
  fusedPlayerOverlayLoadState?: OverlayLoadState;
  fusedPlayerOverlayStatus?: string;
  videoSrc: string;
  fallbackVideoSrc?: string;
  /** 管线轨迹点（含 court_point 球场坐标），用于实时小地图 */
  pipelineTracks?: PipelineTrackPoint[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [activeVideoSrc, setActiveVideoSrc] = useState<string | undefined>(videoSrc);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [naturalSize, setNaturalSize] = useState({ width: 1920, height: 1080 });
  const [showBoxes, setShowBoxes] = useState(true);
  const [showSkeleton, setShowSkeleton] = useState(true);
  const [showBallPoint, setShowBallPoint] = useState(true);
  const [showBallPath, setShowBallPath] = useState(true);
  const [showBounces, setShowBounces] = useState(true);
  const [showCourtHud, setShowCourtHud] = useState(false);

  const source = fusedPlayerOverlay?.source ?? trackingOverlay?.source ?? poseOverlay?.source ?? naturalSize;
  // 加载优先级（spec multiview-fused-player-overlay）：joint 模式 fused overlay 优先，
  // 不可用/无数据时 fallback 到 trackingOverlay（单摄行为完全不变）。
  const useFusedOverlay = Boolean(fusedPlayerOverlay?.frames.length);
  const fusedRenderFrame = useMemo(
    () => resolveFusedPlayerOverlayFrame(fusedPlayerOverlay?.frames ?? [], currentTime),
    [fusedPlayerOverlay, currentTime]
  );
  const detectionRenderFrame = useMemo(
    () => resolveDetectionFrame(trackingOverlay?.frames ?? [], currentTime),
    [currentTime, trackingOverlay]
  );
  const poseRenderFrame = useMemo(
    () => resolvePoseFrame(poseOverlay?.frames ?? [], currentTime),
    [currentTime, poseOverlay]
  );

  const boxCount = useFusedOverlay
    ? (fusedRenderFrame?.frame?.players?.length ?? 0)
    : (detectionRenderFrame?.detections.length ?? 0);
  const skeletonCount = poseRenderFrame?.frame?.subjects.length ?? 0;
  const poseInGap = poseRenderFrame?.inGap ?? false;
  const ballPathSegments = useMemo(() => resolveBallPathSegments(ballTrajectory, currentTime), [ballTrajectory, currentTime]);
  const ballSamples = useMemo(() => ballPathSegments.flat(), [ballPathSegments]);
  const allBounceMarkers = useMemo(() => resolveBounceMarkers(bounceEvents), [bounceEvents]);
  const visibleBounceMarkers = useMemo(
    () => resolveVisibleBounceMarkers(allBounceMarkers, currentTime),
    [allBounceMarkers, currentTime]
  );
  const ballCount = ballSamples.length;
  const boxesAvailable = useFusedOverlay
    ? Boolean(fusedPlayerOverlay?.frames.length)
    : Boolean(trackingOverlay?.frames.length);
  const skeletonAvailable = Boolean(poseOverlay?.frames.length);
  const ballAvailable = hasUsableBallSamples(ballTrajectory);
  const bounceAvailable = Boolean(allBounceMarkers.length);
  const trackingStatusLabel = useFusedOverlay
    ? resolveLayerStatus(fusedPlayerOverlayLoadState, fusedPlayerOverlay?.status ?? fusedPlayerOverlayStatus)
    : resolveLayerStatus(trackingOverlayLoadState, trackingOverlay?.status ?? trackingOverlayStatus);
  const poseStatusLabel = resolveLayerStatus(poseOverlayLoadState, poseOverlay?.status ?? poseOverlayStatus);
  const ballStatusLabel = resolveLayerStatus(ballTrajectoryLoadState, ballTrajectory?.status ?? ballTrajectoryStatus);
  const bounceStatusLabel = resolveLayerStatus(bounceEventsLoadState, bounceEvents?.status ?? bounceEventsStatus);
  const trackingDetail = useFusedOverlay
    ? layerDetail(fusedPlayerOverlayLoadState, fusedPlayerOverlay?.detail ?? fusedPlayerOverlayDetail, "融合球员 overlay")
    : layerDetail(trackingOverlayLoadState, trackingOverlay?.detail ?? trackingOverlayDetail, "人体框 overlay");
  const poseDetail = layerDetail(poseOverlayLoadState, poseOverlay?.detail ?? poseOverlayDetail, "RTMPose 骨架 overlay");
  const ballDetail = layerDetail(ballTrajectoryLoadState, ballTrajectory?.detail ?? ballTrajectoryDetail, "球轨迹 layer");
  const bounceDetail = layerDetail(bounceEventsLoadState, bounceEvents?.detail ?? bounceEventsDetail, "弹跳候选 marker");
  const serveDetail = layerDetail(serveEventsLoadState, serveEvents?.detail ?? serveEventsDetail, "发球候选 marker");
  const serveStatus = resolveLayerStatus(serveEventsLoadState, serveEvents?.status ?? serveEventsStatus);
  const fullscreenSupported = typeof document !== "undefined" && Boolean(document.fullscreenEnabled);
  const progress = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;
  const serveMarkers = useMemo(() => resolveServeMarkers(serveEvents, duration), [duration, serveEvents]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === containerRef.current);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }

    let animationId = 0;
    let videoFrameCallbackId = 0;
    const withVideoFrameCallback = "requestVideoFrameCallback" in HTMLVideoElement.prototype;

    const syncTime = () => setCurrentTime(video.currentTime);
    const schedule = () => {
      if (video.paused || video.ended) {
        return;
      }

      if (withVideoFrameCallback) {
        videoFrameCallbackId = video.requestVideoFrameCallback(() => {
          syncTime();
          schedule();
        });
      } else {
        animationId = window.requestAnimationFrame(() => {
          syncTime();
          schedule();
        });
      }
    };

    const handlePlay = () => {
      setIsPlaying(true);
      syncTime();
      schedule();
    };
    const handlePause = () => {
      setIsPlaying(false);
      syncTime();
    };
    const handleLoadedMetadata = () => {
      setDuration(Number.isFinite(video.duration) ? video.duration : 0);
      if (video.videoWidth && video.videoHeight) {
        setNaturalSize({ width: video.videoWidth, height: video.videoHeight });
      }
      syncTime();
    };
    const handleDurationChange = () => setDuration(Number.isFinite(video.duration) ? video.duration : 0);
    const handleVolumeChange = () => setIsMuted(video.muted);

    video.addEventListener("play", handlePlay);
    video.addEventListener("pause", handlePause);
    video.addEventListener("ended", handlePause);
    video.addEventListener("seeked", syncTime);
    video.addEventListener("seeking", syncTime);
    video.addEventListener("loadedmetadata", handleLoadedMetadata);
    video.addEventListener("durationchange", handleDurationChange);
    video.addEventListener("volumechange", handleVolumeChange);

    handleLoadedMetadata();
    setIsMuted(video.muted);
    if (!video.paused) {
      handlePlay();
    }

    return () => {
      video.removeEventListener("play", handlePlay);
      video.removeEventListener("pause", handlePause);
      video.removeEventListener("ended", handlePause);
      video.removeEventListener("seeked", syncTime);
      video.removeEventListener("seeking", syncTime);
      video.removeEventListener("loadedmetadata", handleLoadedMetadata);
      video.removeEventListener("durationchange", handleDurationChange);
      video.removeEventListener("volumechange", handleVolumeChange);
      if (withVideoFrameCallback && videoFrameCallbackId) {
        video.cancelVideoFrameCallback(videoFrameCallbackId);
      }
      if (animationId) {
        window.cancelAnimationFrame(animationId);
      }
    };
  }, [videoSrc]);

  const togglePlayback = () => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    if (video.paused) {
      void video.play();
    } else {
      video.pause();
    }
  };

  const toggleMuted = () => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.muted = !video.muted;
    setIsMuted(video.muted);
  };

  const toggleFullscreen = async () => {
    const container = containerRef.current;
    if (!container || !fullscreenSupported) {
      return;
    }
    if (document.fullscreenElement === container) {
      await document.exitFullscreen();
    } else {
      await container.requestFullscreen();
    }
  };

  const handleProgressChange = (event: ChangeEvent<HTMLInputElement>) => {
    const video = videoRef.current;
    if (!video || duration <= 0) {
      return;
    }
    const nextTime = (Number(event.target.value) / 100) * duration;
    video.currentTime = nextTime;
    setCurrentTime(nextTime);
  };

  const seekToServeMarker = (seekTime: number) => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.currentTime = seekTime;
    setCurrentTime(seekTime);
  };

  const handleVideoError = () => {
    // 当 overlay 视频（如 mpeg4 编码）无法被浏览器解码时，自动回退到 H.264 源视频
    if (activeVideoSrc !== fallbackVideoSrc && fallbackVideoSrc) {
      console.warn(
        "[VideoAnalysisCard] 主视频源加载失败（可能编码不支持），自动回退到源视频",
        { failedSrc: activeVideoSrc, fallback: fallbackVideoSrc },
      );
      setActiveVideoSrc(fallbackVideoSrc);
    }
  };

  return (
    <div className="bg-[#091016]">
      <div
        className="relative aspect-video overflow-hidden bg-[#091016] data-[fullscreen=true]:aspect-auto data-[fullscreen=true]:h-screen data-[fullscreen=true]:w-screen"
        data-fullscreen={isFullscreen}
        ref={containerRef}
      >
        <video
          className="absolute inset-0 h-full w-full bg-black object-contain"
          muted={isMuted}
          playsInline
          preload="metadata"
          ref={videoRef}
          src={activeVideoSrc}
          onError={handleVideoError}
        />
        {activeVideoSrc && duration === 0 && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/60">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            <span className="text-sm text-white/70">正在加载视频（大文件可能需要几秒）…</span>
          </div>
        )}

        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          viewBox={`0 0 ${source.width} ${source.height}`}
        >
        {showBoxes && useFusedOverlay
          ? fusedRenderFrame?.frame?.players?.map((player) => (
            <FusedPlayerBox
              key={player.player_id}
              entity={player}
              source={source}
              inGap={fusedRenderFrame?.inGap ?? false}
            />
          ))
          : null}
        {showBoxes && !useFusedOverlay && detectionRenderFrame?.detections.map((detection) => {
          const [x1, y1, x2, y2] = detection.bbox;
          const width = Math.max(0, x2 - x1);
          const height = Math.max(0, y2 - y1);
          return (
            <g key={`${detection.track_id ?? "person"}-${x1}-${y1}`}>
              <rect
                fill="rgba(34,197,94,0.08)"
                height={height}
                rx={Math.max(4, source.width * 0.003)}
                stroke="#22C55E"
                strokeWidth={Math.max(2, source.width * 0.0018)}
                width={width}
                x={x1}
                y={y1}
              />
              <text
                fill="#D9FF3F"
                fontSize={Math.max(14, source.width * 0.014)}
                fontWeight="800"
                paintOrder="stroke"
                stroke="rgba(0,0,0,0.75)"
                strokeWidth={Math.max(3, source.width * 0.002)}
                x={x1}
                y={Math.max(18, y1 - 8)}
              >
                {formatPlayerId(detection.player_id) || "person"} · {Math.round(detection.confidence * 100)}%
              </text>
            </g>
          );
        })}

        {showSkeleton && poseRenderFrame?.frame?.subjects.map((subject) => (
          <g
            key={`${subject.track_id}-${subject.bbox.join("-")}`}
            opacity={poseInGap ? 0 : 1}
            style={{ transition: "opacity 0.3s ease-in-out" }}
          >
            {poseOverlay?.skeleton_edges.map((edge) => {
              const from = subject.keypoints.find((keypoint) => keypoint.name === edge.from_keypoint && keypoint.visible);
              const to = subject.keypoints.find((keypoint) => keypoint.name === edge.to_keypoint && keypoint.visible);
              if (!from || !to) {
                return null;
              }
              return (
                <line
                  key={`${subject.track_id}-${edge.from_keypoint}-${edge.to_keypoint}`}
                  stroke="#6BB8FF"
                  strokeLinecap="round"
                  strokeWidth={Math.max(3, source.width * 0.0022)}
                  x1={from.x}
                  x2={to.x}
                  y1={from.y}
                  y2={to.y}
                />
              );
            })}
            {subject.keypoints.filter((keypoint) => keypoint.visible).map((keypoint) => (
              <circle
                cx={keypoint.x}
                cy={keypoint.y}
                fill="#D9FF3F"
                key={`${subject.track_id}-${keypoint.name}`}
                r={Math.max(4, source.width * 0.0032)}
                stroke="#071008"
                strokeWidth={Math.max(1.5, source.width * 0.0012)}
              />
            ))}
          </g>
        ))}

        {showBallPath ? ballPathSegments.map((segment, segmentIndex) => segment.slice(1).map((sample, index) => {
          const previous = segment[index];
          const [x1, y1] = previous.image_xy;
          const [x2, y2] = sample.image_xy;
          const isEstimated = previous.interpolated || sample.interpolated;
          const confidence = Math.min(previous.confidence ?? 1, sample.confidence ?? 1);
          return (
            <line
              data-testid="video-ball-segment"
              key={`${segmentIndex}-${sample.frame_index}-${sample.timestamp_sec}`}
              opacity={isEstimated ? 0.42 : Math.max(0.45, confidence)}
              stroke="#D9FF3F"
              strokeDasharray={isEstimated ? "7 7" : undefined}
              strokeLinecap="round"
              strokeWidth={Math.max(2, source.width * 0.0018)}
              x1={x1}
              x2={x2}
              y1={y1}
              y2={y2}
            />
          );
        })) : null}

        {showBallPoint ? ballSamples.slice(-1).map((sample) => {
          const [x, y] = sample.image_xy;
          return (
            <g data-testid="video-ball-current" key={`${sample.frame_index}-${sample.timestamp_sec}`}>
              <circle cx={x} cy={y} fill="rgba(217,255,63,0.26)" r={Math.max(9, source.width * 0.006)} />
              <circle
                cx={x}
                cy={y}
                fill="#F8FAFC"
                r={Math.max(5, source.width * 0.004)}
                stroke="#D9FF3F"
                strokeWidth={Math.max(2, source.width * 0.0016)}
              />
            </g>
          );
        }) : null}

        {showBounces && visibleBounceMarkers.map((event) => {
          const [x, y] = event.image_xy;
          return (
            <g data-testid="video-bounce" key={event.event_id}>
              <circle
                cx={x}
                cy={y}
                fill="rgba(255,149,0,0.24)"
                r={Math.max(6, source.width * 0.0048)}
                stroke="#FF9500"
                strokeWidth={Math.max(2, source.width * 0.0012)}
              />
            </g>
          );
        })}

        </svg>

        <div className="absolute left-4 top-4 rounded-2xl border border-white/10 bg-black/50 px-3 py-2 backdrop-blur">
        <p className="text-xs font-semibold text-slate-400">{match.teams}</p>
        <strong className="text-sm text-white">{match.venue}</strong>
        </div>

        <div aria-label="视频分析图层" className="absolute right-2 top-2 z-20 flex gap-1.5 sm:right-4 sm:top-4">
          <OverlayToggle
            active={showBoxes}
            available={boxesAvailable}
            icon={<Box size={15} aria-hidden="true" />}
            label="人体框"
            onClick={() => setShowBoxes((value) => !value)}
            tone="green"
            unavailableReason={trackingDetail}
          />
          <OverlayToggle
            active={showSkeleton}
            available={skeletonAvailable}
            icon={<Bone size={15} aria-hidden="true" />}
            label="骨架"
            onClick={() => setShowSkeleton((value) => !value)}
            tone="blue"
            unavailableReason={poseDetail}
          />
          <OverlayToggle
            active={showBallPoint}
            available={ballAvailable}
            icon={<CircleDot size={15} aria-hidden="true" />}
            label="球点"
            onClick={() => setShowBallPoint((value) => !value)}
            tone="lime"
            unavailableReason={ballDetail}
          />
          <OverlayToggle
            active={showBallPath}
            available={ballAvailable}
            icon={<Route size={15} aria-hidden="true" />}
            label="球路"
            onClick={() => setShowBallPath((value) => !value)}
            tone="lime"
            unavailableReason={ballDetail}
          />
          <OverlayToggle
            active={showBounces}
            available={bounceAvailable}
            icon={<Diamond size={15} aria-hidden="true" />}
            label="弹跳候选"
            onClick={() => setShowBounces((value) => !value)}
            tone="orange"
            unavailableReason={bounceDetail}
          />
        </div>

        {(pipelineTracks?.length || ballAvailable || bounceAvailable) ? (
          <div className="absolute right-2 top-12 z-10 flex origin-top-right flex-col items-end gap-1.5 scale-[0.82] shadow-black/20 sm:right-4 sm:top-14 sm:scale-100">
            <button
              aria-expanded={showCourtHud}
              aria-label={showCourtHud ? "收起球场地图" : "展开球场地图"}
              className={`flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-[0.68rem] font-bold backdrop-blur transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#D9FF3F] ${
                showCourtHud
                  ? "border-[#D9FF3F]/60 bg-[#D9FF3F]/18 text-[#D9FF3F]"
                  : "border-white/15 bg-black/50 text-white hover:bg-black/70"
              }`}
              onClick={() => setShowCourtHud((value) => !value)}
              type="button"
            >
              <Map size={14} aria-hidden="true" />
              球场地图
            </button>
            {showCourtHud ? (
              <div className="max-h-[min(24rem,calc(100vh-15rem))] overflow-y-auto rounded-lg">
                <CourtMinimapErrorBoundary>
                  <CourtMinimap
                    ballTrajectory={ballTrajectory}
                    bounceEvents={bounceEvents}
                    showBallPath={showBallPath}
                    showBallPoint={showBallPoint}
                    showBounces={showBounces}
                    tracks={pipelineTracks ?? []}
                    currentTimeSec={currentTime}
                    trailSeconds={3}
                  />
                </CourtMinimapErrorBoundary>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="absolute bottom-24 left-4 rounded-2xl border border-white/10 bg-black/50 px-3 py-2 text-white backdrop-blur">
        <p className="text-xs font-semibold text-slate-400">
          {formatSeconds(currentTime)} · {boxCount} 个框 · {skeletonCount} 组骨架
          {ballTrajectoryLoadState !== "idle" ? ` · ${ballCount ? "球可见" : "球层无当前点"}` : ""}
        </p>
        <strong className="text-sm">{match.currentRally}</strong>
        {boxCount === 0 || skeletonCount === 0 ? (
          <p className="mt-1 max-w-sm text-[0.68rem] font-semibold text-slate-300">
            {boxCount === 0
              ? statusCopy(trackingStatusLabel, trackingDetail)
              : statusCopy(poseStatusLabel, poseDetail)}
          </p>
        ) : null}
        {ballTrajectoryLoadState !== "idle" && !ballCount ? (
          <p className="mt-1 max-w-sm text-[0.68rem] font-semibold text-slate-300">
            球轨迹：{statusCopy(ballStatusLabel, ballDetail)}
          </p>
        ) : null}
        {ballCount ? <p className="mt-1 max-w-sm text-[0.68rem] font-semibold text-slate-300">图像空间球路 · 小地图为球场平面投影 · 视觉估算</p> : null}
        </div>

        <div className="absolute inset-x-4 bottom-4 flex flex-col gap-3 sm:left-auto sm:right-4 sm:w-[min(30rem,calc(100%-2rem))]">
          <div className="rounded-2xl border border-white/10 bg-black/50 p-3 text-white backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              aria-label={isPlaying ? "暂停视频" : "播放视频"}
              className="grid size-9 place-items-center rounded-full border border-white/15 bg-white/10 text-white transition hover:bg-white/20"
              onClick={togglePlayback}
              type="button"
            >
              {isPlaying ? <Pause size={17} fill="currentColor" aria-hidden="true" /> : <Play size={17} fill="currentColor" aria-hidden="true" />}
            </button>
            <button
              aria-label={isMuted ? "打开声音" : "静音视频"}
              className="grid size-9 place-items-center rounded-full border border-white/15 bg-white/10 text-white transition hover:bg-white/20"
              onClick={toggleMuted}
              type="button"
            >
              {isMuted ? <VolumeX size={17} aria-hidden="true" /> : <Volume2 size={17} aria-hidden="true" />}
            </button>
            <span className="w-24 text-xs font-bold text-slate-200">
              {formatSeconds(currentTime)} / {formatSeconds(duration)}
            </span>
            <div className="relative flex-1">
              <input
                aria-label="视频播放进度"
                className="relative z-10 h-2 w-full accent-[#22C55E]"
                max="100"
                min="0"
                onChange={handleProgressChange}
                step="0.1"
                type="range"
                value={progress}
              />
            </div>
            <button
              aria-label={isFullscreen ? "退出全屏" : "全屏播放"}
              className="grid size-9 place-items-center rounded-full border border-white/15 bg-white/10 text-white transition hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-45"
              disabled={!fullscreenSupported}
              onClick={toggleFullscreen}
              type="button"
            >
              {isFullscreen ? <Minimize2 size={17} aria-hidden="true" /> : <Maximize2 size={17} aria-hidden="true" />}
            </button>
          </div>
          <div className="mt-2 h-1 rounded-full bg-white/15">
            <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${progress}%` }} />
          </div>
            {serveEventsLoadState !== "idle" ? (
              <p className="mt-2 text-[0.68rem] font-semibold text-slate-300">
                发球候选：{serveMarkers.length ? `${serveMarkers.length} 个候选` : statusCopy(serveStatus, serveDetail)}
              </p>
            ) : null}
            {bounceEventsLoadState !== "idle" ? (
              <p className="mt-1 text-[0.68rem] font-semibold text-slate-300">
                弹跳候选：{allBounceMarkers.length ? `${allBounceMarkers.length} 个候选 · 当前显示 ${visibleBounceMarkers.length} 个 · 仅供复盘` : statusCopy(bounceStatusLabel, bounceDetail)}
              </p>
            ) : null}
          </div>
        </div>
      </div>
      <ServeRallyStrip
        currentTime={currentTime}
        loadState={serveEventsLoadState}
        markers={serveMarkers}
        onSeek={seekToServeMarker}
        status={serveStatus}
        statusDetail={serveDetail}
      />
    </div>
  );
}

export function ServeRallyStrip({
  currentTime,
  loadState,
  markers,
  onSeek,
  status,
  statusDetail,
}: {
  currentTime: number;
  loadState: OverlayLoadState;
  markers: ServeMarker[];
  onSeek: (seekTime: number) => void;
  status: string;
  statusDetail: string;
}) {
  if (loadState === "idle") {
    return null;
  }

  const showMarkers = markers.length > 0;
  return (
    <div className="border-t border-white/10 bg-[#0D1419] px-4 py-3 text-white">
      <div className="mx-auto flex w-full max-w-full flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-black uppercase tracking-wide text-[#D9FF3F]">发球候选导航</p>
            <p className="text-[0.68rem] font-semibold text-slate-300">
              {showMarkers ? `${markers.length} 个回合起点候选` : statusCopy(status, statusDetail)}
            </p>
          </div>
          {status === "partial" ? (
            <span className="rounded-full border border-[#FF9500]/35 bg-[#FF9500]/15 px-2 py-1 text-[0.65rem] font-black text-[#FFD7A0]">
              降级信号
            </span>
          ) : null}
        </div>
        {showMarkers ? (
          <div className="flex w-full gap-2 overflow-x-auto overscroll-x-contain pb-1 [scrollbar-width:thin]">
            {markers.map((marker, index) => {
              const active = isServeMarkerActive(marker, currentTime);
              return (
                <button
                  aria-label={`跳转到第 ${index + 1} 个发球候选 ${formatSeconds(marker.timestamp_seconds)}`}
                  className={`min-h-20 w-36 shrink-0 rounded-lg border p-3 text-left transition hover:-translate-y-0.5 hover:border-[#D9FF3F]/70 ${
                    active
                      ? "border-[#D9FF3F] bg-[#D9FF3F]/18 shadow-[0_0_22px_rgba(217,255,63,0.25)]"
                      : "border-white/10 bg-white/[0.06]"
                  }`}
                  key={marker.id}
                  onClick={() => onSeek(marker.seekTime)}
                  title={`${serveMarkerSignalSummary(marker)} · ${marker.reason}`}
                  type="button"
                >
                  <span className="block text-[0.65rem] font-black uppercase text-slate-400">#{String(index + 1).padStart(2, "0")}</span>
                  <span className="mt-1 block text-lg font-black text-white">{formatSeconds(marker.timestamp_seconds)}</span>
                  <span className="mt-1 block truncate text-[0.68rem] font-semibold text-slate-300">
                    {Math.round(marker.confidence * 100)}% · {serveMarkerModeLabel(marker.detection_mode)}
                  </span>
                  <span className="mt-1 block truncate text-[0.65rem] font-semibold text-slate-400">
                    {serveMarkerSignalSummary(marker)}
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function OverlayToggle({
  active,
  available,
  icon,
  label,
  onClick,
  tone,
  unavailableReason,
}: {
  active: boolean;
  available: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  tone: "blue" | "green" | "lime" | "orange";
  unavailableReason: string;
}) {
  const activeClasses = {
    blue: "border-[#2F80ED]/60 bg-[#2F80ED]/25 text-[#BBD8FF]",
    green: "border-[#22C55E]/60 bg-[#22C55E]/22 text-[#D9FF3F]",
    lime: "border-[#D9FF3F]/60 bg-[#D9FF3F]/18 text-[#D9FF3F]",
    orange: "border-[#FF9500]/60 bg-[#FF9500]/20 text-[#FFD7A0]",
  }[tone];

  return (
    <button
      aria-label={`${active ? "隐藏" : "显示"}${label}`}
      aria-pressed={active}
      className={`grid size-8 place-items-center rounded-md border backdrop-blur transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#D9FF3F] disabled:cursor-not-allowed disabled:opacity-45 ${active ? activeClasses : "border-white/15 bg-black/50 text-white"}`}
      disabled={!available}
      onClick={onClick}
      title={available ? `${active ? "隐藏" : "显示"}${label}` : unavailableReason}
      type="button"
    >
      {icon}
    </button>
  );
}

function resolveLayerStatus(loadState: OverlayLoadState, artifactStatus?: string): string {
  if (loadState === "loading") {
    return "loading";
  }
  if (loadState === "failed") {
    return "failed";
  }
  if (loadState === "available") {
    return artifactStatus ?? "available";
  }
  return artifactStatus ?? "unavailable";
}

function layerDetail(loadState: OverlayLoadState, detail: string | undefined, label: string): string {
  if (loadState === "loading") {
    return `${label} 正在按需读取，视频可先播放。`;
  }
  if (loadState === "failed") {
    return `${label} 读取失败，其他视频层仍可使用。`;
  }
  return detail ?? `${label} 暂不可用`;
}

function statusCopy(status: string, detail: string): string {
  if (status === "loading") {
    return detail;
  }
  if (status === "available") {
    return detail;
  }
  if (status === "no_detections" || status === "no_poses" || status === "no_candidates") {
    return detail;
  }
  return detail;
}

type ImageBallSample = BallTrajectoryArtifact["samples"][number] & { image_xy: [number, number] };

function hasImagePoint(sample: BallTrajectoryArtifact["samples"][number]): sample is ImageBallSample {
  return Array.isArray(sample.image_xy)
    && sample.image_xy.length >= 2
    && Number.isFinite(sample.image_xy[0])
    && Number.isFinite(sample.image_xy[1])
    && Number.isFinite(sample.timestamp_sec)
    && (sample.accepted ?? true);
}

function hasUsableBallSamples(ballTrajectory: BallTrajectoryArtifact | null | undefined): boolean {
  return (ballTrajectory?.samples ?? []).some(hasImagePoint);
}

function sampleBallPathEvenly(samples: ImageBallSample[], maxPoints: number): ImageBallSample[] {
  if (samples.length <= maxPoints) return samples;
  return Array.from(
    { length: maxPoints },
    (_, index) => samples[Math.round((index * (samples.length - 1)) / (maxPoints - 1))],
  );
}

function resolveBallPathSegments(
  ballTrajectory: BallTrajectoryArtifact | null | undefined,
  currentTime: number,
): ImageBallSample[][] {
  const cutoff = currentTime - BALL_TRAIL_SECONDS;
  const samples = (ballTrajectory?.samples ?? [])
    .filter(hasImagePoint)
    .filter((sample) => sample.timestamp_sec >= cutoff && sample.timestamp_sec <= currentTime)
    .sort((left, right) => left.timestamp_sec - right.timestamp_sec);
  const segments: ImageBallSample[][] = [];
  let active: ImageBallSample[] = [];

  for (const sample of samples) {
    const previous = active.at(-1);
    if (previous && sample.timestamp_sec - previous.timestamp_sec > BALL_PATH_GAP_SECONDS) {
      if (active.length) segments.push(sampleBallPathEvenly(active, MAX_BALL_PATH_POINTS));
      active = [];
    }
    active.push(sample);
  }

  if (active.length) segments.push(sampleBallPathEvenly(active, MAX_BALL_PATH_POINTS));
  return segments;
}

function resolveBounceMarkers(bounceEvents: BounceEventsArtifact | null | undefined) {
  return (bounceEvents?.events ?? []).filter((event) => Array.isArray(event.image_xy) && event.image_xy.length >= 2);
}

function resolveVisibleBounceMarkers(
  markers: ReturnType<typeof resolveBounceMarkers>,
  currentTime: number
) {
  return markers
    .filter((event) => typeof event.timestamp_sec === "number" && Math.abs(event.timestamp_sec - currentTime) <= BOUNCE_MARKER_WINDOW_SECONDS)
    .sort((left, right) => Math.abs(left.timestamp_sec - currentTime) - Math.abs(right.timestamp_sec - currentTime))
    .slice(0, MAX_VISIBLE_BOUNCE_MARKERS);
}

function formatSeconds(value: number): string {
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function serveMarkerModeLabel(mode: string | undefined): string {
  if (mode === "pose") {
    return "姿态峰值";
  }
  if (mode === "roi") {
    return "ROI 降级";
  }
  if (mode === "tracking") {
    return "tracking 降级";
  }
  return "上下文检测";
}

function serveMarkerSignalSummary(marker: ServeEventsArtifact["events"][number]): string {
  const signals = marker.signals;
  if (!signals) {
    return "信号：旧版候选";
  }
  const baseline = Math.round((signals.baseline_position_score ?? 0) * 100);
  const stillness = Math.round((signals.pre_stillness_score ?? 0) * 100);
  const peak = Math.round(Math.max(signals.arm_motion_peak_score ?? 0, signals.roi_motion_peak_score ?? 0) * 100);
  const rally = Math.round((signals.rally_after_score ?? 0) * 100);
  return `底线 ${baseline}% · 静止 ${stillness}% · 峰值 ${peak}% · 回合 ${rally}%`;
}

export function resolveServeMarkers(serveEvents: ServeEventsArtifact | null | undefined, duration: number) {
  if (!serveEvents?.events.length || duration <= 0) {
    return [];
  }
  return serveEvents.events.map((event) => ({
    ...event,
    position: Math.min(100, Math.max(0, (event.timestamp_seconds / duration) * 100)),
    seekTime: Math.min(duration, Math.max(0, event.seek_time_seconds)),
  }));
}

function isServeMarkerActive(marker: ServeMarker, currentTime: number): boolean {
  const start = marker.start_time_seconds ?? Math.max(0, marker.timestamp_seconds - 2);
  const end = marker.end_time_seconds ?? marker.timestamp_seconds + 4;
  return currentTime >= start && currentTime <= end;
}

// ---- 融合球员叠加层（multiview-fused-player-overlay.v1）渲染 -----------------

const FUSED_EVIDENCE_STYLE = {
  base_observed: { stroke: "#22C55E", dash: undefined, fill: "rgba(34,197,94,0.10)", label: "检测" },
  guided_observed: { stroke: "#22C55E", dash: undefined, fill: "rgba(34,197,94,0.10)", label: "协同恢复" },
  refined_observed: { stroke: "#38BDF8", dash: undefined, fill: "rgba(56,189,248,0.10)", label: "离线精修" },
  cross_view_projected: { stroke: "#FACC15", dash: "8 6", fill: "rgba(250,204,21,0.08)", label: "双摄补全" },
  predicted_only: { stroke: "#94A3B8", dash: "3 5", fill: "rgba(148,163,184,0.06)", label: "预测" },
} as const;

function FusedPlayerBox({
  entity,
  source,
  inGap,
}: {
  entity: FusedPlayerOverlayEntity;
  source: { width: number; height: number };
  inGap: boolean;
}) {
  const style = FUSED_EVIDENCE_STYLE[entity.evidence_type];
  const opacity = inGap ? 0 : 1;
  const label = entity.label ?? entity.player_id;

  if (entity.evidence_type === "predicted_only") {
    // 预测仅光圈：footpoint + identity badge + uncertainty halo（不渲染人体框）
    if (!entity.footpoint) {
      return null;
    }
    return (
      <g key={`fused-${entity.player_id}`} opacity={opacity} style={{ transition: "opacity 0.3s ease-in-out" }}>
        <circle
          cx={entity.footpoint[0]}
          cy={entity.footpoint[1]}
          fill="none"
          r={Math.max(14, source.width * 0.012)}
          stroke="#94A3B8"
          strokeDasharray="3 5"
          strokeWidth={Math.max(1.5, source.width * 0.0012)}
        />
        <circle
          cx={entity.footpoint[0]}
          cy={entity.footpoint[1]}
          fill="#94A3B8"
          r={Math.max(3.5, source.width * 0.003)}
          stroke="rgba(0,0,0,0.6)"
          strokeWidth={1}
        />
        <text
          fill="#CBD5E1"
          fontSize={Math.max(12, source.width * 0.011)}
          fontWeight="700"
          paintOrder="stroke"
          stroke="rgba(0,0,0,0.75)"
          strokeWidth={Math.max(3, source.width * 0.002)}
          textAnchor="middle"
          x={entity.footpoint[0]}
          y={Math.max(16, entity.footpoint[1] - Math.max(14, source.width * 0.012) - 6)}
        >
          {label} · 预测
        </text>
      </g>
    );
  }

  if (!entity.bbox) {
    // 无历史 bbox：footpoint + identity badge + halo（不伪造人体框）
    if (!entity.footpoint) {
      return null;
    }
    return (
      <g key={`fused-${entity.player_id}`} opacity={opacity} style={{ transition: "opacity 0.3s ease-in-out" }}>
        <circle
          cx={entity.footpoint[0]}
          cy={entity.footpoint[1]}
          fill="none"
          r={Math.max(12, source.width * 0.01)}
          stroke={style.stroke}
          strokeDasharray="5 5"
          strokeWidth={Math.max(1.5, source.width * 0.0012)}
        />
        <circle
          cx={entity.footpoint[0]}
          cy={entity.footpoint[1]}
          fill={style.stroke}
          r={Math.max(3.5, source.width * 0.003)}
          stroke="rgba(0,0,0,0.6)"
          strokeWidth={1}
        />
        <text
          fill="#F8FAFC"
          fontSize={Math.max(12, source.width * 0.011)}
          fontWeight="700"
          paintOrder="stroke"
          stroke="rgba(0,0,0,0.75)"
          strokeWidth={Math.max(3, source.width * 0.002)}
          x={entity.footpoint[0]}
          y={Math.max(16, entity.footpoint[1] - Math.max(12, source.width * 0.01) - 6)}
          textAnchor="middle"
        >
          {label}
          {entity.evidence_type === "cross_view_projected" ? ` · ${style.label}` : ""}
        </text>
      </g>
    );
  }

  const [x1, y1, x2, y2] = entity.bbox;
  const width = Math.max(0, x2 - x1);
  const height = Math.max(0, y2 - y1);
  const isProjected = entity.evidence_type === "cross_view_projected";
  // 展示稳定性（stabilize-multiview-overlay-display）：
  // - view_scale_profiled：尺度投影虚线框（来源标签区分真实检测）
  // - bbox_stale：stale memory bbox 按 bbox_age_ms 淡化
  const isScaleProfiled = entity.bbox_source === "view_scale_profiled";
  const staleOpacity = entity.bbox_stale ? 0.55 : 1;
  const boxOpacity = (isProjected ? 0.85 : 1) * staleOpacity;
  const sourceLabel = isScaleProfiled
    ? " · 尺度投影"
    : entity.evidence_type !== "base_observed" && entity.evidence_type !== "guided_observed"
      ? ` · ${style.label}`
      : "";
  return (
    <g key={`fused-${entity.player_id}`} opacity={boxOpacity} style={{ transition: "opacity 0.3s ease-in-out" }}>
      <rect
        fill={style.fill}
        height={height}
        rx={Math.max(4, source.width * 0.003)}
        stroke={style.stroke}
        strokeDasharray={isScaleProfiled ? "10 6" : style.dash}
        strokeWidth={Math.max(2, source.width * 0.0018)}
        width={width}
        x={x1}
        y={y1}
      />
      <text
        fill="#D9FF3F"
        fontSize={Math.max(13, source.width * 0.013)}
        fontWeight="800"
        paintOrder="stroke"
        stroke="rgba(0,0,0,0.75)"
        strokeWidth={Math.max(3, source.width * 0.002)}
        x={x1}
        y={Math.max(18, y1 - 8)}
      >
        {label}
        {sourceLabel}
      </text>
    </g>
  );
}
