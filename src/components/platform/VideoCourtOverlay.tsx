import type { CourtOverlayGeometry, Point2D } from "../../services/videoCourtOverlay";
import { pointsToSvgAttribute } from "../../services/videoCourtOverlay";

export function VideoCourtOverlay({
  courtGeometry,
  netPoints,
  sourceWidth,
}: {
  courtGeometry: CourtOverlayGeometry | null;
  netPoints: Point2D[] | null;
  sourceWidth: number;
}) {
  const strokeWidth = Math.max(2, sourceWidth * 0.0015);
  const netStrokeWidth = Math.max(3, sourceWidth * 0.0022);
  return (
    <g data-testid="video-court-net-overlay">
      {courtGeometry ? (
        <g data-testid="video-court-overlay">
          <polyline
            data-testid="video-court-boundary"
            fill="none"
            points={pointsToSvgAttribute(courtGeometry.boundary)}
            stroke="#8BFFB0"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={strokeWidth * 1.35}
          />
          {courtGeometry.lines.filter((line) => line.kind !== "boundary").map((line) => (
            <polyline
              data-testid={`video-court-line-${line.id}`}
              fill="none"
              key={line.id}
              points={pointsToSvgAttribute(line.points)}
              stroke={line.kind === "kitchen" ? "#22C55E" : "#CFFFE0"}
              strokeDasharray={line.kind === "kitchen" ? undefined : "10 6"}
              strokeLinecap="round"
              strokeWidth={strokeWidth}
            />
          ))}
        </g>
      ) : null}
      {netPoints ? (
        <g data-testid="video-net-overlay">
          <polyline
            fill="none"
            points={pointsToSvgAttribute(netPoints)}
            stroke="#FFD166"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={netStrokeWidth * 1.5}
          />
          <path
            d={`M ${netPoints[0].x} ${netPoints[0].y} Q ${netPoints[0].x} ${netPoints[0].y} ${netPoints[1].x} ${netPoints[1].y} Q ${netPoints[2].x} ${netPoints[2].y} ${netPoints[2].x} ${netPoints[2].y}`}
            fill="none"
            stroke="#FFF3C4"
            strokeDasharray="8 5"
            strokeLinecap="round"
            strokeWidth={netStrokeWidth}
          />
          {netPoints.map((point, index) => (
            <circle
              cx={point.x}
              cy={point.y}
              data-testid={`video-net-point-${index}`}
              fill="#FFF3C4"
              key={`${point.x}-${point.y}-${index}`}
              r={Math.max(4, sourceWidth * 0.003)}
              stroke="#7A4B00"
              strokeWidth={Math.max(1, sourceWidth * 0.0008)}
            />
          ))}
        </g>
      ) : null}
    </g>
  );
}
