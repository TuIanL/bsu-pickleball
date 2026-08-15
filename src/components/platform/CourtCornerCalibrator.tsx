import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Info } from "lucide-react";
import type { AutomaticCalibrationResponse } from "../../types/report";
import type { AnalysisApiError } from "../../services/analysisClient";
import { DiagnosticNoticeCard } from "../DiagnosticNoticeCard";
import {
  acceptAutomaticCalibration,
  createManualCalibration,
  requestAutomaticCalibration,
  resolveAnalysisAssetUrl,
  isAnalysisApiError,
} from "../../services/analysisClient";
import { automaticCalibrationNotice } from "../../services/analysisDiagnostics";
import { errorToNotice } from "../../utils/analysisHelpers";

// ── Types ───────────────────────────────────────────────────────────────────

const calibrationPointOrder = [
  { id: "top_left", label: "远端左角" },
  { id: "top_right", label: "远端右角" },
  { id: "bottom_right", label: "近端右角" },
  { id: "bottom_left", label: "近端左角" },
] as const;

export type CalibrationPointDraft = {
  id: (typeof calibrationPointOrder)[number]["id"];
  label: string;
  viewX: number;
  viewY: number;
  x: number;
  y: number;
};

type CalibrationPointId = CalibrationPointDraft["id"];

const calibrationEdges: { id: string; corners: [CalibrationPointId, CalibrationPointId] }[] = [
  { id: "top", corners: ["top_left", "top_right"] },
  { id: "right", corners: ["top_right", "bottom_right"] },
  { id: "bottom", corners: ["bottom_right", "bottom_left"] },
  { id: "left", corners: ["bottom_left", "top_left"] },
];

/** 自动标定抽帧位置：靠近开头固定位置（秒）。前后端统一。 */
const CALIBRATION_FRAME_SECONDS = 0.5;

/**
 * 校验四点标定的近端/远端底线 Y 顺序是否合理。
 * 正常标定下近端底线位于画面下方（图像 y 更大）。
 * 返回 true 表示顺序合理（或数据不足以判断），false 表示疑似颠倒/差值过小。
 */
export function isBaselineOrderPlausible(
  points: CalibrationPointDraft[],
  frameHeight: number,
): boolean {
  const far = points.filter((point) => point.id === "top_left" || point.id === "top_right");
  const near = points.filter((point) => point.id === "bottom_left" || point.id === "bottom_right");
  if (far.length !== 2 || near.length !== 2) {
    return true;
  }
  const farAvgY = (far[0].y + far[1].y) / 2;
  const nearAvgY = (near[0].y + near[1].y) / 2;
  if (!Number.isFinite(farAvgY) || !Number.isFinite(nearAvgY)) {
    return true;
  }
  const threshold = Number.isFinite(frameHeight) && frameHeight > 0 ? frameHeight * 0.1 : 20;
  return nearAvgY - farAvgY >= threshold;
}

