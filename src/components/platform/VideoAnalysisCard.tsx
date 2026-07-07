import { CirclePause, Maximize2, Minimize2, Pause, Play, Volume2, VolumeX } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ChangeEvent } from "react";
import type {
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  MatchSummary,
  PlayerMarker,
  PoseOverlayArtifact,
  ServeEventsArtifact,
  TimelineMarker,
  TrackingOverlayArtifact,
  VideoOverlayLabel,
} from "../../types/report";
import { resolveDetectionFrame, resolvePoseFrame } from "./videoOverlayPlayback";

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
  videoSrc?: string;
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
  videoSrc,
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
          videoSrc={videoSrc}
        />
        {!compact ? (
          <RealVideoFooter
            poseOverlayDetail={poseOverlayDetail}
            poseOverlayLoadState={poseOverlayLoadState}
            poseOverlayStatus={poseOverlayStatus}
            poseOverlay={poseOverlay}
            ballTrajectory={ballTrajectory}
            ballTrajectoryDetail={ballTrajectoryDetail}
            ballTrajectoryLoadState={ballTrajectoryLoadState}
            ballTrajectoryStatus={ballTrajectoryStatus}
            bounceEvents={bounceEvents}
            bounceEventsDetail={bounceEventsDetail}
            bounceEventsLoadState={bounceEventsLoadState}
            bounceEventsStatus={bounceEventsStatus}
            trackingOverlayDetail={trackingOverlayDetail}
            trackingOverlayLoadState={trackingOverlayLoadState}
            trackingOverlayStatus={trackingOverlayStatus}
            trackingOverlay={trackingOverlay}
          />
        ) : null}
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

