import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { ArrowRight, Camera, Upload } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import type { AnalysisUploadMetadata, AutomaticCalibrationResponse } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { Field } from "../components/Field";
import { DiagnosticNoticeCard } from "../components/DiagnosticNoticeCard";
import {
  type AnalysisApiError,
  uploadVideo,
  acceptAutomaticCalibration,
  createManualCalibration,
  createAnalysisJob,
  rememberAnalysisJob,
  requestAutomaticCalibration,
  resolveAnalysisAssetUrl,
  getVideoStreamUrl,
  isAnalysisApiError,
} from "../services/analysisClient";
import { automaticCalibrationNotice } from "../services/analysisDiagnostics";
import { errorToNotice } from "../utils/analysisHelpers";

const calibrationPointOrder = [
  { id: "top_left", label: "远端左角" },
  { id: "top_right", label: "远端右角" },
  { id: "bottom_right", label: "近端右角" },
  { id: "bottom_left", label: "近端左角" },
] as const;


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

type CalibrationPointDraft = {
  id: (typeof calibrationPointOrder)[number]["id"];
  label: string;
  viewX: number;
  viewY: number;
  x: number;
  y: number;
};

export function NewAnalysisPage({ onNavigate }: { onNavigate: NavigateFn }) {
  const today = new Date().toISOString().slice(0, 10);
  const calibrationVideoRef = useRef<HTMLVideoElement | null>(null);
  const calibrationCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const calibrationAutoSeekAttemptsRef = useRef(0);
  const calibrationAutoSeekEnabledRef = useRef(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [calibrationPoints, setCalibrationPoints] = useState<CalibrationPointDraft[]>([]);
  const [calibrationFrameStatus, setCalibrationFrameStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [calibrationFrameError, setCalibrationFrameError] = useState<string | null>(null);
  const [calibrationFramePreviewUrl, setCalibrationFramePreviewUrl] = useState<string | null>(null);
  const [uploadedVideoId, setUploadedVideoId] = useState<string | null>(null);
  const [automaticCalibration, setAutomaticCalibration] = useState<AutomaticCalibrationResponse | null>(null);
  const [automaticCalibrationStatus, setAutomaticCalibrationStatus] = useState<"idle" | "uploading" | "detecting" | "ready" | "unavailable" | "rejected" | "error">("idle");
  const [automaticCalibrationError, setAutomaticCalibrationError] = useState<AnalysisApiError | null>(null);
  const [submitStep, setSubmitStep] = useState<"idle" | "uploading" | "calibrating" | "creating">("idle");

  // 任务级推理开关：默认全部开启，用户可手动关闭（无标定时检测阶段本就跳过）
  const [enableModelInference, setEnableModelInference] = useState(true);
  const [enablePoseInference, setEnablePoseInference] = useState(true);

  // 支持直接传入 videoId（如从其他页面跳转）
  const [searchParams] = useState(() => new URLSearchParams(window.location.search));
  const videoIdParam = searchParams.get("videoId");
  const sourceFpsParam = Number(searchParams.get("fps") ?? NaN);

  const [metadata, setMetadata] = useState({
    matchTitle: "匹克球训练对局",
    venue: "北京体育大学匹克球训练场",
    matchDate: today,
    sourceFps: 60,
    matchFormat: "doubles" as AnalysisUploadMetadata["matchFormat"],
    cameraAngle: "elevated" as AnalysisUploadMetadata["cameraAngle"],
    athleteLabel: "球馆体验用户 A",
    level: "大众进阶",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<DiagnosticNotice | null>(null);

  // 当 videoId 传入时自动设置，并预填 fps
  useEffect(() => {
    if (!videoIdParam) return;
    // URL parameters are external input; hydrate local form state when they change.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- synchronizes URL state into the form.
    setUploadedVideoId(videoIdParam);
    if (Number.isFinite(sourceFpsParam) && sourceFpsParam > 0) {
      setMetadata((current) => ({ ...current, sourceFps: sourceFpsParam }));
    }
  }, [videoIdParam, sourceFpsParam]);

  const validSourceFps = Number.isFinite(metadata.sourceFps) && metadata.sourceFps > 0 && metadata.sourceFps <= 240;
  const hasCalibration = calibrationPoints.length === calibrationPointOrder.length;
  const canSubmit = Boolean(
    (selectedFile || uploadedVideoId) &&
      hasCalibration &&
      validSourceFps &&
      metadata.matchTitle.trim() &&
      metadata.venue.trim() &&
      metadata.matchDate &&
      metadata.athleteLabel.trim() &&
      metadata.level.trim()
  );
  const canRequestAutomaticCalibration = Boolean((selectedFile || uploadedVideoId) && !isSubmitting && automaticCalibrationStatus !== "uploading" && automaticCalibrationStatus !== "detecting");

  const updateMetadata = <K extends keyof typeof metadata>(key: K, value: (typeof metadata)[K]) => {
    setMetadata((current) => ({ ...current, [key]: value }));
    setError(null);
  };

  const videoPreviewUrl = useMemo(() => {
    if (selectedFile) return URL.createObjectURL(selectedFile);
    if (videoIdParam) return getVideoStreamUrl(videoIdParam) ?? null;
    return null;
  }, [selectedFile, videoIdParam]);

  useEffect(() => {
    calibrationAutoSeekAttemptsRef.current = 0;
    calibrationAutoSeekEnabledRef.current = Boolean(videoPreviewUrl);
    return () => {
      if (videoPreviewUrl && videoPreviewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(videoPreviewUrl);
      }
    };
  }, [videoPreviewUrl]);

  const calibrationComplete = calibrationPoints.length === calibrationPointOrder.length;
  const calibrationFrameReady = calibrationFrameStatus === "ready";
  const automaticPreviewUrl = resolveAnalysisAssetUrl(automaticCalibration?.preview_image_url);

  const captureCalibrationFrame = () => {
    const video = calibrationVideoRef.current;
    if (!video || video.readyState < 2) {
      return;
    }

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
        seekCalibrationVideo(video.currentTime + Math.min(Math.max(video.duration * 0.05, 0.75), 2), {
          autoSkipDark: true,
        });
        return;
      }

      calibrationAutoSeekEnabledRef.current = false;
      setCalibrationFramePreviewUrl(canvas.toDataURL("image/jpeg", 0.88));
      setCalibrationFrameStatus("ready");
    } catch {
      setCalibrationFrameStatus("ready");
    }
  };

  const seekCalibrationVideo = (targetSeconds?: number, options: { autoSkipDark?: boolean } = {}) => {
    const video = calibrationVideoRef.current;
    if (!video) {
      return;
    }

    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    if (duration <= 0) {
      if (video.readyState >= 2) {
        captureCalibrationFrame();
      } else {
        setCalibrationFrameStatus("loading");
      }
      return;
    }

    calibrationAutoSeekEnabledRef.current = Boolean(options.autoSkipDark);
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
    if (!video || calibrationPoints.length > 0) {
      return;
    }
    calibrationAutoSeekAttemptsRef.current = 0;
    seekCalibrationVideo(video.currentTime + seconds, { autoSkipDark: false });
  };

  const handleCalibrationClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (calibrationPoints.length >= calibrationPointOrder.length) {
      return;
    }
    if (!calibrationFrameReady) {
      setError({
        title: "标定画面未就绪",
        body: "标定帧还没有加载完成，请等画面出现后再点选四角。",
      });
      return;
    }

    const video = calibrationVideoRef.current;
    if (!video) {
      return;
    }

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

  const ensureUploadedVideo = async () => {
    if (uploadedVideoId) {
      return uploadedVideoId;
    }
    if (!selectedFile) {
      throw new Error("No selected file");
    }
    const upload = await uploadVideo(selectedFile);
    setUploadedVideoId(upload.video.id);
    return upload.video.id;
  };

  const pointMapFromDraft = () =>
    calibrationPoints.reduce(
      (acc, point) => {
        acc[point.id] = { x: point.x, y: point.y };
        return acc;
      },
      {} as Record<CalibrationPointDraft["id"], { x: number; y: number }>
    );

  const applyAutomaticKeypoints = (response: AutomaticCalibrationResponse) => {
    if (!response.keypoints || !response.selected_frame?.width || !response.selected_frame.height) {
      return;
    }
    const width = response.selected_frame.width;
    const height = response.selected_frame.height;
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
    if (!canRequestAutomaticCalibration) {
      return;
    }

    setError(null);
    setAutomaticCalibration(null);
    setAutomaticCalibrationError(null);
    try {
      setAutomaticCalibrationStatus(uploadedVideoId ? "detecting" : "uploading");
      const videoId = await ensureUploadedVideo();
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
    } catch (error) {
      setAutomaticCalibrationStatus("error");
      setAutomaticCalibrationError(isAnalysisApiError(error) ? error : null);
      setError(errorToNotice("自动识别边线失败", "可以继续手动点选四个角点，已保留当前视频和比赛信息。", error));
    }
  };

  const handleSubmit = async () => {
    if (!canSubmit) {
      setError({
        title: "分析信息不完整",
        body: "请选择视频、点选四个场地角点、确认视频帧率并补全比赛信息。",
      });
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      setSubmitStep(uploadedVideoId ? "calibrating" : "uploading");
      const videoId = await ensureUploadedVideo();
      const pointMap = pointMapFromDraft();

      setSubmitStep("calibrating");
      const source = automaticCalibration?.status === "available" ? "automatic" : "corrected";
      const automaticAccepted =
        automaticCalibration?.status === "available"
          ? await acceptAutomaticCalibration(videoId, pointMap, source)
          : null;
      const calibrationId =
        automaticAccepted?.calibration_id ??
        (await createManualCalibration(videoId, pointMap)).calibration_id;

      setSubmitStep("creating");
      const job = await createAnalysisJob({
        metadata: {
          ...metadata,
          fileName: selectedFile?.name ?? `recording-${videoId}.mp4`,
          fileSize: selectedFile?.size,
        },
        videoId,
        calibrationId,
        frameStride: 2,
        useDemoFallback: false,
        enableModelInference,
        enablePoseInference,
      });
      rememberAnalysisJob(job);
      onNavigate("/analysis/tasks");
    } catch (error) {
      setError(
        errorToNotice(
          "真实上传或分析任务创建失败",
          "请确认后端已启动、视频格式受支持，并重新检查四角标定。",
          error
        )
      );
    } finally {
      setIsSubmitting(false);
      setSubmitStep("idle");
    }
  };

  const nextCalibrationPoint = calibrationPointOrder[calibrationPoints.length];
  const submitCopy = {
    idle: "开始真实分析",
    uploading: "上传视频中...",
    calibrating: "提交标定中...",
    creating: "创建任务中...",
  }[submitStep];
  const automaticCalibrationDiagnostic = automaticCalibrationNotice(
    automaticCalibration,
    automaticCalibrationStatus,
    automaticCalibrationError
  );

  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Upload size={16} aria-hidden="true" />
            上传比赛视频
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">创建视觉分析任务</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            上传视频会进入本地 Python 后端，四角标定后创建持久化任务，由 worker 执行视觉分析，先输出移动、速度、热力图等真实可追溯反馈。
          </p>

          <div className="mt-6 grid gap-3 rounded-3xl border border-[#DDE9D6] bg-white/70 p-4">
            {[
              ["1", "上传视频", "保留原始文件和基础比赛信息"],
              ["2", "四角标定", "把画面坐标映射到标准匹克球场"],
              ["3", "生成报告", "输出移动轨迹、速度、热力图和有限诊断"],
            ].map(([index, title, body]) => (
              <div className="flex gap-3 rounded-2xl bg-[#F5FAF1] p-3" key={index}>
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[#22C55E] text-sm font-black text-[#071008]">
                  {index}
                </span>
                <div>
                  <strong className="text-[#14241B]">{title}</strong>
                  <p className="mt-1 text-sm text-slate-600">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <section className="sport-card p-5 sm:p-6">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">视频文件</p>
            {videoIdParam ? (
              <div className="mt-3 rounded-3xl border border-[#22C55E]/30 bg-[#F0FFF0] p-6 text-center">
                <span className="grid size-14 place-items-center mx-auto rounded-full bg-[#22C55E]/15 text-[#168A34]">
                  <Camera size={24} aria-hidden="true" />
                </span>
                <strong className="mt-4 block text-lg text-[#14241B]">已选择视频</strong>
                <p className="mt-2 text-sm text-slate-500">
                  跳过文件上传步骤，直接进行四角标定
                </p>
              </div>
            ) : (
            <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed border-[#BFD5B8] bg-[#F5FAF1] p-8 text-center transition hover:border-[#22C55E]/60 hover:bg-[#F9FFF6]">
              <input
                accept="video/*"
                className="sr-only"
                onChange={(event) => {
                  const nextFile = event.target.files?.[0] ?? null;
                  setSelectedFile(nextFile);
                  setCalibrationPoints([]);
                  setCalibrationFrameStatus(nextFile ? "loading" : "idle");
                  setCalibrationFrameError(null);
                  setCalibrationFramePreviewUrl(null);
                  setUploadedVideoId(null);
                  setAutomaticCalibration(null);
                  setAutomaticCalibrationError(null);
                  setAutomaticCalibrationStatus("idle");
                  setError(null);
                }}
                type="file"
              />
              <span className="grid size-14 place-items-center rounded-full bg-[#22C55E]/15 text-[#168A34]">
                <Upload size={24} aria-hidden="true" />
              </span>
              <strong className="mt-4 text-lg text-[#14241B]">
                {selectedFile ? selectedFile.name : "选择比赛视频"}
              </strong>
              <p className="mt-2 text-sm text-slate-500">
                {selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(1)} MB · 将上传到本地分析后端` : "支持常见视频格式，真实上传由后端接管"}
              </p>
            </label>
            )}
          </div>

          {videoPreviewUrl ? (
            <div className="mt-6 rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
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
                    tone={automaticCalibrationStatus === "ready" || automaticCalibrationStatus === "detecting" || automaticCalibrationStatus === "uploading" ? "info" : "error"}
                  />
                ) : null}
                {automaticCalibration?.confidence_breakdown ? (
                  <div className="mt-3 grid grid-cols-4 gap-2 text-xs">
                    {([
                      ["分割模型", automaticCalibration.confidence_breakdown.segmentation],
                      ["几何拟合", automaticCalibration.confidence_breakdown.geometry],
                      ["球场线校准", automaticCalibration.confidence_breakdown.reference],
                      ["综合置信度", automaticCalibration.confidence_breakdown.combined],
                    ] as const).map(([label, value]) => (
                      <div key={label} className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-2 text-center">
                        <div className="font-black text-base text-[#17231D]">{(value * 100).toFixed(0)}%</div>
                        <div className="mt-0.5 text-slate-400">{label}</div>
                      </div>
                    ))}
                  </div>
                ) : null}
                {automaticCalibration?.reference ? (
                  <div className="mt-2 rounded-xl border border-[#DDE9D6] bg-[#F8FBF5] p-3 text-xs text-slate-600">
                    <span className="font-bold text-[#17231D]">球场线参考: </span>
                    {automaticCalibration.reference.summary}
                    {automaticCalibration.reference.passing_line_names?.length > 0 && (
                      <span className="ml-1 text-slate-400">
                        (通过: {automaticCalibration.reference.passing_line_names.slice(0, 4).join(", ")})
                      </span>
                    )}
                    {automaticCalibration.reference.rejection_reason && (
                      <div className="mt-1 text-[#C92A2A]">
                        拒绝原因: {automaticCalibration.reference.rejection_reason}
                      </div>
                    )}
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
              {!calibrationComplete && calibrationPoints.length === 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    className="quiet-button px-3 py-2 text-xs"
                    disabled={!videoPreviewUrl || calibrationFrameStatus === "error"}
                    onClick={() => shiftCalibrationFrame(-1)}
                    type="button"
                  >
                    前一秒
                  </button>
                  <button
                    className="quiet-button px-3 py-2 text-xs"
                    disabled={!videoPreviewUrl || calibrationFrameStatus === "error"}
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
                  onLoadedMetadata={() => seekCalibrationVideo(undefined, { autoSkipDark: true })}
                  onSeeked={() => captureCalibrationFrame()}
                  playsInline
                  preload="auto"
                  ref={calibrationVideoRef}
                  src={videoPreviewUrl}
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
              <div className="mt-3 grid gap-2 sm:grid-cols-4">
                {calibrationPointOrder.map((point, index) => {
                  const selected = calibrationPoints.find((item) => item.id === point.id);
                  return (
                    <div className="rounded-2xl bg-white/75 p-3 text-xs" key={point.id}>
                      <strong className={selected ? "text-[#168A34]" : "text-slate-500"}>
                        {index + 1}. {point.label}
                      </strong>
                      <p className="mt-1 text-slate-500">{selected ? `${selected.x}, ${selected.y}` : "等待点击"}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <Field label="比赛名称">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("matchTitle", event.target.value)}
                value={metadata.matchTitle}
              />
            </Field>
            <Field label="比赛日期">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("matchDate", event.target.value)}
                type="date"
                value={metadata.matchDate}
              />
            </Field>
            <Field label="视频帧率">
              <div className="grid grid-cols-[1fr_110px] gap-2">
                <select
                  className="field-input"
                  onChange={(event) => {
                    if (event.target.value !== "custom") updateMetadata("sourceFps", Number(event.target.value));
                  }}
                  value={[24, 25, 30, 50, 60, 90, 120].includes(metadata.sourceFps) ? metadata.sourceFps : "custom"}
                >
                  {[24, 25, 30, 50, 60, 90, 120].map((fps) => (
                    <option key={fps} value={fps}>{fps} fps</option>
                  ))}
                  <option value="custom">自定义</option>
                </select>
                <input
                  className="field-input"
                  max={240}
                  min={1}
                  onChange={(event) => updateMetadata("sourceFps", Number(event.target.value))}
                  type="number"
                  value={metadata.sourceFps}
                />
              </div>
            </Field>
            <Field label="场地">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("venue", event.target.value)}
                value={metadata.venue}
              />
            </Field>
            <Field label="球员/队伍">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("athleteLabel", event.target.value)}
                value={metadata.athleteLabel}
              />
            </Field>
            <Field label="比赛形式">
              <div className="flex gap-1 rounded-lg border border-gray-300 p-0.5 bg-gray-50">
                <button
                  type="button"
                  className={`flex-1 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                    metadata.matchFormat === "doubles"
                      ? "bg-white text-gray-900 shadow-sm border border-gray-200"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                  onClick={() => updateMetadata("matchFormat", "doubles")}
                >
                  双打（4人）
                </button>
                <button
                  type="button"
                  className={`flex-1 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                    metadata.matchFormat === "singles"
                      ? "bg-white text-gray-900 shadow-sm border border-gray-200"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                  onClick={() => updateMetadata("matchFormat", "singles")}
                >
                  单打（2人）
                </button>
              </div>
            </Field>
            <Field label="拍摄角度">
              <select
                className="field-input"
                onChange={(event) => updateMetadata("cameraAngle", event.target.value as AnalysisUploadMetadata["cameraAngle"])}
                value={metadata.cameraAngle}
              >
                <option value="elevated">高位俯拍</option>
                <option value="baseline">底线视角</option>
                <option value="sideline">边线视角</option>
                <option value="unknown">未知</option>
              </select>
            </Field>
            <Field label="水平">
              <input
                className="field-input"
                onChange={(event) => updateMetadata("level", event.target.value)}
                value={metadata.level}
              />
            </Field>
          </div>

          {error ? (
            <div className="mt-4">
              <DiagnosticNoticeCard notice={error} />
            </div>
          ) : null}

          <div className="mt-6 rounded-3xl border border-[#DDE9D6] bg-white/70 p-4">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">模型推理</p>
            <p className="mt-1 text-xs text-slate-500">选择本次分析是否运行以下模型推理（默认开启，可手动关闭）。</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <label className="flex cursor-pointer items-center justify-between gap-3 rounded-2xl bg-[#F5FAF1] px-3 py-2.5">
                <span className="text-sm font-semibold text-[#14241B]">人体检测 (YOLO)</span>
                <input
                  checked={enableModelInference}
                  className="size-4 accent-[#22C55E]"
                  onChange={(event) => setEnableModelInference(event.target.checked)}
                  type="checkbox"
                />
              </label>
              <label className="flex cursor-pointer items-center justify-between gap-3 rounded-2xl bg-[#F5FAF1] px-3 py-2.5">
                <span className="text-sm font-semibold text-[#14241B]">姿态识别 (RTMPose)</span>
                <input
                  checked={enablePoseInference}
                  className="size-4 accent-[#22C55E]"
                  onChange={(event) => setEnablePoseInference(event.target.checked)}
                  type="checkbox"
                />
              </label>
            </div>
            {!hasCalibration ? (
              <p className="mt-2 text-xs text-[#A45A00]">完成四角标定后，人体检测与姿态识别才会真正运行。</p>
            ) : null}
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button className="green-button" disabled={!canSubmit || isSubmitting} onClick={handleSubmit} type="button">
              {isSubmitting ? submitCopy : "开始真实分析"}
              <ArrowRight size={17} aria-hidden="true" />
            </button>
            <button className="quiet-button" onClick={() => onNavigate("/vision")} type="button">
              查看演示工作台
            </button>
            <button className="quiet-button" onClick={() => onNavigate("/analysis/tasks")} type="button">
              查看任务管理
            </button>
          </div>
        </section>
      </section>
    </PageFrame>
  );
}
