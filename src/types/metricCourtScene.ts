export type SceneCalibrationStatus = "draft" | "ready" | "degraded" | "invalidated";
export type SceneCalibrationSource = "manual" | "auto_suggested" | "manual_verified";
export type SceneHeightSource = "standard" | "measured";
export type CameraModelSource = "net_refined_virtual" | "homography_constrained_virtual";
export type MetricValidity = "metric_multiview" | "approximate_multiview" | "visualization_only" | "unavailable";

export interface SceneImagePoint {
  x: number;
  y: number;
}

export interface ScenePoint3D {
  x: number;
  y: number;
  z: number;
}

export interface NetProfileControlPoint {
  id: string;
  world: ScenePoint3D;
  image_by_view?: Record<string, SceneImagePoint>;
  provenance?: SceneCalibrationSource;
  confirmed?: boolean;
}

export interface NetProfile {
  profile_type: "standard" | "measured";
  height_source: SceneHeightSource;
  coordinate_units: "feet";
  control_points: NetProfileControlPoint[];
  sampled_top_profile: ScenePoint3D[];
  post_world_points?: ScenePoint3D[];
}

export interface SceneCameraQuality {
  court_reprojection_error_px?: number | null;
  net_reprojection_error_px?: number | null;
  holdout_reprojection_error_px?: number | null;
  ray_angle_deg?: number | null;
  height_uncertainty_ft?: number | null;
  status: "ok" | "warning" | "failed";
  rejection_reasons: string[];
}

export interface SceneCameraModel {
  source: CameraModelSource;
  projection?: number[][] | null;
  rotation?: number[][] | null;
  translation?: number[] | null;
  focal_px?: number | null;
  image_width?: number | null;
  image_height?: number | null;
}

export interface SceneViewCalibration {
  view_id: string;
  camera_id?: string | null;
  video_id?: string | null;
  calibration_id?: string | null;
  image_width?: number | null;
  image_height?: number | null;
  frame_index?: number | null;
  timestamp_seconds?: number | null;
  court_orientation?: string | null;
  net_annotations: Record<string, SceneImagePoint>;
  holdout_annotations?: Record<string, SceneImagePoint>;
  camera_model?: SceneCameraModel | null;
  quality: SceneCameraQuality;
  provenance: SceneCalibrationSource;
}

export interface MetricCourtSceneCalibration {
  schema_version: "metric_court_scene.v1";
  capture_take_id: string;
  revision: number;
  status: SceneCalibrationStatus;
  canonical_frame_id?: string | null;
  coordinate_units: "feet";
  court_width_ft: number;
  court_length_ft: number;
  net_y_ft: number;
  net_profile: NetProfile;
  holdout_control_points?: NetProfileControlPoint[];
  views: SceneViewCalibration[];
  provenance: SceneCalibrationSource;
  quality: SceneCameraQuality;
  fallback_metric_validity: MetricValidity;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
  rejection_reasons: string[];
}

export interface MetricCourtSceneDraftRequest {
  canonical_frame_id?: string | null;
  net_profile?: Partial<NetProfile> & Pick<NetProfile, "control_points">;
  holdout_control_points?: NetProfileControlPoint[];
  views: SceneViewCalibration[];
  provenance?: SceneCalibrationSource;
}

export interface MetricCourtSceneValidationResponse {
  capture_take_id: string;
  status: Exclude<SceneCalibrationStatus, "draft">;
  quality: SceneCameraQuality;
  rejection_reasons: string[];
  scene: MetricCourtSceneCalibration;
}

export interface MetricCourtSceneRevisionSummary {
  revision: number;
  status: SceneCalibrationStatus;
  provenance: SceneCalibrationSource;
  created_at: string;
  published_at?: string | null;
}

export const STANDARD_NET_HEIGHT_FT = {
  endpoint: 36 / 12,
  center: 34 / 12,
} as const;

export function buildStandardNetProfile(confirmed = false): NetProfile {
  const control_points: NetProfileControlPoint[] = [
    { id: "left", world: { x: 0, y: 22, z: STANDARD_NET_HEIGHT_FT.endpoint }, provenance: "manual", confirmed },
    { id: "center", world: { x: 10, y: 22, z: STANDARD_NET_HEIGHT_FT.center }, provenance: "manual", confirmed },
    { id: "right", world: { x: 20, y: 22, z: STANDARD_NET_HEIGHT_FT.endpoint }, provenance: "manual", confirmed },
  ];
  return {
    profile_type: "standard",
    height_source: "standard",
    coordinate_units: "feet",
    control_points,
    sampled_top_profile: [],
    post_world_points: [
      { x: -1, y: 22, z: STANDARD_NET_HEIGHT_FT.endpoint },
      { x: 21, y: 22, z: STANDARD_NET_HEIGHT_FT.endpoint },
    ],
  };
}
