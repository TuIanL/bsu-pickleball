import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Camera, Upload } from "lucide-react";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { taskContextFromLocation, taskListPath } from "../app/navigationContext";
import type { AnalysisUploadMetadata } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { Field } from "../components/Field";
import { DiagnosticNoticeCard } from "../components/DiagnosticNoticeCard";
import { CourtCornerCalibrator } from "../components/platform/CourtCornerCalibrator";
import {
  uploadVideo,
  createAnalysisJob,
  rememberAnalysisJob,
  getVideoStreamUrl,
} from "../services/analysisClient";
import { errorToNotice } from "../utils/analysisHelpers";

export function NewAnalysisPage({ onNavigate }: { onNavigate: NavigateFn }) {
  const today = new Date().toISOString().slice(0, 10);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadedVideoId, setUploadedVideoId] = useState<string | null>(null);
  const uploadedVideoIdRef = useRef<string | null>(null);
  const uploadPromiseRef = useRef<Promise<string> | null>(null);

  // 任务级推理开关：默认全部开启，用户可手动关闭（无标定时检测阶段本就跳过）
  const [enableModelInference, setEnableModelInference] = useState(true);
  const [enablePoseInference, setEnablePoseInference] = useState(true);

  // 支持直接传入 videoId（如从其他页面跳转）
  const [searchParams] = useState(() => new URLSearchParams(window.location.search));
  const returnTaskContext = taskContextFromLocation();
  const returnParam = new URLSearchParams(window.location.search).get("return");
  // 从 Library 进入时优先回到来源工作区；否则回任务列表（既有行为）
  const goReturn = () => onNavigate((returnParam ?? taskListPath(returnTaskContext)) as NavigatePath);
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
  const metadataComplete = Boolean(
    (selectedFile || uploadedVideoId) &&
      validSourceFps &&
      metadata.matchTitle.trim() &&
      metadata.venue.trim() &&
      metadata.matchDate &&
      metadata.athleteLabel.trim() &&
      metadata.level.trim()
  );

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
    return () => {
      if (videoPreviewUrl && videoPreviewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(videoPreviewUrl);
      }
    };
  }, [videoPreviewUrl]);

  const ensureUploadedVideo = async (): Promise<string> => {
    if (uploadedVideoId) {
      return uploadedVideoId;
    }
    if (uploadedVideoIdRef.current) {
      return uploadedVideoIdRef.current;
    }
    if (uploadPromiseRef.current) {
      return uploadPromiseRef.current;
    }
    if (!selectedFile) {
      throw new Error("No selected file");
    }
    uploadPromiseRef.current = (async () => {
      const upload = await uploadVideo(selectedFile);
      uploadedVideoIdRef.current = upload.video.id;
      setUploadedVideoId(upload.video.id);
      return upload.video.id;
    })();
    return uploadPromiseRef.current;
  };

  const handleCalibrationComplete = async (calibrationId: string) => {
    if (!metadataComplete) {
      setError({
        title: "分析信息不完整",
        body: "请选择视频、确认视频帧率并补全比赛信息后再启动分析。",
      });
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const videoId = await ensureUploadedVideo();
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
      goReturn();
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
    }
  };

  return (
    <PageFrame>
      <button
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-bold text-[#168A34] transition hover:text-[#0F7A2B]"
        onClick={() => onNavigate("/library")}
        type="button"
      >
        <ArrowLeft size={16} aria-hidden="true" />
        返回比赛库
      </button>
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
                  setUploadedVideoId(null);
                  uploadedVideoIdRef.current = null;
                  uploadPromiseRef.current = null;
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
            <CourtCornerCalibrator
              videoSrc={videoPreviewUrl}
              videoId=""
              ensureVideoId={ensureUploadedVideo}
              isSubmitting={isSubmitting}
              onComplete={handleCalibrationComplete}
            />
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
            {!metadataComplete ? (
              <p className="mt-2 text-xs text-[#A45A00]">完成视频选择与四角标定后，人体检测与姿态识别才会真正运行。</p>
            ) : null}
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button className="quiet-button" onClick={() => onNavigate("/vision")} type="button">
              查看演示工作台
            </button>
            <button className="quiet-button" onClick={() => onNavigate(taskListPath(returnTaskContext))} type="button">
              查看任务管理
            </button>
          </div>
        </section>
      </section>
    </PageFrame>
  );
}
