import { useEffect, useRef, useState, type MouseEvent } from "react";
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

export interface CourtCornerCalibratorProps {
  /** 视频流 URL（用于预览和标定） */
  videoSrc: string;
  /** 已注册的视频 ID（用于调用后端标定 API） */
  videoId: string;
  /** 标定完成后回调，返回 calibrationId + 四个点的坐标 */
  onComplete: (calibrationId: string, points: CalibrationPointDraft[]) => void;
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

// ── Component ───────────────────────────────────────────────────────────────

export function CourtCornerCalibrator({
  videoSrc,
  videoId,
  onComplete,
  onCancel,
  isSubmitting = false,
}: CourtCornerCalibratorProps) {
  const calibrationVideoRef = useRef<HTMLVideoElement | null>(null);
  const calibrationCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const calibrationAutoSeekAttemptsRef = useRef(0);
  const calibrationAutoSeekEnabledRef = useRef(false);

  const [calibrationPoints, setCalibrationPoints] = useState<CalibrationPointDraft[]>([]);
  const [calibrationFrameStatus, setCalibrationFrameStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [calibrationFrameError, setCalibrationFrameError] = useState<string | null>(null);
  const [calibrationFramePreviewUrl, setCalibrationFramePreviewUrl] = useState<string | null>(null);

  const [automaticCalibration, setAutomaticCalibration] = useState<AutomaticCalibrationResponse | null>(null);
  const [automaticCalibrationStatus, setAutomaticCalibrationStatus] = useState<"idle" | "uploading" | "detecting" | "ready" | "unavailable" | "rejected" | "error">("idle");
  const [automaticCalibrationError, setAutomaticCalibrationError] = useState<AnalysisApiError | null>(null);
  const [error, setError] = useState<{ title: string; body: string } | null>(null);

  const calibrationComplete = calibrationPoints.length === calibrationPointOrder.length;
  const calibrationFrameReady = calibrationFrameStatus === "ready";
  const nextCalibrationPoint = calibrationPointOrder[calibrationPoints.length];
  const automaticPreviewUrl = resolveAnalysisAssetUrl(automaticCalibration?.preview_image_url);

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

    const defaultTarget = Math.min(Math.max(duration * 0.1, 0.15), Math.max(duration - 0.05, 0));
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
    if (!video || calibrationPoints.length > 0) return;
    calibrationAutoSeekAttemptsRef.current = 0;
    calibrationAutoSeekEnabledRef.current = false;
    seekCalibrationVideo(video.currentTime + seconds);
  };

  // ── Manual calibration ──────────────────────────────────────────────────

  const handleCalibrationClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (calibrationPoints.length >= calibrationPointOrder.length) return;
    if (!calibrationFrameReady) {
      setError({
        title: "标定画面未就绪",
        body: "标定帧还没有加载完成，请等画面出现后再点选四角。",
      });
      return;
    }

    const video = calibrationVideoRef.current;
    if (!video) return;

    video.pause();
    const rect = event.currentTarget.getBoundingClientRect();
    const nextPoint = calibrationPointOrder[calibrationPoints.length];
    const naturalWidth = video.videoWidth || rect.width;
    const naturalHeight = video.videoHeight || rect.height;
    const mediaAspect = naturalWidth / naturalHeight;
    const viewAspect = rect.width / rect.height;
    const renderedWidth = viewAspect > mediaAspect ? rect.height * mediaAspect : rect.width;
    const renderedHeight = viewAspect > mediaAspect ? rect.height : rect.width / mediaAspect;
    const offsetX = (rect.width - renderedWidth) / 2;
    const offsetY = (rect.height - renderedHeight) / 2;
    const xInMedia = Math.min(Math.max(event.clientX - rect.left - offsetX, 0), renderedWidth);
    const yInMedia = Math.min(Math.max(event.clientY - rect.top - offsetY, 0), renderedHeight);
    setCalibrationPoints((current) => [
      ...current,
      {
        id: nextPoint.id,
        label: nextPoint.label,
        x: Math.round(xInMedia * (naturalWidth / renderedWidth)),
        y: Math.round(yInMedia * (naturalHeight / renderedHeight)),
        viewX: ((offsetX + xInMedia) / rect.width) * 100,
        viewY: ((offsetY + yInMedia) / rect.height) * 100,
      },
    ]);
    setError(null);
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
  };

  const handleAutomaticCalibration = async () => {
    if (automaticCalibrationStatus === "uploading" || automaticCalibrationStatus === "detecting") return;

    setError(null);
    setAutomaticCalibration(null);
    setAutomaticCalibrationError(null);
    try {
      setAutomaticCalibrationStatus("detecting");
      const response = await requestAutomaticCalibration(videoId);
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
      setError(errorToNotice("自动识别边线失败", "可以继续手动点选四个角点，已保留当前视频和比赛信息。", err));
    }
  };

  const canRequestAutomaticCalibration =
    Boolean(videoId) &&
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

