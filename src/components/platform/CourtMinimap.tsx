import { useMemo } from "react";
import type { BallTrajectoryArtifact, BounceEventsArtifact, FusedPlayerOverlayFrame, PipelineTrackPoint } from "../../types/report";
import { buildVideoOverlayHud, type HudPoint } from "../../services/videoOverlayHud";

const COURT_WIDTH_FT = 20;
const COURT_LENGTH_FT = 44;
const TRACKING_BOUNDS = { xMin: -4, xMax: 24, yMin: -8, yMax: 52 };
const VIEW_WIDTH = 180;
const VIEW_HEIGHT = 330;
const PADDING = 12;
const PLAYER_COLORS = ["#38BDF8", "#FBBF24", "#F472B6", "#A78BFA"] as const;

interface CourtMinimapProps {
  tracks?: PipelineTrackPoint[];
  ballTrajectory?: BallTrajectoryArtifact | null;
  bounceEvents?: BounceEventsArtifact | null;
  currentTimeSec: number;
  trailSeconds?: number;
  showBallPoint?: boolean;
  showBallPath?: boolean;
  showBounces?: boolean;
  className?: string;
  /** joint 模式展示权威：fused overlay 逐帧实体，携带 bootstrap 回填真实观测，消除启动窗口小地图空白 */
  overlayFrames?: FusedPlayerOverlayFrame[];
}

interface PointMapper {
  scale: number;
  toSvg: (x: number, y: number) => [number, number] | null;
}

function createMapper(): PointMapper {
  const spanX = TRACKING_BOUNDS.xMax - TRACKING_BOUNDS.xMin;
  const spanY = TRACKING_BOUNDS.yMax - TRACKING_BOUNDS.yMin;
  const scale = Math.min((VIEW_WIDTH - PADDING * 2) / spanX, (VIEW_HEIGHT - PADDING * 2) / spanY);
  const offsetX = (VIEW_WIDTH - spanX * scale) / 2;
  const offsetY = (VIEW_HEIGHT - spanY * scale) / 2;

  return {
    scale,
    toSvg: (x, y) => {
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      if (x < TRACKING_BOUNDS.xMin || x > TRACKING_BOUNDS.xMax || y < TRACKING_BOUNDS.yMin || y > TRACKING_BOUNDS.yMax) return null;
      return [
        offsetX + (x - TRACKING_BOUNDS.xMin) * scale,
        offsetY + (y - TRACKING_BOUNDS.yMin) * scale,
      ];
    },
  };
}

function pointsAttribute(points: Array<[number, number]>): string {
  return points.map((point) => point.join(",")).join(" ");
}

function mappedPoint(mapper: PointMapper, point: HudPoint): [number, number] | null {
  return mapper.toSvg(point.x, point.y);
}

