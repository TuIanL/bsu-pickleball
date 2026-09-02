import { useEffect, useMemo, useState } from "react";
import { getCalibration, getMetricCourtSceneRevision } from "../services/analysisClient";
import type { MetricCourtSceneCalibration, SceneViewCalibration } from "../types/metricCourtScene";
import type {
  CalibrationReadResponse,
  CourtOrientation,
  DisplayViewGeometry,
  GeometryLayerState,
  ImageSize,
} from "../types/videoCourtOverlay";

export interface DisplayViewGeometryInput {
  viewId: string;
  videoId?: string | null;
  calibrationId?: string | null;
  imageWidth?: number | null;
  imageHeight?: number | null;
  courtOrientation?: CourtOrientation | null;
}

interface UseDisplayViewGeometryOptions {
  captureTakeId?: string | null;
  sceneCalibrationRevision?: number | null;
  inputs: DisplayViewGeometryInput[];
}

interface CalibrationResult {
  value: CalibrationReadResponse | null;
  error: unknown | null;
}

interface SceneResult {
  value: MetricCourtSceneCalibration | null;
  error: unknown | null;
}

function validSize(width?: number | null, height?: number | null): ImageSize | null {
  return Number.isFinite(width) && Number.isFinite(height) && (width ?? 0) > 0 && (height ?? 0) > 0
    ? { width: width as number, height: height as number }
    : null;
}

function validMatrix(matrix: number[][] | null | undefined): matrix is number[][] {
  return Boolean(
    matrix &&
      matrix.length >= 3 &&
      matrix.slice(0, 3).every((row) => row.length >= 3 && row.slice(0, 3).every((value) => Number.isFinite(value))),
  );
}

function validPoint(point: unknown): point is { x: number; y: number } {
  if (!point || typeof point !== "object") return false;
  const candidate = point as { x?: unknown; y?: unknown };
  return typeof candidate.x === "number" && Number.isFinite(candidate.x) && typeof candidate.y === "number" && Number.isFinite(candidate.y);
}

function errorDetail(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "几何资产读取失败";
}

function buildLoadingGeometry(input: DisplayViewGeometryInput): DisplayViewGeometry {
  return {
    viewId: input.viewId,
    videoId: input.videoId ?? null,
    calibrationId: input.calibrationId ?? null,
    orientation: input.courtOrientation ?? null,
    sourceSize: validSize(input.imageWidth, input.imageHeight),
    calibrationImageSize: validSize(input.imageWidth, input.imageHeight),
    netImageSize: validSize(input.imageWidth, input.imageHeight),
    inverseHomography: null,
    calibrationQuality: null,
    netAnnotations: {},
    courtState: input.calibrationId ? "loading" : "unavailable",
    courtDetail: input.calibrationId ? "正在读取场地标定" : "当前机位没有场地标定",
    netState: "loading",
    netDetail: "正在读取球网场景标定",
  };
}

function buildGeometry(
  input: DisplayViewGeometryInput,
  calibrationResult: CalibrationResult,
  sceneResult: SceneResult,
): DisplayViewGeometry {
  const sceneView: SceneViewCalibration | undefined = sceneResult.value?.views.find(
    (view) => view.view_id === input.viewId,
  );
  const calibration = calibrationResult.value;
  const sceneSize = validSize(sceneView?.image_width, sceneView?.image_height);
  const inputSize = validSize(input.imageWidth, input.imageHeight);
  const calibrationImageSize = inputSize ?? sceneSize;
  const sourceSize = inputSize ?? sceneSize;

  let courtState: GeometryLayerState = "unavailable";
  let courtDetail = "当前机位没有场地标定";
  if (input.calibrationId && calibrationResult.error) {
    courtState = "failed";
    courtDetail = errorDetail(calibrationResult.error);
  } else if (input.calibrationId && calibration && validMatrix(calibration.inverse_homography)) {
    courtState = "available";
    courtDetail = calibration.quality.status === "warning"
      ? `场地标定可用，重投影误差 ${calibration.quality.reprojection_error.toFixed(1)} px`
      : "场地标定可用";
  } else if (input.calibrationId) {
    courtState = "failed";
    courtDetail = "场地标定缺少有效逆单应矩阵";
  }

  const netAnnotations = sceneView?.net_annotations ?? {};
  const requiredNetPoints = [netAnnotations.left, netAnnotations.center, netAnnotations.right];
  let netState: GeometryLayerState = "unavailable";
  let netDetail = "当前任务没有可用的球网三点标定";
  if (sceneResult.error) {
    netState = "failed";
    netDetail = errorDetail(sceneResult.error);
  } else if (!sceneResult.value) {
    netDetail = "当前任务没有引用的场景标定 revision";
  } else if (!sceneView) {
    netDetail = "场景标定中没有当前机位";
  } else if (sceneResult.value.status === "invalidated") {
    netDetail = "场景标定 revision 已失效";
  } else if (!requiredNetPoints.every(validPoint)) {
    netDetail = "球网缺少左端、中心或右端人工标注";
  } else if (sceneView.quality.status === "failed") {
    netDetail = sceneView.quality.rejection_reasons[0] ?? "球网场景标定质量不可用";
  } else {
    netState = "available";
    netDetail = sceneView.quality.status === "warning" || sceneResult.value.status === "degraded"
      ? "球网标定可用，但质量为降级状态"
      : "球网标定可用";
  }

  return {
    viewId: input.viewId,
    videoId: input.videoId ?? null,
    calibrationId: input.calibrationId ?? null,
    orientation: input.courtOrientation ?? null,
    sourceSize,
    calibrationImageSize,
    netImageSize: sceneSize ?? inputSize,
    inverseHomography: validMatrix(calibration?.inverse_homography) ? calibration.inverse_homography : null,
    calibrationQuality: calibration?.quality ?? null,
    netAnnotations,
    courtState,
    courtDetail,
    netState,
    netDetail,
  };
}

