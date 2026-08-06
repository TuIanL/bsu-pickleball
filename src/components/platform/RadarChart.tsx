import { PLAYER_SCORE_DIMENSIONS } from "../../types/report";

/** 六轴等角雷达图（纯 SVG）：中心 0、外缘 10，环形网格 + 维度标签 + 顶点分值（1 位小数）。 */

const VIEW_WIDTH = 400;
const VIEW_HEIGHT = 340;
const CENTER_X = 200;
const CENTER_Y = 165;
const RADIUS = 105;
const LABEL_RADIUS = RADIUS + 18;
const MAX_SCORE = 10;
/** 网格刻度：外缘 10 的分数环（0 为隐式中心）。 */
const GRID_LEVELS = [2, 4, 6, 8, 10];

interface RadarChartProps {
  /** 六个维度分值，顺序与 PLAYER_SCORE_DIMENSIONS 一致，取值 0–10。 */
  values: number[];
  /** 六轴标签（默认 PLAYER_SCORE_DIMENSIONS 中文名）。 */
  labels?: string[];
  /** 球员多边形填充/描边颜色（canonical 球员色）。 */
  color: string;
}

/** 由维度索引与分值算出顶点坐标（角度自顶部顺时针 60° 间隔）。 */
function polarPoint(index: number, value: number, maxScore: number, radius: number): [number, number] {
  const angle = ((-90 + index * 60) * Math.PI) / 180;
  const ratio = Math.max(0, Math.min(maxScore, value)) / maxScore;
  return [CENTER_X + ratio * radius * Math.cos(angle), CENTER_Y + ratio * radius * Math.sin(angle)];
}

export function RadarChart({ values, labels, color }: RadarChartProps) {
  const dimensionCount = PLAYER_SCORE_DIMENSIONS.length;
  const axisLabels = labels ?? PLAYER_SCORE_DIMENSIONS.map((dimension) => dimension.label);
  const safeValues = Array.from({ length: dimensionCount }, (_, i) => values[i] ?? 0);
  const vertices = safeValues.map((value, i) => polarPoint(i, value, MAX_SCORE, RADIUS));
  const polygonPoints = vertices.map((point) => point.join(",")).join(" ");

  return (
    <svg
      aria-label="球员六维雷达评分图"
      className="mx-auto block w-full max-w-[420px]"
      role="img"
      viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
    >
      {/* 环形网格（2 / 4 / 6 / 8 / 10） */}
      {GRID_LEVELS.map((level) => {
        const ring = PLAYER_SCORE_DIMENSIONS.map((_, i) => polarPoint(i, level, MAX_SCORE, RADIUS));
        return <polygon fill="none" key={`ring-${level}`} points={ring.map((point) => point.join(",")).join(" ")} stroke="#DDE9D6" strokeWidth="1" />;
      })}

      {/* 轴线 */}
      {PLAYER_SCORE_DIMENSIONS.map((_, i) => {
        const [x, y] = polarPoint(i, MAX_SCORE, MAX_SCORE, RADIUS);
        return <line key={`axis-${i}`} stroke="#DFEADA" strokeWidth="1" x1={CENTER_X} x2={x} y1={CENTER_Y} y2={y} />;
      })}

      {/* 球员多边形（canonical 球员色） */}
      <polygon fill={color} fillOpacity="0.28" points={polygonPoints} stroke={color} strokeLinejoin="round" strokeWidth="2" />

      {/* 维度标签 + 顶点分值（1 位小数） */}
      {vertices.map(([x, y], i) => {
        const label = axisLabels[i] ?? PLAYER_SCORE_DIMENSIONS[i].label;
        const [lx, ly] = polarPoint(i, MAX_SCORE, MAX_SCORE, LABEL_RADIUS);
        const anchor = lx < CENTER_X - 8 ? "end" : lx > CENTER_X + 8 ? "start" : "middle";
        return (
          <g key={`vertex-${i}`}>
            <text fill="#315640" fontSize="11" fontWeight="700" textAnchor={anchor} x={lx} y={ly + 4}>
              {label}
            </text>
            <circle cx={x} cy={y} fill={color} r="3" />
            <text fill="#14241B" fontSize="11" fontWeight="800" textAnchor="middle" x={x} y={y + 18}>
              {safeValues[i].toFixed(1)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