export interface CourtCornerCalibratorProps {
  /** 视频流 URL（用于预览和标定） */
  videoSrc: string;
  /** 已注册的视频 ID（用于调用后端标定 API） */
  videoId: string;
  /** 视频尚未注册时，用于惰性上传/注册并返回 videoId（上传流程使用） */
  ensureVideoId?: () => Promise<string>;
  /** 标定完成后回调，返回 calibrationId + 四个点的坐标 */
  onComplete: (calibrationId: string, points: CalibrationPointDraft[]) => void;
  /** 返回向导上一步或退出当前流程的文案 */
  cancelLabel?: string;
  /** 重新进入该机位时恢复的点位草稿 */
  initialPoints?: CalibrationPointDraft[];
  /** 取消回调 */
  onCancel?: () => void;
  /** 是否正在提交（禁用按钮） */
  isSubmitting?: boolean;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

const isProbablyBlankFrame = (context: CanvasRenderingContext2D, width: number, height: number) => {
  const data = context.getImageData(0, 0, width, height).data;
  const pixelCount = width * height;
  const sampleStep = Math.max(1, Math.floor(pixelCount / 1800));
  let samples = 0;
  let darkSamples = 0;
  let luminanceSum = 0;

  for (let pixel = 0; pixel < pixelCount; pixel += sampleStep) {
    const offset = pixel * 4;
    const luminance = data[offset] * 0.2126 + data[offset + 1] * 0.7152 + data[offset + 2] * 0.0722;
    luminanceSum += luminance;
    samples += 1;
    if (luminance < 16) {
      darkSamples += 1;
    }
  }

  return samples > 0 && luminanceSum / samples < 14 && darkSamples / samples > 0.94;
};

/** 居中默认四边形（人工标定兜底时的起始矩形）。 */
export function buildDefaultQuadPoints(width: number, height: number): CalibrationPointDraft[] {
  const w = width > 0 ? width : 1280;
  const h = height > 0 ? height : 720;
  const marginX = 0.22;
  const marginY = 0.18;
  const coords: Record<CalibrationPointId, [number, number]> = {
    top_left: [w * marginX, h * marginY],
    top_right: [w * (1 - marginX), h * marginY],
    bottom_right: [w * (1 - marginX), h * (1 - marginY)],
    bottom_left: [w * marginX, h * (1 - marginY)],
  };
  return calibrationPointOrder.map((point) => {
    const [x, y] = coords[point.id];
    return {
      id: point.id,
      label: point.label,
      x: Math.round(x),
      y: Math.round(y),
      viewX: (x / w) * 100,
      viewY: (y / h) * 100,
    };
  });
}

// ── Component ───────────────────────────────────────────────────────────────

export function CourtCornerCalibrator({
  videoSrc,
  videoId,
  ensureVideoId,
  onComplete,
  onCancel,
  cancelLabel = "取消",
  initialPoints,
  isSubmitting = false,
}: CourtCornerCalibratorProps) {
  const calibrationVideoRef = useRef<HTMLVideoElement | null>(null);
  const calibrationCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const calibrationAutoSeekAttemptsRef = useRef(0);
  const calibrationAutoSeekEnabledRef = useRef(false);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const autoTriggeredRef = useRef(false);
  const dragRef = useRef<{
    cornerIds: CalibrationPointId[];
    lastX: number;
    lastY: number;
  } | null>(null);

  const [calibrationPoints, setCalibrationPoints] = useState<CalibrationPointDraft[]>(() => initialPoints ? [...initialPoints] : []);
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null);
  const [calibrationFrameStatus, setCalibrationFrameStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [calibrationFrameError, setCalibrationFrameError] = useState<string | null>(null);
  const [calibrationFramePreviewUrl, setCalibrationFramePreviewUrl] = useState<string | null>(null);

  const [automaticCalibration, setAutomaticCalibration] = useState<AutomaticCalibrationResponse | null>(null);
  const [automaticCalibrationStatus, setAutomaticCalibrationStatus] = useState<"idle" | "uploading" | "detecting" | "ready" | "unavailable" | "rejected" | "error">("idle");
  const [automaticCalibrationError, setAutomaticCalibrationError] = useState<AnalysisApiError | null>(null);
  const [error, setError] = useState<{ title: string; body: string } | null>(null);
  /** 开发诊断区（就绪提示 + 指标 + 预览）是否展开，默认折叠，不持久化 */
  const [showCalibrationDetails, setShowCalibrationDetails] = useState(false);

  const calibrationComplete = calibrationPoints.length === calibrationPointOrder.length;
  const calibrationFrameReady = calibrationFrameStatus === "ready";
  const automaticPreviewUrl = resolveAnalysisAssetUrl(automaticCalibration?.preview_image_url);
  const manualMode = automaticCalibrationStatus === "rejected" || automaticCalibrationStatus === "unavailable" || automaticCalibrationStatus === "error";
  /** 是否存在开发诊断数据（决定标题旁 Info 图标是否渲染；无数据时图标隐藏） */
  const hasCalibrationDiagnostics = automaticCalibration != null || automaticCalibrationError != null;

  // ── Video frame capture ──────────────────────────────────────────────────

  const captureCalibrationFrame = () => {
    const video = calibrationVideoRef.current;
    if (!video || video.readyState < 2) return;

    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) {
      setCalibrationFrameStatus("ready");
      return;
    }

    setNaturalSize({ width, height });

    try {
      const canvas = calibrationCanvasRef.current ?? document.createElement("canvas");
      calibrationCanvasRef.current = canvas;
      const scale = Math.min(1, 1280 / width);
      canvas.width = Math.max(1, Math.round(width * scale));
      canvas.height = Math.max(1, Math.round(height * scale));

      const context = canvas.getContext("2d");
      if (!context) {
        setCalibrationFrameStatus("ready");
        return;
      }

      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      if (
        calibrationAutoSeekEnabledRef.current &&
        calibrationAutoSeekAttemptsRef.current < 6 &&
        Number.isFinite(video.duration) &&
        video.currentTime < video.duration - 0.75 &&
        isProbablyBlankFrame(context, canvas.width, canvas.height)
      ) {
        calibrationAutoSeekAttemptsRef.current += 1;
        seekCalibrationVideo(video.currentTime + Math.min(Math.max(video.duration * 0.05, 0.75), 2));
        return;
      }

      calibrationAutoSeekEnabledRef.current = false;
      setCalibrationFramePreviewUrl(canvas.toDataURL("image/jpeg", 0.88));
      setCalibrationFrameStatus("ready");
    } catch {
      setCalibrationFrameStatus("ready");
    }
  };