/**
 * 为当前任务构建逐机位几何资产缓存。
 * 所有网络请求只发生在 job/view 输入变化时，不进入视频帧回调。
 */
export function useDisplayViewGeometry({
  captureTakeId,
  sceneCalibrationRevision,
  inputs,
}: UseDisplayViewGeometryOptions): Record<string, DisplayViewGeometry> {
  const inputSignature = JSON.stringify(inputs);
  const stableInputs = useMemo(() => JSON.parse(inputSignature) as DisplayViewGeometryInput[], [inputSignature]);
  const [geometryByViewId, setGeometryByViewId] = useState<Record<string, DisplayViewGeometry>>({});

  useEffect(() => {
    let cancelled = false;
    const uniqueInputs = stableInputs.filter(
      (input, index, all) => all.findIndex((candidate) => candidate.viewId === input.viewId) === index,
    );
    const initialGeometry = Object.fromEntries(uniqueInputs.map((input) => [input.viewId, buildLoadingGeometry(input)]));
    const initialGeometryTimer = window.setTimeout(() => {
      if (!cancelled) setGeometryByViewId(initialGeometry);
    }, 0);

    if (!uniqueInputs.length) return () => {
      cancelled = true;
      window.clearTimeout(initialGeometryTimer);
    };

    const calibrationIds = [...new Set(uniqueInputs.map((input) => input.calibrationId).filter((id): id is string => Boolean(id)))];
    const calibrationPromises = new Map<string, Promise<CalibrationReadResponse>>();
    calibrationIds.forEach((calibrationId) => {
      calibrationPromises.set(calibrationId, getCalibration(calibrationId));
    });

    const scenePromise = captureTakeId && Number.isInteger(sceneCalibrationRevision) && (sceneCalibrationRevision ?? 0) > 0
      ? getMetricCourtSceneRevision(captureTakeId, sceneCalibrationRevision as number)
      : null;

    void (async () => {
      const [sceneOutcome, calibrationOutcomes] = await Promise.all([
        scenePromise ? Promise.allSettled([scenePromise]).then(([result]) => result) : Promise.resolve(null),
        Promise.all(
          calibrationIds.map(async (calibrationId) => {
            const result = await Promise.allSettled([calibrationPromises.get(calibrationId) as Promise<CalibrationReadResponse>]);
            return [calibrationId, result[0]] as const;
          }),
        ),
      ]);
      if (cancelled) return;

      const sceneResult: SceneResult = sceneOutcome?.status === "fulfilled"
        ? { value: sceneOutcome.value, error: null }
        : sceneOutcome?.status === "rejected"
          ? { value: null, error: sceneOutcome.reason }
          : { value: null, error: null };
      const calibrationResults = new Map<string, CalibrationResult>();
      calibrationOutcomes.forEach(([calibrationId, outcome]) => {
        calibrationResults.set(
          calibrationId,
          outcome.status === "fulfilled"
            ? { value: outcome.value, error: null }
            : { value: null, error: outcome.reason },
        );
      });

      const nextGeometry = Object.fromEntries(
        uniqueInputs.map((input) => [
          input.viewId,
          buildGeometry(input, calibrationResults.get(input.calibrationId ?? "") ?? { value: null, error: null }, sceneResult),
        ]),
      );
      setGeometryByViewId(nextGeometry);
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(initialGeometryTimer);
    };
  }, [captureTakeId, sceneCalibrationRevision, stableInputs]);

  return geometryByViewId;
}
