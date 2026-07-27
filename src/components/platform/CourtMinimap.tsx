import { useMemo } from "react";
import type { PipelineTrackPoint } from "../../types/report";

// ── 球场几何常量（与后端 standard_court / MinimapVisualizer 保持一致） ──

const COURT_WIDTH_FT = 20;
const COURT_LENGTH_FT = 44;

/** tracking bounds（与后端 court_geometry.tracking_bounds 一致） */
const TB = {
  xMin: -4,
  xMax: 24,
  yMin: -8,
  yMax: 52,
};

/** minimap 画布尺寸（像素） */
const W = 160;
const H = 220;
const PAD = 10;

// ── 配色（与后端 MinimapStyle 对应，转为 CSS/SVG 颜色） ──

const COLOR = {
  bg: "#F6F9F4",
  courtFill: "#E2F2E0",
  line: "#224C2D",
  kitchenFill: "#D8EBF5",
  trackingFill: "#ECF4EA",
  trackingLine: "#BED2B9",
} as const;

const PLAYER_COLORS = [
  "#218A34",
  "#E05F24",
  "#BE48B2",
  "#2A80D6",
  "#505CDC",
  "#28A0A0",
] as const;

// ── 坐标映射 ──

function courtToSvg(x: number, y: number): [number, number] | null {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  if (x < TB.xMin || x > TB.xMax || y < TB.yMin || y > TB.yMax) return null;
  const drawW = W - PAD * 2;
  const drawH = H - PAD * 2;
  const px = PAD + ((x - TB.xMin) / (TB.xMax - TB.xMin)) * drawW;
  const py = PAD + ((y - TB.yMin) / (TB.yMax - TB.yMin)) * drawH;
  return [px, H - py];
}

// ── 厨房区（Non-Volley Zone）── 后端 kitchen_zones 标准位置 ──

const KITCHEN_ZONES: Array<{ points: [number, number][] }> = [
  {
    points: [
      [0, 0],
      [COURT_WIDTH_FT, 0],
      [COURT_WIDTH_FT, 7],
      [0, 7],
    ],
  },
  {
    points: [
      [0, COURT_LENGTH_FT],
      [COURT_WIDTH_FT, COURT_LENGTH_FT],
      [COURT_WIDTH_FT, COURT_LENGTH_FT - 7],
      [0, COURT_LENGTH_FT - 7],
    ],
  },
];

// ── 组件 ──

interface CourtMinimapProps {
  /** 全部轨迹点（按时间排序） */
  tracks: PipelineTrackPoint[];
  /** 当前视频播放时间（秒） */
  currentTimeSec: number;
  /** 显示的最近轨迹长度（秒），默认 6 */
  trailSeconds?: number;
  /** 容器类名 */
  className?: string;
}

