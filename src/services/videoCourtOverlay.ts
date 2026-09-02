import type { SceneImagePoint } from "../types/metricCourtScene";
import type { CourtOrientation, ImageSize } from "../types/videoCourtOverlay";

export const PICKLEBALL_COURT_WIDTH_FT = 20;
export const PICKLEBALL_COURT_LENGTH_FT = 44;
export const PICKLEBALL_KITCHEN_NEAR_Y_FT = 15;
export const PICKLEBALL_KITCHEN_FAR_Y_FT = 29;
export const PICKLEBALL_NET_Y_FT = 22;
/** 球网立柱通常略微超出场地边线，给人工端点保留可视余量。 */
export const NET_SIDE_MARGIN_RATIO = 0.2;

export interface Point2D {
  x: number;
  y: number;
}

export interface CourtOverlayLine {
  id: string;
  kind: "boundary" | "kitchen" | "center";
  points: Point2D[];
}

export interface CourtOverlayGeometry {
  boundary: Point2D[];
  lines: CourtOverlayLine[];
}

function isFinitePoint(point: Point2D | null | undefined): point is Point2D {
  return Boolean(point && Number.isFinite(point.x) && Number.isFinite(point.y));
}

function isValidSize(size: ImageSize | null | undefined): size is ImageSize {
  return Boolean(size && Number.isFinite(size.width) && size.width > 0 && Number.isFinite(size.height) && size.height > 0);
}

/** 将 canonical 语义坐标转换到当前机位使用的 local court 坐标。 */
export function canonicalToLocalCourtPoint(point: Point2D, orientation: CourtOrientation | null | undefined): Point2D {
  switch (orientation) {
    case "rotate_180":
      return {
        x: PICKLEBALL_COURT_WIDTH_FT - point.x,
        y: PICKLEBALL_COURT_LENGTH_FT - point.y,
      };
    case "mirror_x":
      return { x: PICKLEBALL_COURT_WIDTH_FT - point.x, y: point.y };
    case "mirror_y":
      return { x: point.x, y: PICKLEBALL_COURT_LENGTH_FT - point.y };
    case "identity":
    case null:
    case undefined:
      return point;
  }
}

function applyHomography(matrix: number[][] | null | undefined, point: Point2D): Point2D | null {
  if (!matrix || matrix.length < 3 || matrix.some((row) => row.length < 3)) return null;
  const denominator = matrix[2][0] * point.x + matrix[2][1] * point.y + matrix[2][2];
  if (!Number.isFinite(denominator) || Math.abs(denominator) < 1e-9) return null;
  const x = (matrix[0][0] * point.x + matrix[0][1] * point.y + matrix[0][2]) / denominator;
  const y = (matrix[1][0] * point.x + matrix[1][1] * point.y + matrix[1][2]) / denominator;
  return isFinitePoint({ x, y }) ? { x, y } : null;
}

function scaleImagePoint(point: Point2D, fromSize: ImageSize | null | undefined, toSize: ImageSize): Point2D {
  if (!isValidSize(fromSize) || !isValidSize(toSize)) return point;
  return {
    x: point.x * (toSize.width / fromSize.width),
    y: point.y * (toSize.height / fromSize.height),
  };
}

/** 将 local court 坐标通过 court→image 单应性映射到当前视频源像素。 */
export function projectCourtPointToImage(
  inverseHomography: number[][] | null | undefined,
  point: Point2D,
  calibrationImageSize: ImageSize | null | undefined,
  sourceSize: ImageSize,
): Point2D | null {
  const projected = applyHomography(inverseHomography, point);
  return projected ? scaleImagePoint(projected, calibrationImageSize, sourceSize) : null;
}

interface LocalCourtLine {
  id: string;
  kind: CourtOverlayLine["kind"];
  points: Point2D[];
}