function VideoCardHeader({ match }: { match: MatchSummary }) {
  return (
    <div className="flex items-center justify-between border-b border-[#DDE9D6] px-4 py-3 sm:px-5">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">实时智能标注</p>
        <h2 className="mt-1 text-lg font-black text-[#14241B] sm:text-xl">视频回放 · {match.currentRally}</h2>
      </div>
      <div className="rounded-full border border-[#DDE9D6] bg-[#17231D] px-3 py-1 text-sm font-black text-white">
        {match.score}
      </div>
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
  videoSrc,
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
  videoSrc: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [naturalSize, setNaturalSize] = useState({ width: 1920, height: 1080 });
  const [showBoxes, setShowBoxes] = useState(true);
  const [showSkeleton, setShowSkeleton] = useState(true);
  const [showBall, setShowBall] = useState(true);

  const source = trackingOverlay?.source ?? poseOverlay?.source ?? naturalSize;
  const detectionRenderFrame = useMemo(
    () => resolveDetectionFrame(trackingOverlay?.frames ?? [], currentTime),
    [currentTime, trackingOverlay]
  );
  const poseRenderFrame = useMemo(
    () => resolvePoseFrame(poseOverlay?.frames ?? [], currentTime),
    [currentTime, poseOverlay]
  );

  const boxCount = detectionRenderFrame?.detections.length ?? 0;
  const skeletonCount = poseRenderFrame?.subjects.length ?? 0;
  const ballSamples = useMemo(() => resolveBallSamples(ballTrajectory, currentTime), [ballTrajectory, currentTime]);
  const bounceMarkers = useMemo(() => resolveBounceMarkers(bounceEvents), [bounceEvents]);
  const ballCount = ballSamples.length;
  const skeletonAvailable = Boolean(poseOverlay?.frames.length);
  const trackingStatusLabel = resolveLayerStatus(trackingOverlayLoadState, trackingOverlay?.status ?? trackingOverlayStatus);
  const poseStatusLabel = resolveLayerStatus(poseOverlayLoadState, poseOverlay?.status ?? poseOverlayStatus);
  const ballStatusLabel = resolveLayerStatus(ballTrajectoryLoadState, ballTrajectory?.status ?? ballTrajectoryStatus);
  const bounceStatusLabel = resolveLayerStatus(bounceEventsLoadState, bounceEvents?.status ?? bounceEventsStatus);
  const trackingDetail = layerDetail(trackingOverlayLoadState, trackingOverlay?.detail ?? trackingOverlayDetail, "人体框 overlay");
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
          src={videoSrc}
        />

        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          viewBox={`0 0 ${source.width} ${source.height}`}
        >
        {showBoxes && detectionRenderFrame?.detections.map((detection) => {
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
                {detection.track_id ? `ID ${detection.track_id}` : "person"} · {Math.round(detection.confidence * 100)}%
              </text>
            </g>
          );
        })}

        {showSkeleton && poseRenderFrame?.subjects.map((subject) => (
          <g key={`${subject.track_id}-${subject.bbox.join("-")}`}>
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

        {showBall && ballSamples.length ? (
          <g>
            <polyline
              fill="none"
              points={ballSamples.map((sample) => sample.image_xy?.join(",")).filter(Boolean).join(" ")}
              stroke="#D9FF3F"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={Math.max(2, source.width * 0.0018)}
              opacity="0.75"
            />
            {ballSamples.slice(-1).map((sample) => {
              if (!sample.image_xy) {
                return null;
              }
              const [x, y] = sample.image_xy;
              return (
                <circle
                  cx={x}
                  cy={y}
                  fill="#D9FF3F"
                  key={`${sample.frame_index}-${sample.timestamp_sec}`}
                  r={Math.max(5, source.width * 0.004)}
                  stroke="#071008"
                  strokeWidth={Math.max(2, source.width * 0.0016)}
                />
              );
            })}
          </g>
        ) : null}

        {showBall && bounceMarkers.map((event) => {
          const [x, y] = event.image_xy;
          return (
            <g key={event.event_id}>
              <circle
                cx={x}
                cy={y}
                fill="rgba(255,149,0,0.16)"
                r={Math.max(10, source.width * 0.008)}
                stroke="#FF9500"
                strokeDasharray="5 5"
                strokeWidth={Math.max(2, source.width * 0.0016)}
              />
              <text
                fill="#FFD7A0"
                fontSize={Math.max(13, source.width * 0.012)}
                fontWeight="800"
                paintOrder="stroke"
                stroke="rgba(0,0,0,0.75)"
                strokeWidth={Math.max(3, source.width * 0.002)}
                x={x + Math.max(8, source.width * 0.006)}
                y={y - Math.max(8, source.width * 0.006)}
              >
                弹跳候选
              </text>
            </g>
          );
        })}

        </svg>

        <div className="absolute left-4 top-4 rounded-2xl border border-white/10 bg-black/50 px-3 py-2 backdrop-blur">
        <p className="text-xs font-semibold text-slate-400">{match.teams}</p>
        <strong className="text-sm text-white">{match.venue}</strong>
        </div>

        <div className="absolute right-4 top-4 flex gap-2">
        <button
          className={`rounded-full border px-3 py-1 text-xs font-black backdrop-blur ${showBoxes ? "border-[#22C55E]/45 bg-[#22C55E]/20 text-[#D9FF3F]" : "border-white/10 bg-black/45 text-white"}`}
          onClick={() => setShowBoxes((value) => !value)}
          type="button"
        >
          人框
        </button>
        <button
          className={`rounded-full border px-3 py-1 text-xs font-black backdrop-blur ${showSkeleton ? "border-[#2F80ED]/45 bg-[#2F80ED]/25 text-[#BBD8FF]" : "border-white/10 bg-black/45 text-white"}`}
          title={skeletonAvailable ? "显示或隐藏 RTMPose 骨架" : poseDetail}
          onClick={() => setShowSkeleton((value) => !value)}
          type="button"
        >
          骨架
        </button>
        <button
          className={`rounded-full border px-3 py-1 text-xs font-black backdrop-blur ${showBall ? "border-[#D9FF3F]/45 bg-[#D9FF3F]/18 text-[#D9FF3F]" : "border-white/10 bg-black/45 text-white"}`}
          title={ballTrajectory?.samples.length ? "显示或隐藏球轨迹与弹跳候选" : ballDetail}
          onClick={() => setShowBall((value) => !value)}
          type="button"
        >
          球
        </button>
        </div>

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
                弹跳候选：{bounceMarkers.length ? `${bounceMarkers.length} 个候选 · 仅供复盘` : statusCopy(bounceStatusLabel, bounceDetail)}
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

function RealVideoFooter({
  ballTrajectory,
  ballTrajectoryDetail,
  ballTrajectoryLoadState = "idle",
  ballTrajectoryStatus,
  bounceEvents,
  bounceEventsDetail,
  bounceEventsLoadState = "idle",
  bounceEventsStatus,
  poseOverlayDetail,
  poseOverlayLoadState = "idle",
  poseOverlayStatus,
  poseOverlay,
  trackingOverlayDetail,
  trackingOverlayLoadState = "idle",
  trackingOverlayStatus,
  trackingOverlay,
}: {
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
  trackingOverlay?: TrackingOverlayArtifact | null;
  trackingOverlayDetail?: string;
  trackingOverlayLoadState?: OverlayLoadState;
  trackingOverlayStatus?: string;
}) {
  const trackingDetail = layerDetail(trackingOverlayLoadState, trackingOverlay?.detail ?? trackingOverlayDetail, "人体框 overlay");
  const poseDetail = layerDetail(poseOverlayLoadState, poseOverlay?.detail ?? poseOverlayDetail, "骨架关节 overlay");
  const ballDetail = layerDetail(ballTrajectoryLoadState, ballTrajectory?.detail ?? ballTrajectoryDetail, "球轨迹 layer");
  const bounceDetail = layerDetail(bounceEventsLoadState, bounceEvents?.detail ?? bounceEventsDetail, "弹跳候选 marker");
  const trackingStatus = resolveLayerStatus(trackingOverlayLoadState, trackingOverlay?.status ?? trackingOverlayStatus);
  const poseStatus = resolveLayerStatus(poseOverlayLoadState, poseOverlay?.status ?? poseOverlayStatus);
  const ballStatus = resolveLayerStatus(ballTrajectoryLoadState, ballTrajectory?.status ?? ballTrajectoryStatus);
  const bounceStatus = resolveLayerStatus(bounceEventsLoadState, bounceEvents?.status ?? bounceEventsStatus);
  return (
    <div className="border-t border-[#DDE9D6] bg-white/70 px-4 py-4 sm:px-5">
      <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl bg-[#F5FAF1] p-3">
          <strong className="text-[#168A34]">YOLO 人体框</strong>
          {trackingStatus ? <span className="ml-2 text-xs font-black uppercase text-slate-500">{statusLabel(trackingStatus)}</span> : null}
          <p className="mt-1 text-slate-600">{trackingDetail}</p>
        </div>
        <div className="rounded-2xl bg-[#F5FAF1] p-3">
          <strong className="text-[#1E63B6]">RTMPose 骨架</strong>
          {poseStatus ? <span className="ml-2 text-xs font-black uppercase text-slate-500">{statusLabel(poseStatus)}</span> : null}
          <p className="mt-1 text-slate-600">{poseDetail}</p>
        </div>
        <div className="rounded-2xl bg-[#F5FAF1] p-3">
          <strong className="text-[#7A8F00]">球轨迹</strong>
          {ballStatus ? <span className="ml-2 text-xs font-black uppercase text-slate-500">{statusLabel(ballStatus)}</span> : null}
          <p className="mt-1 text-slate-600">{ballDetail}</p>
        </div>
        <div className="rounded-2xl bg-[#F5FAF1] p-3">
          <strong className="text-[#A45A00]">弹跳候选</strong>
          {bounceStatus ? <span className="ml-2 text-xs font-black uppercase text-slate-500">{statusLabel(bounceStatus)}</span> : null}
          <p className="mt-1 text-slate-600">{bounceDetail}</p>
        </div>
      </div>
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

function statusLabel(status: string): string {
  if (status === "loading") {
    return "加载中";
  }
  if (status === "available") {
    return "可用";
  }
  if (status === "partial") {
    return "部分";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "skipped") {
    return "跳过";
  }
  if (status === "no_detections" || status === "no_poses" || status === "no_candidates") {
    return "无主体";
  }
  return "不可用";
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

function resolveBallSamples(ballTrajectory: BallTrajectoryArtifact | null | undefined, currentTime: number): BallTrajectoryArtifact["samples"] {
  const samples = (ballTrajectory?.samples ?? []).filter((sample) => sample.image_xy && (sample.accepted ?? true));
  if (!samples.length) {
    return [];
  }
  const currentIndex = samples.findIndex((sample) => Math.abs(sample.timestamp_sec - currentTime) <= 0.08);
  if (currentIndex >= 0) {
    return samples.slice(Math.max(0, currentIndex - 18), currentIndex + 1);
  }
  const previous = samples.filter((sample) => sample.timestamp_sec <= currentTime).slice(-18);
  return previous.length ? previous : samples.slice(0, 1);
}

function resolveBounceMarkers(bounceEvents: BounceEventsArtifact | null | undefined) {
  return (bounceEvents?.events ?? []).filter((event) => Array.isArray(event.image_xy) && event.image_xy.length >= 2);
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