export function CourtMinimap({
  tracks,
  currentTimeSec,
  trailSeconds = 6,
  className = "",
}: CourtMinimapProps) {
  const data = useMemo(() => {
    try {
      return buildMinimapData(tracks, currentTimeSec, trailSeconds);
    } catch {
      return null;
    }
  }, [tracks, currentTimeSec, trailSeconds]);

  if (!data || !Array.isArray(tracks) || tracks.length === 0) return null;

  const { players, courtPoly, kitchenPolys, trackingPoly } = data;

  return (
    <svg
      className={`rounded-lg border border-black/10 shadow-lg ${className}`}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      width={W}
    >
      <rect fill={COLOR.bg} height={H} rx={6} width={W} />

      {trackingPoly.length >= 3 && (
        <polygon
          fill={COLOR.trackingFill}
          points={trackingPoly.map((p) => p.join(",")).join(" ")}
          stroke={COLOR.trackingLine}
          strokeWidth={0.8}
        />
      )}

      {courtPoly.length >= 3 && (
        <polygon fill={COLOR.courtFill} points={courtPoly.map((p) => p.join(",")).join(" ")} />
      )}

      {kitchenPolys.map(
        (poly, i) =>
          poly.length >= 3 && (
            <polygon
              fill={COLOR.kitchenFill}
              key={`kitchen-${i}`}
              points={poly.map((p) => p.join(",")).join(" ")}
            />
          ),
      )}

      {courtPoly.length >= 3 && (
        <polygon
          fill="none"
          points={courtPoly.map((p) => p.join(",")).join(" ")}
          stroke={COLOR.line}
          strokeWidth={1.5}
        />
      )}

      {(() => {
        const midTop = courtToSvg(COURT_WIDTH_FT / 2, 0);
        const midBot = courtToSvg(COURT_WIDTH_FT / 2, COURT_LENGTH_FT);
        if (!midTop || !midBot) return null;
        return <line stroke={COLOR.line} strokeWidth={1} x1={midTop[0]} x2={midBot[0]} y1={midTop[1]} y2={midBot[1]} />;
      })()}

      {(() => {
        const netLeft = courtToSvg(0, COURT_LENGTH_FT / 2);
        const netRight = courtToSvg(COURT_WIDTH_FT, COURT_LENGTH_FT / 2);
        if (!netLeft || !netRight) return null;
        return (
          <line stroke={COLOR.line} strokeWidth={1.5} x1={netLeft[0]} x2={netRight[0]} y1={netLeft[1]} y2={netRight[1]} />
        );
      })()}

      {players.map(({ trackId, svgPts, latest }, idx) => {
        const color = PLAYER_COLORS[idx % PLAYER_COLORS.length];
        return (
          <g key={trackId}>
            {svgPts.length >= 2 && (
              <polyline
                fill="none"
                points={svgPts.map((p) => p.join(",")).join(" ")}
                stroke={color}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
              />
            )}
            {svgPts.slice(0, -1).map((p, i) => (
              <circle cx={p[0]} cy={p[1]} fill={color} key={i} r={2} />
            ))}
            {latest && (
              <>
                <circle cx={latest[0]} cy={latest[1]} fill={color} r={4.5} stroke="#071008" strokeWidth={0.8} />
                <text
                  fill="#14241B"
                  fontSize={7.5}
                  fontWeight={700}
                  paintOrder="stroke"
                  stroke="rgba(240,248,240,0.7)"
                  strokeWidth={2}
                  x={latest[0]}
                  y={latest[1] - 7}
                  textAnchor="middle"
                >
                  ID{String(trackId).slice(-2)}
                </text>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── 纯计算函数（可被 try-catch 包裹） ──

/** 最大处理的轨迹点数（超过时自动降采样） */
const MAX_TRACK_POINTS = 2000;

function buildMinimapData(
  tracks: PipelineTrackPoint[],
  currentTimeSec: number,
  trailSeconds: number,
) {
  const courtPts = [
    courtToSvg(0, 0),
    courtToSvg(COURT_WIDTH_FT, 0),
    courtToSvg(COURT_WIDTH_FT, COURT_LENGTH_FT),
    courtToSvg(0, COURT_LENGTH_FT),
  ].filter((p): p is [number, number] => p !== null);

  const kitchenPts = KITCHEN_ZONES.map((zone) =>
    zone.points.map(([x, y]) => courtToSvg(x, y)).filter((p): p is [number, number] => p !== null),
  );

  const tbPts = [
    courtToSvg(TB.xMin, TB.yMin),
    courtToSvg(TB.xMax, TB.yMin),
    courtToSvg(TB.xMax, TB.yMax),
    courtToSvg(TB.xMin, TB.yMax),
  ].filter((p): p is [number, number] => p !== null);

  const time = Number.isFinite(currentTimeSec) ? currentTimeSec : 0;
  const trail = Math.max(0, Number.isFinite(trailSeconds) ? trailSeconds : 6);
  const cutoff = time - trail;

  // 先过滤时间窗口
  let visibleTracks = tracks.filter((t) => {
    if (!t?.court_point) return false;
    const ts = t.timestamp_seconds;
    if (!Number.isFinite(ts)) return false;
    return ts <= time && ts >= cutoff;
  });

  // 降采样：如果点数过多，按固定间隔采样
  if (visibleTracks.length > MAX_TRACK_POINTS) {
    const step = visibleTracks.length / MAX_TRACK_POINTS;
    visibleTracks = visibleTracks.filter((_, i) => i % Math.round(step) < 1 || i === visibleTracks.length - 1);
  }

  const grouped = new Map<string, typeof visibleTracks>();
  for (const pt of visibleTracks) {
    const key = pt.track_id ?? "unknown";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(pt);
  }

  // 每个球员内部也限制最大点数
  const MAX_POINTS_PER_PLAYER = 300;
  const playerEntries = Array.from(grouped.entries())
    .map(([trackId, pts]) => {
      pts.sort((a, b) => (a.timestamp_seconds ?? 0) - (b.timestamp_seconds ?? 0));
      // 每个球员最多保留 N 个点
      let sampled = pts;
      if (pts.length > MAX_POINTS_PER_PLAYER) {
        const step = pts.length / MAX_POINTS_PER_PLAYER;
        sampled = pts.filter((_, i) => i % Math.round(step) < 1 || i === pts.length - 1);
      }
      const svgPts = sampled
        .map((p) => courtToSvg(p.court_point.x, p.court_point.y))
        .filter((p): p is [number, number] => p !== null);
      const latestRaw = sampled[sampled.length - 1];
      const latest =
        latestRaw?.court_point
          ? courtToSvg(latestRaw.court_point.x, latestRaw.court_point.y)
          : null;
      return { trackId, svgPts, latest };
    })
    .filter((e) => e.svgPts.length > 0);

  return {
    players: playerEntries,
    courtPoly: courtPts,
    kitchenPolys: kitchenPts,
    trackingPoly: tbPts,
  };
}