const LOCAL_COURT_LINES: LocalCourtLine[] = [
  {
    id: "boundary",
    kind: "boundary",
    points: [
      { x: 0, y: 0 },
      { x: PICKLEBALL_COURT_WIDTH_FT, y: 0 },
      { x: PICKLEBALL_COURT_WIDTH_FT, y: PICKLEBALL_COURT_LENGTH_FT },
      { x: 0, y: PICKLEBALL_COURT_LENGTH_FT },
      { x: 0, y: 0 },
    ],
  },
  {
    id: "kitchen-near",
    kind: "kitchen",
    points: [
      { x: 0, y: PICKLEBALL_KITCHEN_NEAR_Y_FT },
      { x: PICKLEBALL_COURT_WIDTH_FT, y: PICKLEBALL_KITCHEN_NEAR_Y_FT },
    ],
  },
  {
    id: "kitchen-far",
    kind: "kitchen",
    points: [
      { x: 0, y: PICKLEBALL_KITCHEN_FAR_Y_FT },
      { x: PICKLEBALL_COURT_WIDTH_FT, y: PICKLEBALL_KITCHEN_FAR_Y_FT },
    ],
  },
  {
    id: "center-near",
    kind: "center",
    points: [
      { x: PICKLEBALL_COURT_WIDTH_FT / 2, y: 0 },
      { x: PICKLEBALL_COURT_WIDTH_FT / 2, y: PICKLEBALL_KITCHEN_NEAR_Y_FT },
    ],
  },
  {
    id: "center-far",
    kind: "center",
    points: [
      { x: PICKLEBALL_COURT_WIDTH_FT / 2, y: PICKLEBALL_KITCHEN_FAR_Y_FT },
      { x: PICKLEBALL_COURT_WIDTH_FT / 2, y: PICKLEBALL_COURT_LENGTH_FT },
    ],
  },
];

/** 构建固定机位下的球场线。这里输入必须是 local court 坐标，不重复套用 orientation。 */
export function buildCourtOverlayGeometry(
  inverseHomography: number[][] | null | undefined,
  calibrationImageSize: ImageSize | null | undefined,
  sourceSize: ImageSize,
): CourtOverlayGeometry | null {
  if (!isValidSize(sourceSize)) return null;
  const lines: CourtOverlayLine[] = [];
  for (const line of LOCAL_COURT_LINES) {
    const projected = line.points.map((point) =>
      projectCourtPointToImage(inverseHomography, point, calibrationImageSize, sourceSize),
    );
    if (projected.some((point) => !isFinitePoint(point))) return null;
    lines.push({ id: line.id, kind: line.kind, points: projected as Point2D[] });
  }
  return {
    boundary: lines[0].points,
    lines,
  };
}

/** 球网点属于 image-space 标注，只做尺寸缩放，不再应用 courtOrientation。 */
export function buildNetOverlayPoints(
  annotations: Record<string, SceneImagePoint> | null | undefined,
  annotationImageSize: ImageSize | null | undefined,
  sourceSize: ImageSize,
): Point2D[] | null {
  if (!annotations || !isValidSize(sourceSize)) return null;
  const points = [annotations.left, annotations.center, annotations.right];
  if (points.some((point) => !isFinitePoint(point))) return null;
  return points.map((point) => scaleImagePoint(point, annotationImageSize, sourceSize));
}

function interpolateXAtY(start: Point2D, end: Point2D, y: number): number | null {
  const minY = Math.min(start.y, end.y);
  const maxY = Math.max(start.y, end.y);
  if (y < minY || y > maxY || Math.abs(end.y - start.y) < 1e-9) return null;
  const ratio = (y - start.y) / (end.y - start.y);
  return start.x + (end.x - start.x) * ratio;
}

/**
 * 球网顶线是人工 image-space 标注，但可见球网不应越过当前 view 的球场两侧。
 * 用同一 homography 得到的左右边界做裁剪，避免标注点偏宽时把网线画到场地外。
 */
export function clipNetOverlayPointsToCourt(
  points: Point2D[] | null,
  courtGeometry: CourtOverlayGeometry | null,
  sideMarginRatio = NET_SIDE_MARGIN_RATIO,
): Point2D[] | null {
  if (!points || points.length < 3 || !courtGeometry || courtGeometry.boundary.length < 4) return points;
  const [topLeft, topRight, bottomRight, bottomLeft] = courtGeometry.boundary;
  return points.map((point) => {
    const leftX = interpolateXAtY(topLeft, bottomLeft, point.y);
    const rightX = interpolateXAtY(topRight, bottomRight, point.y);
    if (leftX === null || rightX === null) return point;
    const courtLeft = Math.min(leftX, rightX);
    const courtRight = Math.max(leftX, rightX);
    const sideMargin = (courtRight - courtLeft) * Math.max(0, sideMarginRatio);
    return {
      ...point,
      x: Math.min(Math.max(point.x, courtLeft - sideMargin), courtRight + sideMargin),
    };
  });
}

export function pointsToSvgAttribute(points: Point2D[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}