  const seekCalibrationVideo = (targetSeconds?: number) => {
    const video = calibrationVideoRef.current;
    if (!video) return;

    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    if (duration <= 0) {
      if (video.readyState >= 2) {
        captureCalibrationFrame();
      } else {
        setCalibrationFrameStatus("loading");
      }
      return;
    }

    // 靠近开头固定位置抽帧，避免跳到大视频深处导致等待过久
    const defaultTarget = Math.min(CALIBRATION_FRAME_SECONDS, Math.max(duration - 0.05, 0));
    const nextTime = Math.min(Math.max(targetSeconds ?? defaultTarget, 0), Math.max(duration - 0.05, 0));
    setCalibrationFrameStatus("loading");
    setCalibrationFrameError(null);
    setCalibrationFramePreviewUrl(null);
    video.pause();
    if (Math.abs(video.currentTime - nextTime) < 0.03 && video.readyState >= 2) {
      captureCalibrationFrame();
      return;
    }
    video.currentTime = nextTime;
  };

  const shiftCalibrationFrame = (seconds: number) => {
    const video = calibrationVideoRef.current;
    if (!video) return;
    calibrationAutoSeekAttemptsRef.current = 0;
    calibrationAutoSeekEnabledRef.current = false;
    seekCalibrationVideo(video.currentTime + seconds);
  };

  // ── Quad calibration (drag) ─────────────────────────────────────────────

  const pointById = (id: CalibrationPointId) => calibrationPoints.find((point) => point.id === id);