function formatSpeed(speedMetersPerSecond: number | null): string {
  return speedMetersPerSecond === null ? "--" : `${speedMetersPerSecond.toFixed(1)} m/s`;
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  const remainder = Math.floor(Math.max(0, seconds) % 60);
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function CourtMinimap({
  tracks = [],
  ballTrajectory,
  bounceEvents,
  currentTimeSec,
  trailSeconds = 3,
  showBallPoint = true,
  showBallPath = true,
  showBounces = true,
  className = "",
  overlayFrames = [],
}: CourtMinimapProps) {
  const mapper = useMemo(() => createMapper(), []);
  const hud = useMemo(
    () => buildVideoOverlayHud(tracks, ballTrajectory, bounceEvents, currentTimeSec, { playerTrailSeconds: trailSeconds, overlayFrames }),
    [ballTrajectory, bounceEvents, currentTimeSec, tracks, trailSeconds, overlayFrames],
  );

  const courtPolygon = useMemo(() => [
    mapper.toSvg(0, 0),
    mapper.toSvg(COURT_WIDTH_FT, 0),
    mapper.toSvg(COURT_WIDTH_FT, COURT_LENGTH_FT),
    mapper.toSvg(0, COURT_LENGTH_FT),
  ].filter((point): point is [number, number] => point !== null), [mapper]);
  const trackingPolygon = useMemo(() => [
    mapper.toSvg(TRACKING_BOUNDS.xMin, TRACKING_BOUNDS.yMin),
    mapper.toSvg(TRACKING_BOUNDS.xMax, TRACKING_BOUNDS.yMin),
    mapper.toSvg(TRACKING_BOUNDS.xMax, TRACKING_BOUNDS.yMax),
    mapper.toSvg(TRACKING_BOUNDS.xMin, TRACKING_BOUNDS.yMax),
  ].filter((point): point is [number, number] => point !== null), [mapper]);
  const kitchenPolygons = useMemo(() => [
    [[0, COURT_LENGTH_FT / 2 - 7], [COURT_WIDTH_FT, COURT_LENGTH_FT / 2 - 7], [COURT_WIDTH_FT, COURT_LENGTH_FT / 2], [0, COURT_LENGTH_FT / 2]],
    [[0, COURT_LENGTH_FT / 2], [COURT_WIDTH_FT, COURT_LENGTH_FT / 2], [COURT_WIDTH_FT, COURT_LENGTH_FT / 2 + 7], [0, COURT_LENGTH_FT / 2 + 7]],
  ].map((zone) => zone.map(([x, y]) => mapper.toSvg(x, y)).filter((point): point is [number, number] => point !== null)), [mapper]);
  const netStart = mapper.toSvg(0, COURT_LENGTH_FT / 2);
  const netEnd = mapper.toSvg(COURT_WIDTH_FT, COURT_LENGTH_FT / 2);
  const centreTop = mapper.toSvg(COURT_WIDTH_FT / 2, 0);
  const centreBottom = mapper.toSvg(COURT_WIDTH_FT / 2, COURT_LENGTH_FT);
  const hasData = hud.visiblePlayerCount > 0 || hud.ballPointCount > 0 || hud.bounces.length > 0;

  if (!hasData) return null;

  return (
    <section
      aria-label="球场移动与球路 HUD"
      className={`w-[7.25rem] overflow-hidden rounded-lg border border-white/20 bg-[#07131B]/88 shadow-[0_14px_36px_rgba(0,0,0,0.36)] backdrop-blur-md sm:w-36 ${className}`}
      data-testid="court-minimap-hud"
    >
      <div className="flex items-center justify-between border-b border-white/10 px-2.5 py-2 text-[0.58rem] font-bold tracking-wide text-slate-300">
        <span className="text-[#D9FF3F]">COURT HUD</span>
        <span>{formatTime(currentTimeSec)}</span>
      </div>
      <svg className="block h-auto w-full" role="img" viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}>
        <defs>
          <filter id="court-hud-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur result="blur" stdDeviation="2.2" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect fill="#07131B" height={VIEW_HEIGHT} width={VIEW_WIDTH} />
        {trackingPolygon.length === 4 ? (
          <polygon data-testid="tracking-boundary" fill="rgba(148,163,184,0.08)" points={pointsAttribute(trackingPolygon)} stroke="rgba(148,163,184,0.22)" strokeDasharray="3 4" strokeWidth="0.8" />
        ) : null}
        {courtPolygon.length === 4 ? <polygon fill="#16314B" points={pointsAttribute(courtPolygon)} /> : null}
        {kitchenPolygons.map((polygon, index) => (
          polygon.length === 4 ? <polygon fill="rgba(56,189,248,0.15)" key={index} points={pointsAttribute(polygon)} /> : null
        ))}
        {courtPolygon.length === 4 ? <polygon data-testid="court-boundary" fill="none" points={pointsAttribute(courtPolygon)} stroke="#D7FBE4" strokeWidth="1.5" /> : null}
        {centreTop && centreBottom ? <line stroke="rgba(215,251,228,0.76)" strokeWidth="1" x1={centreTop[0]} x2={centreBottom[0]} y1={centreTop[1]} y2={centreBottom[1]} /> : null}
        {netStart && netEnd ? <line stroke="#F8FAFC" strokeWidth="2" x1={netStart[0]} x2={netEnd[0]} y1={netStart[1]} y2={netEnd[1]} /> : null}

        {hud.players.map((player, playerIndex) => {
          const color = PLAYER_COLORS[playerIndex % PLAYER_COLORS.length];
          const latest = player.latest ? mappedPoint(mapper, player.latest) : null;
          return (
            <g key={player.id} opacity={player.stale ? 0.45 : 1} style={{ color }}>
              {player.segments.map((segment, segmentIndex) => {
                const points = segment.map((point) => mappedPoint(mapper, point)).filter((point): point is [number, number] => point !== null);
                return points.length > 1 ? <polyline fill="none" key={segmentIndex} points={pointsAttribute(points)} stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" /> : null;
              })}
              {latest ? (
                <>
                  {!player.stale ? <circle cx={latest[0]} cy={latest[1]} fill={color} filter="url(#court-hud-glow)" opacity="0.32" r="10" /> : null}
                  <circle cx={latest[0]} cy={latest[1]} fill={color} r="4.5" stroke="#07131B" strokeDasharray={player.stale ? "2 1.5" : undefined} strokeWidth="1.4" />
                  <text fill="#F8FAFC" fontSize="7.4" fontWeight="800" paintOrder="stroke" stroke="#07131B" strokeWidth="2.4" textAnchor="middle" x={latest[0]} y={latest[1] - 8}>{player.label}{player.stale ? "?" : ""}</text>
                </>
              ) : null}
            </g>
          );
        })}

        {showBallPath ? hud.ballSegments.map((segment, segmentIndex) => segment.slice(1).map((point, index) => {
          const previous = mappedPoint(mapper, segment[index]);
          const current = mappedPoint(mapper, point);
          if (!previous || !current) return null;
          return <line key={`${segmentIndex}-${point.timestampSeconds}`} stroke={point.interpolated ? "rgba(217,255,63,0.48)" : "#D9FF3F"} strokeDasharray={point.interpolated ? "3 3" : undefined} strokeLinecap="round" strokeWidth="2.2" x1={previous[0]} x2={current[0]} y1={previous[1]} y2={current[1]} />;
        })) : null}
        {showBallPoint && hud.ballLatest ? (() => {
          const latest = mappedPoint(mapper, hud.ballLatest);
          return latest ? <g data-testid="hud-ball-current" filter="url(#court-hud-glow)"><circle cx={latest[0]} cy={latest[1]} fill="none" r="7" stroke="#D9FF3F" strokeWidth="1.2" /><circle cx={latest[0]} cy={latest[1]} fill="#F8FAFC" r="3.3" stroke="#D9FF3F" strokeWidth="2" /></g> : null;
        })() : null}
        {showBounces ? hud.bounces.map((bounce) => {
          const point = mappedPoint(mapper, bounce.point);
          return point ? <g data-testid="hud-bounce" key={bounce.id} opacity={bounce.active ? 1 : 0.38} transform={`translate(${point[0]} ${point[1]})`}><path d="M0,-5 L5,0 L0,5 L-5,0 Z" fill="none" stroke="#FB923C" strokeWidth={bounce.active ? "2" : "1.2"} /><circle fill="#FB923C" r="1.5" /></g> : null;
        }) : null}
        <text fill="rgba(226,232,240,0.58)" fontSize="5.8" fontWeight="700" x="12" y={(netStart?.[1] ?? 0) - 4}>NET</text>
      </svg>
      <div className="grid grid-cols-2 gap-x-2 border-t border-white/10 px-2.5 py-2 text-[0.57rem] font-semibold text-slate-300">
        <span>球员 {hud.visiblePlayerCount}</span>
        <span className="text-right text-[#D9FF3F]">球 {hud.ballLatest ? "LIVE" : "--"}</span>
        {hud.players.slice(0, 2).map((player) => <span className="col-span-1 mt-1 text-slate-400" key={player.id}>{player.label} {player.stale ? "丢失" : formatSpeed(player.speedMetersPerSecond)}</span>)}
        <span className="col-span-1 mt-1 text-right text-slate-400">弹跳 {hud.bounces.length}</span>
      </div>
    </section>
  );
}