    try {
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
          ? await acceptAutomaticCalibration(videoId, pointMap, source)
          : null;
      const calibrationId =
        automaticAccepted?.calibration_id ??
        (await createManualCalibration(videoId, pointMap)).calibration_id;

      onComplete(calibrationId, calibrationPoints);
    } catch (err) {
      setError(
        errorToNotice("标定提交失败", "请检查后端连接和视频格式后重试。", err)
      );
    }
  };

  // ── Video lifecycle ─────────────────────────────────────────────────────

  useEffect(() => {
    calibrationAutoSeekAttemptsRef.current = 0;
    calibrationAutoSeekEnabledRef.current = Boolean(videoSrc);
  }, [videoSrc]);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <section className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">四角标定</p>
          <h2 className="mt-1 text-lg font-black text-[#14241B]">
            {nextCalibrationPoint ? `点击画面中的${nextCalibrationPoint.label}` : "四个角点已记录"}
          </h2>
          <p className="mt-1 text-xs font-semibold text-slate-500">
            点选期间视频控件会隐藏，避免误触播放键或进度条。
          </p>
        </div>
        <button className="quiet-button px-3 py-2 text-xs" onClick={resetCalibration} type="button">
          重新点选
        </button>
      </div>

      {/* Auto calibration */}
      <div className="mt-3 grid gap-3 rounded-2xl border border-[#22C55E]/20 bg-white/70 p-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <strong className="text-sm text-[#14241B]">自动识别球场边线</strong>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              先上传视频并请求后端模型建议，识别结果会填入四角点，仍可手动修正。
            </p>
          </div>
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
                : "自动识别"}
          </button>
        </div>
        {automaticCalibrationDiagnostic ? (
          <DiagnosticNoticeCard
            notice={automaticCalibrationDiagnostic}
            tone={
              automaticCalibrationStatus === "ready" ||
              automaticCalibrationStatus === "detecting" ||
              automaticCalibrationStatus === "uploading"
                ? "info"
                : "error"
            }
          />
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
            alt=""
            className="max-h-56 w-full rounded-xl border border-[#DDE9D6] object-contain"
            src={automaticPreviewUrl}
          />
        ) : null}
      </div>

      {/* Frame navigation */}
      {!calibrationComplete && calibrationPoints.length === 0 ? (
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
          controls={calibrationComplete}
          muted
          onError={() => {
            setCalibrationFrameStatus("error");
            setCalibrationFramePreviewUrl(null);
            setCalibrationFrameError("浏览器无法预览这个视频编码。请换用 H.264 MP4，或先转码后再标定。");
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
          preload="auto"
          ref={calibrationVideoRef}
          src={videoSrc}
        />
        {!calibrationComplete && calibrationFramePreviewUrl ? (
          <img
            alt=""
            className="pointer-events-none absolute inset-0 h-full w-full object-contain"
            src={calibrationFramePreviewUrl}
          />
        ) : null}
        {!calibrationComplete ? (
          <button
            aria-label={nextCalibrationPoint ? `点击${nextCalibrationPoint.label}` : "标定画面"}
            className={`absolute inset-0 text-left ${
              calibrationFrameReady ? "cursor-crosshair bg-black/5" : "cursor-not-allowed bg-black/35"
            }`}
            disabled={!calibrationFrameReady}
            onClick={handleCalibrationClick}
            type="button"
          >
            <span className="absolute left-3 top-3 rounded-full border border-white/15 bg-black/55 px-3 py-1 text-xs font-black text-white shadow-lg">
              {calibrationFrameReady && nextCalibrationPoint
                ? `标定中 · ${calibrationPoints.length + 1}/4 · ${nextCalibrationPoint.label}`
                : "正在准备标定画面"}
            </span>
          </button>
        ) : null}
        {!calibrationComplete && calibrationFrameStatus !== "ready" ? (
          <div className="pointer-events-none absolute inset-0 grid place-items-center px-5 text-center text-white">
            <div className="max-w-sm rounded-2xl border border-white/15 bg-black/65 px-4 py-3 shadow-xl">
              <strong className="text-sm">
                {calibrationFrameStatus === "error" ? "视频预览失败" : "正在读取可标定画面"}
              </strong>
              <p className="mt-1 text-xs leading-5 text-white/80">
                {calibrationFrameError ?? "系统会自动跳过开头黑场，等画面出现后再点选四个场地角。"}
              </p>
            </div>
          </div>
        ) : null}
        {calibrationPoints.map((point, index) => (
          <span
            className="pointer-events-none absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white bg-[#22C55E] text-xs font-black text-[#071008] shadow-lg"
            key={point.id}
            style={{ left: `${point.viewX}%`, top: `${point.viewY}%` }}
          >
            {index + 1}
          </span>
        ))}
      </div>

      {/* Point summary */}
      <div className="mt-3 grid gap-2 sm:grid-cols-4">
        {calibrationPointOrder.map((point, index) => {
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
              {match ? `${match.id} ✓` : `${index + 1}. ${point.label}`}
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
            className="sport-button px-5 py-2.5 text-sm font-bold"
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
            取消
          </button>
        )}
      </div>
    </section>
  );
}