  const toSvgPoint = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const point = svg.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    const transformed = point.matrixTransform(ctm.inverse());
    return { x: transformed.x, y: transformed.y };
  };

  const startDrag = (
    event: ReactPointerEvent,
    cornerIds: CalibrationPointId[],
  ) => {
    if (!calibrationFrameReady || isSubmitting) return;
    const point = toSvgPoint(event.clientX, event.clientY);
    if (!point) return;
    event.preventDefault();
    event.stopPropagation();
    try {
      svgRef.current?.setPointerCapture(event.pointerId);
    } catch {
      // 某些浏览器在 pointerId 无效时会抛异常，忽略即可
    }
    dragRef.current = { cornerIds, lastX: point.x, lastY: point.y };
  };

  const handleSvgPointerMove = (event: ReactPointerEvent) => {
    const drag = dragRef.current;
    if (!drag || !naturalSize) return;
    const point = toSvgPoint(event.clientX, event.clientY);
    if (!point) return;
    const dx = point.x - drag.lastX;
    const dy = point.y - drag.lastY;
    drag.lastX = point.x;
    drag.lastY = point.y;
    setCalibrationPoints((current) =>
      current.map((draft) => {
        if (!drag.cornerIds.includes(draft.id)) return draft;
        const nx = Math.min(Math.max(draft.x + dx, 0), naturalSize.width);
        const ny = Math.min(Math.max(draft.y + dy, 0), naturalSize.height);
        return {
          ...draft,
          x: Math.round(nx),
          y: Math.round(ny),
          viewX: (nx / naturalSize.width) * 100,
          viewY: (ny / naturalSize.height) * 100,
        };
      })
    );
  };

  const endDrag = (event: ReactPointerEvent) => {
    if (dragRef.current) {
      try {
        svgRef.current?.releasePointerCapture?.(event.pointerId);
      } catch {
        // 忽略释放异常
      }
      dragRef.current = null;
    }
  };

  const resetCalibration = () => {
    setCalibrationPoints([]);
    setAutomaticCalibration(null);
    setAutomaticCalibrationError(null);
    setAutomaticCalibrationStatus("idle");
    setError(null);
  };

  // ── Auto calibration ────────────────────────────────────────────────────

  const applyAutomaticKeypoints = (response: AutomaticCalibrationResponse) => {
    if (!response.keypoints || !response.selected_frame?.width || !response.selected_frame.height) return;
    const { width, height } = response.selected_frame;
    setCalibrationPoints(
      calibrationPointOrder.map((point) => {
        const detected = response.keypoints?.[point.id];
        const x = detected?.x ?? 0;
        const y = detected?.y ?? 0;
        return {
          id: point.id,
          label: point.label,
          x: Math.round(x),
          y: Math.round(y),
          viewX: Math.min(100, Math.max(0, (x / width) * 100)),
          viewY: Math.min(100, Math.max(0, (y / height) * 100)),
        };
      })
    );
    setNaturalSize({ width, height });
  };

  const resolveVideoId = async (): Promise<string | null> => {
    if (videoId) return videoId;
    if (ensureVideoId) {
      return ensureVideoId();
    }
    return null;
  };

  const handleAutomaticCalibration = async () => {
    if (automaticCalibrationStatus === "uploading" || automaticCalibrationStatus === "detecting") return;

    setError(null);
    setAutomaticCalibration(null);
    setAutomaticCalibrationError(null);
    try {
      setAutomaticCalibrationStatus(videoId ? "detecting" : "uploading");
      const resolvedVideoId = await resolveVideoId();
      if (!resolvedVideoId) {
        setAutomaticCalibrationStatus("unavailable");
        return;
      }
      setAutomaticCalibrationStatus("detecting");
      const response = await requestAutomaticCalibration(resolvedVideoId, {
        timestampSeconds: CALIBRATION_FRAME_SECONDS,
      });
      setAutomaticCalibration(response);
      if (response.status === "available" && response.keypoints) {
        applyAutomaticKeypoints(response);
        setAutomaticCalibrationStatus("ready");
      } else if (response.status === "rejected") {
        setAutomaticCalibrationStatus("rejected");
      } else {
        setAutomaticCalibrationStatus("unavailable");
      }
    } catch (err) {
      setAutomaticCalibrationStatus("error");
      setAutomaticCalibrationError(isAnalysisApiError(err) ? err : null);
      setError(errorToNotice("自动识别边线失败", "可以继续手动拖动四角点，已保留当前视频和比赛信息。", err));
    }
  };

  const canRequestAutomaticCalibration =
    Boolean(videoId || ensureVideoId) &&
    !isSubmitting &&
    automaticCalibrationStatus !== "uploading" &&
    automaticCalibrationStatus !== "detecting";

  const automaticCalibrationDiagnostic = automaticCalibrationNotice(
    automaticCalibration,
    automaticCalibrationStatus,
    automaticCalibrationError
  );

  // ── Submit ───────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!calibrationComplete) return;

    const frameHeight = naturalSize?.height ?? calibrationVideoRef.current?.videoHeight ?? 0;
    if (!isBaselineOrderPlausible(calibrationPoints, frameHeight)) {
      const confirmed = window.confirm(
        "检测到近端与远端底线可能颠倒（近端底线应位于画面下方）。请确认画面顶/底对应的场地底线，确认无误后继续。",
      );
      if (!confirmed) return;
    }

    try {
      const resolvedVideoId = await resolveVideoId();
      if (!resolvedVideoId) {
        setError(errorToNotice("标定提交失败", "视频尚未注册，请稍后重试。", null));
        return;
      }

      const pointMap = calibrationPoints.reduce(
        (acc, point) => {
          acc[point.id] = { x: point.x, y: point.y };
          return acc;
        },
        {} as Record<CalibrationPointDraft["id"], { x: number; y: number }>
      );

      const source = automaticCalibration?.status === "available" ? "automatic" : "corrected";
      const automaticAccepted =
        automaticCalibration?.status === "available"
          ? await acceptAutomaticCalibration(resolvedVideoId, pointMap, source)
          : null;
      const calibrationId =
        automaticAccepted?.calibration_id ??
        (await createManualCalibration(resolvedVideoId, pointMap)).calibration_id;

      onComplete(calibrationId, calibrationPoints);
    } catch (err) {
      setError(
        errorToNotice("标定提交失败", "请检查后端连接和视频格式后重试。", err)
      );
    }
  };

  // ── Lifecycle ────────────────────────────────────────────────────────────

  // Incoming drafts change when the wizard switches camera/video; reset the local editor state intentionally.
  useEffect(() => {
    calibrationAutoSeekAttemptsRef.current = 0;
    calibrationAutoSeekEnabledRef.current = Boolean(videoSrc);
    autoTriggeredRef.current = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- synchronize the local draft with new props
    setCalibrationPoints(initialPoints ? [...initialPoints] : []);
    setError(null);
    setShowCalibrationDetails(false);
  }, [initialPoints, videoId, videoSrc]);

  // 打开标定即自动触发一次自动标定（每个 videoId/ensureVideoId 仅一次）
  useEffect(() => {
    if (autoTriggeredRef.current) return;
    if (!videoId && !ensureVideoId) return;
    autoTriggeredRef.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 自动标定在挂载后异步发起，非同步 setState
    void handleAutomaticCalibration();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅在标定目标变化时触发一次
  }, [videoId, ensureVideoId]);

  // 自动标定失败 → 人工兜底：铺设居中默认四边形
  useEffect(() => {
    if (!manualMode) return;
    if (calibrationPoints.length > 0) return;
    if (!naturalSize) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 自动标定失败后填充默认草稿
    setCalibrationPoints(buildDefaultQuadPoints(naturalSize.width, naturalSize.height));
  }, [manualMode, naturalSize, calibrationPoints.length]);

  // ── Render ───────────────────────────────────────────────────────────────

  const polygonPoints = calibrationPoints.map((point) => `${point.x},${point.y}`).join(" ");
  const handleR = naturalSize ? Math.max(8, naturalSize.width * 0.006) : 8;
  const handleHitR = naturalSize ? Math.max(22, naturalSize.width * 0.016) : 22;
  const edgeStroke = naturalSize ? Math.max(2, naturalSize.width * 0.0018) : 2;
  const edgeHitStroke = naturalSize ? Math.max(20, naturalSize.width * 0.014) : 20;
  const handleStroke = naturalSize ? Math.max(2, naturalSize.width * 0.0015) : 2;
  const labelFont = naturalSize ? Math.max(12, naturalSize.width * 0.014) : 12;

  return (
    <section className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">四角标定</p>
          <div className="mt-1 flex items-center gap-1.5">
            <h2 className="text-lg font-black text-[#14241B]">
              {manualMode ? "拖动四边形对齐球场四角" : "自动识别球场边线"}
            </h2>
            {hasCalibrationDiagnostics ? (
              <button
                aria-expanded={showCalibrationDetails}
                aria-label="查看自动识别详细数据"
                className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[#168A34]/30 bg-[#168A34]/10 text-[#168A34] transition-colors hover:bg-[#168A34]/20"
                onClick={() => setShowCalibrationDetails((prev) => !prev)}
                type="button"
              >
                <Info className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
          <p className="mt-1 text-xs font-semibold text-slate-500">
            拖动四角或四边，让四边形贴合球场边界。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="quiet-button px-3 py-2 text-xs"
            disabled={!canRequestAutomaticCalibration}
            onClick={handleAutomaticCalibration}
            type="button"
          >
            {automaticCalibrationStatus === "uploading"
              ? "上传中..."
              : automaticCalibrationStatus === "detecting"
                ? "识别中..."
                : "重新自动识别"}
          </button>
          <button className="quiet-button px-3 py-2 text-xs" onClick={resetCalibration} type="button">
            重置
          </button>
        </div>
      </div>

      {/* Auto calibration status */}
      <div className="mt-3 grid gap-3 rounded-2xl border border-[#22C55E]/20 bg-white/70 p-3">
        {/* 保留可见：识别中/上传中进度反馈 */}
        {automaticCalibrationStatus === "uploading" || automaticCalibrationStatus === "detecting" ? (
          automaticCalibrationDiagnostic ? (
            <DiagnosticNoticeCard notice={automaticCalibrationDiagnostic} tone="info" />
          ) : (
            <p className="text-xs font-semibold text-slate-500">
              {automaticCalibrationStatus === "uploading" ? "正在上传视频并自动识别球场边线…" : "正在自动识别球场边线…"}
            </p>
          )
        ) : null}
        {/* 保留可见：失败/拒绝/不可用 → 操作指引 + 错误诊断 */}
        {automaticCalibrationStatus === "rejected" ||
        automaticCalibrationStatus === "unavailable" ||
        automaticCalibrationStatus === "error" ? (
          <>
            {manualMode ? (
              <p className="text-xs font-semibold text-[#A45A00]">
                自动标定失败，已切换到人工标定：拖动下方四边形对齐球场四角。
              </p>
            ) : null}
            {automaticCalibrationDiagnostic ? (
              <DiagnosticNoticeCard notice={automaticCalibrationDiagnostic} tone="error" />
            ) : null}
          </>
        ) : null}
        {/* 折叠区：仅展开时显示（就绪提示 + 开发指标 + 检测预览） */}
        {showCalibrationDetails ? (
          <>
            {automaticCalibrationStatus === "ready" && automaticCalibrationDiagnostic ? (
              <DiagnosticNoticeCard notice={automaticCalibrationDiagnostic} tone="info" />
            ) : null}
            {automaticCalibration?.confidence_breakdown ? (
              <div className="mt-3 grid grid-cols-4 gap-2 text-xs">
                {(
                  [
                    ["分割模型", automaticCalibration.confidence_breakdown.segmentation],
                    ["几何拟合", automaticCalibration.confidence_breakdown.geometry],
                    ["球场线校准", automaticCalibration.confidence_breakdown.reference],
                    ["综合置信度", automaticCalibration.confidence_breakdown.combined],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-2 text-center">
                    <div className="font-black text-base text-[#17231D]">{(value * 100).toFixed(0)}%</div>
                    <div className="mt-0.5 text-slate-400">{label}</div>
                  </div>
                ))}
              </div>
            ) : null}
            {automaticPreviewUrl ? (
              <img
                alt="自动标定检测预览"
                className="max-h-56 w-full rounded-xl border border-[#DDE9D6] object-contain"
                src={automaticPreviewUrl}
              />
            ) : null}
          </>
        ) : null}
      </div>

      {/* Frame navigation（仅人工标定模式需要） */}
      {manualMode ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="quiet-button px-3 py-2 text-xs"
            disabled={!videoSrc || calibrationFrameStatus === "error"}
            onClick={() => shiftCalibrationFrame(-1)}
            type="button"
          >
            前一秒
          </button>
          <button
            className="quiet-button px-3 py-2 text-xs"
            disabled={!videoSrc || calibrationFrameStatus === "error"}
            onClick={() => shiftCalibrationFrame(1)}
            type="button"
          >
            后一秒
          </button>
          <span className="self-center text-xs font-semibold text-slate-500">
            如果开头是黑场，可以先切换标定帧。
          </span>
        </div>
      ) : null}

      {/* Video + overlay */}
      <div className="relative mt-4 overflow-hidden rounded-2xl bg-[#091016]">
        <video
          className="block aspect-video w-full object-contain"
          controls={false}
          muted
          onError={() => {
            setCalibrationFrameStatus("error");
            setCalibrationFramePreviewUrl(null);
            setCalibrationFrameError(
              "视频资源加载失败，可能是文件暂不可访问、服务端返回错误，或视频编码不兼容。请刷新后重试；若仍失败，请检查视频是否已完成合并。",
            );
          }}
          onLoadedData={() => {
            if (!Number.isFinite(calibrationVideoRef.current?.duration ?? Number.NaN)) {
              captureCalibrationFrame();
            }
          }}
          onLoadedMetadata={() => {
            calibrationAutoSeekEnabledRef.current = true;
            seekCalibrationVideo();
          }}
          onSeeked={() => captureCalibrationFrame()}
          playsInline
          preload="metadata"
          ref={calibrationVideoRef}
          src={videoSrc}
        />
        {calibrationFramePreviewUrl ? (
          <img
            alt=""
            className="pointer-events-none absolute inset-0 h-full w-full object-contain"
            src={calibrationFramePreviewUrl}
          />
        ) : null}
        {naturalSize && calibrationFrameReady && calibrationComplete ? (
          <svg
            ref={svgRef}
            className="absolute inset-0 h-full w-full"
            preserveAspectRatio="xMidYMid meet"
            style={{ touchAction: "none" }}
            viewBox={`0 0 ${naturalSize.width} ${naturalSize.height}`}
            onPointerCancel={endDrag}
            onPointerMove={handleSvgPointerMove}
            onPointerUp={endDrag}
          >
            <polygon
              fill="rgba(34,197,94,0.12)"
              pointerEvents="none"
              points={polygonPoints}
              stroke="#22C55E"
              strokeLinejoin="round"
              strokeWidth={edgeStroke}
            />
            {calibrationEdges.map((edge) => {
              const from = pointById(edge.corners[0]);
              const to = pointById(edge.corners[1]);
              if (!from || !to) return null;
              return (
                <line
                  key={edge.id}
                  stroke="transparent"
                  strokeWidth={edgeHitStroke}
                  style={{ cursor: "move" }}
                  x1={from.x}
                  x2={to.x}
                  y1={from.y}
                  y2={to.y}
                  onPointerDown={(event) => startDrag(event, edge.corners)}
                />
              );
            })}
            {calibrationPoints.map((point, index) => (
              <g
                key={point.id}
                style={{ cursor: "grab" }}
                onPointerDown={(event) => startDrag(event, [point.id])}
              >
                <circle cx={point.x} cy={point.y} fill="transparent" r={handleHitR} />
                <circle
                  cx={point.x}
                  cy={point.y}
                  fill="#22C55E"
                  r={handleR}
                  stroke="#ffffff"
                  strokeWidth={handleStroke}
                />
                <text
                  fill="#ffffff"
                  fontSize={labelFont}
                  fontWeight="800"
                  paintOrder="stroke"
                  stroke="rgba(0,0,0,0.6)"
                  strokeWidth={1}
                  textAnchor="middle"
                  x={point.x}
                  y={point.y - handleR - 6}
                >
                  {index + 1}
                </text>
              </g>
            ))}
          </svg>
        ) : null}
        {!calibrationComplete && calibrationFrameStatus !== "ready" ? (
          <div className="pointer-events-none absolute inset-0 grid place-items-center px-5 text-center text-white">
            <div className="max-w-sm rounded-2xl border border-white/15 bg-black/65 px-4 py-3 shadow-xl">
              <strong className="text-sm">
                {calibrationFrameStatus === "error" ? "视频预览失败" : "正在读取可标定画面"}
              </strong>
              <p className="mt-1 text-xs leading-5 text-white/80">
                {calibrationFrameError ?? "系统会自动跳过开头黑场，等画面出现后再拖动四边形。"}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      {/* Point summary */}
      <div className="mt-3 grid gap-2 sm:grid-cols-4">
        {calibrationPointOrder.map((point) => {
          const match = calibrationPoints.find((p) => p.id === point.id);
          return (
            <div
              key={point.id}
              className={`rounded-xl border p-2 text-center text-xs ${
                match
                  ? "border-[#22C55E] bg-[#EAF7EE] font-bold text-[#168A34]"
                  : "border-[#DDE9D6] bg-[#F8FBF5] text-slate-400"
              }`}
            >
              {match ? `${point.label} · (${match.x}, ${match.y})` : point.label}
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error ? (
        <div className="mt-3 rounded-2xl border border-[#FCA5A5] bg-[#FEF2F2] p-3 text-xs">
          <strong className="block text-[#991B1B]">{error.title}</strong>
          <p className="mt-1 text-[#B91C1C]">{error.body}</p>
        </div>
      ) : null}

      {/* Submit + Cancel */}
      <div className="mt-4 flex flex-wrap gap-3">
        {calibrationComplete && (
          <button
            className="green-button px-5 py-2.5 text-sm font-bold"
            disabled={isSubmitting}
            onClick={handleSubmit}
            type="button"
          >
            {isSubmitting ? "提交中…" : "确认并启动分析"}
          </button>
        )}
        {onCancel && (
          <button
            className="quiet-button px-4 py-2.5 text-sm"
            disabled={isSubmitting}
            onClick={onCancel}
            type="button"
          >
            {cancelLabel}
          </button>
        )}
      </div>
    </section>
  );
}
