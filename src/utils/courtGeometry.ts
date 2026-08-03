/** 球场 SVG viewBox 常量 */
export const COURT_VIEWBOX_WIDTH = 200;
export const COURT_VIEWBOX_HEIGHT = 440;
export const COURT_PADDING = 24;

/** Tracking viewBox 常量（包含 tracking buffer） */
export const TRACKING_VIEWBOX_WIDTH = 280;
export const TRACKING_VIEWBOX_HEIGHT = 600;
export const TRACKING_PADDING = 24;

/** 标准匹克球场尺寸（英尺） */
export const COURT_WIDTH_FT = 20;
export const COURT_LENGTH_FT = 44;

/** Tracking buffer 尺寸（英尺） */
export const TRACKING_X_MIN = -4;
export const TRACKING_X_MAX = 24;
export const TRACKING_Y_MIN = -8;
export const TRACKING_Y_MAX = 52;
export const TRACKING_WIDTH_FT = TRACKING_X_MAX - TRACKING_X_MIN;
export const TRACKING_LENGTH_FT = TRACKING_Y_MAX - TRACKING_Y_MIN;

/** 非截击区（厨房）从端线的距离（英尺） */
export const KITCHEN_DEPTH_FT = 7;

/** 中线位置（长度方向的一半） */
export const CENTER_LINE_Y_FT = COURT_LENGTH_FT / 2;

/** 球场物理坐标 (x_ft, y_ft) → SVG viewBox 坐标 (x, y) */
export function courtToSvg(xFt: number, yFt: number): { x: number; y: number } {
  const scaleX = (COURT_VIEWBOX_WIDTH - COURT_PADDING * 2) / COURT_WIDTH_FT;
  const scaleY = (COURT_VIEWBOX_HEIGHT - COURT_PADDING * 2) / COURT_LENGTH_FT;
  return {
    x: COURT_PADDING + xFt * scaleX,
    y: COURT_PADDING + yFt * scaleY,
  };
}

/** Tracking 坐标 (x_ft, y_ft) → SVG viewBox 坐标，支持界外点显示 */
export function trackingToSvg(xFt: number, yFt: number): { x: number; y: number } {
  const scaleX = (TRACKING_VIEWBOX_WIDTH - TRACKING_PADDING * 2) / TRACKING_WIDTH_FT;
  const scaleY = (TRACKING_VIEWBOX_HEIGHT - TRACKING_PADDING * 2) / TRACKING_LENGTH_FT;
  return {
    x: TRACKING_PADDING + (xFt - TRACKING_X_MIN) * scaleX,
    y: TRACKING_PADDING + (yFt - TRACKING_Y_MIN) * scaleY,
  };
}

/** 批量转换坐标点 */
export function pointsToSvg(points: [number, number][]): { x: number; y: number }[] {
  return points.map(([x, y]) => courtToSvg(x, y));
}

/** SVG 球场底图参数 */
export function courtSvgDefs() {
  const tl = courtToSvg(0, 0);
  const br = courtToSvg(COURT_WIDTH_FT, COURT_LENGTH_FT);
  const netLeft = courtToSvg(0, CENTER_LINE_Y_FT);
  const netRight = courtToSvg(COURT_WIDTH_FT, CENTER_LINE_Y_FT);
  const kitchenTopFar = courtToSvg(0, KITCHEN_DEPTH_FT);
  const kitchenTopNear = courtToSvg(COURT_WIDTH_FT, KITCHEN_DEPTH_FT);
  const kitchenBottomFar = courtToSvg(0, COURT_LENGTH_FT - KITCHEN_DEPTH_FT);
  const kitchenBottomNear = courtToSvg(COURT_WIDTH_FT, COURT_LENGTH_FT - KITCHEN_DEPTH_FT);

  return {
    viewBox: `0 0 ${COURT_VIEWBOX_WIDTH} ${COURT_VIEWBOX_HEIGHT}`,
    courtOutline: {
      x: tl.x,
      y: tl.y,
      width: br.x - tl.x,
      height: br.y - tl.y,
    },
    net: {
      x1: netLeft.x,
      y1: netLeft.y,
      x2: netRight.x,
      y2: netRight.y,
    },
    kitchenTop: {
      x1: kitchenTopFar.x,
      y1: kitchenTopFar.y,
      x2: kitchenTopNear.x,
      y2: kitchenTopNear.y,
    },
    kitchenBottom: {
      x1: kitchenBottomFar.x,
      y1: kitchenBottomFar.y,
      x2: kitchenBottomNear.x,
      y2: kitchenBottomNear.y,
    },
  };
}
