import type { SceneImagePoint } from "./metricCourtScene";

export type CourtOrientation = "identity" | "rotate_180" | "mirror_x" | "mirror_y";

export type GeometryLayerState = "idle" | "loading" | "available" | "unavailable" | "failed";

export interface ImageSize {
  width: number;
  height: number;
}

export interface CalibrationKeypoint {
  name: string;
  image: SceneImagePoint;
  court: SceneImagePoint;
}

export interface CalibrationQuality {
  reprojection_error: number;
  status: "ok" | "warning";
}

/** 后端 GET /calibration/{calibration_id} 的完整只读响应。 */
export interface CalibrationReadResponse {
  calibration_id: string;
  video_id?: string | null;
  keypoints: CalibrationKeypoint[];
  homography: number[][];
  inverse_homography: number[][] | null;
  court_coordinate_system: {
    unit: "feet";
    width: number;
    length: number;
  };
  quality: CalibrationQuality;
  created_at: string;
}

export interface DisplayViewGeometry {
  viewId: string;
  videoId: string | null;
  calibrationId: string | null;
  orientation: CourtOrientation | null;
  sourceSize: ImageSize | null;
  calibrationImageSize: ImageSize | null;
  netImageSize: ImageSize | null;
  inverseHomography: number[][] | null;
  calibrationQuality: CalibrationQuality | null;
  netAnnotations: Record<string, SceneImagePoint>;
  courtState: GeometryLayerState;
  courtDetail: string;
  netState: GeometryLayerState;
  netDetail: string;
}
