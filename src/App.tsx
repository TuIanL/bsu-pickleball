// 导入 Lucide 图标库
import {
  ArrowRight,
  BadgeCheck,
  Brain,
  Camera,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Dumbbell,
  Gauge,
  LineChart,
  Play,
  Radar,
  ShieldCheck,
  Sparkles,
  Timer,
  Upload,
  Zap,
} from "lucide-react";
// 导入 React 核心钩子和类型
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell } from "./components/platform/AppShell";
import { MetricCard } from "./components/platform/MetricCard";
import { ProgressChart } from "./components/platform/ProgressChart";
import { ReportVisualization } from "./components/platform/ReportVisualization";
import { ShotExplorer } from "./components/platform/ShotExplorer";
import { SkillRatings } from "./components/platform/SkillRatings";
import { VideoAnalysisCard } from "./components/platform/VideoAnalysisCard";
import {
  drillRecommendations,
  hardwarePreview,
  matchSummary,
  overviewCards,
  platformNavigation,
  playerMarkers,
  progressPoints,
  reportActions,
  shotFilters,
  shotTrajectories,
  timelineMarkers,
  trainingRecommendations,
  videoOverlayLabels,
} from "./data/demoData";
import type {
  AnalysisJobSummary,
  AnalysisReport,
  AnalysisUploadMetadata,
  AppPath,
  DrillRecommendation,
  InsightTone,
  ReportType,
} from "./types/report";
import { createAnalysisJob, demoAnalysisReport as demoReport, getAnalysisJob, getAnalysisReport } from "./services/analysisClient";

// 定义路由状态类型，用于管理应用内的页面导航
type RouteState =
  | { page: "overview"; path: "/" } // 总览页
  | { page: "new-analysis"; path: "/analysis/new" } // 新建分析任务页
  | { page: "analysis-job"; path: `/analysis/${string}`; jobId: string } // 分析任务详情页
  | { page: "vision"; path: "/vision" } // 视觉分析工作台
  | { page: "vision"; path: `/analysis/${string}/vision`; jobId: string } // 特定任务的视觉分析
  | { page: "report"; path: `/reports/${ReportType}`; reportType: ReportType } // 报告页
  | { page: "report"; path: `/analysis/${string}/reports/${ReportType}`; reportType: ReportType; jobId: string } // 特定任务的报告
  | { page: "training"; path: "/training" } // 训练建议页
  | { page: "hardware"; path: "/hardware" }; // 硬件融合预览页

const supportedReportTypes: ReportType[] = ["landing", "movement", "rally", "diagnosis"];

const toneStyles: Record<InsightTone, { dot: string; text: string; border: string; bg: string }> = {
  advantage: {
    dot: "bg-[#22C55E]",
    text: "text-[#168A34]",
    border: "border-[#22C55E]/25",
    bg: "bg-[#22C55E]/12",
  },
  risk: {
    dot: "bg-[#FF9500]",
    text: "text-[#A45A00]",
    border: "border-[#FF9500]/25",
    bg: "bg-[#FF9500]/12",
  },
  error: {
    dot: "bg-[#FF4D4F]",
    text: "text-[#C92A2A]",
    border: "border-[#FF4D4F]/25",
    bg: "bg-[#FF4D4F]/12",
  },
  training: {
    dot: "bg-[#2F80ED]",
    text: "text-[#1E63B6]",
    border: "border-[#2F80ED]/25",
    bg: "bg-[#2F80ED]/12",
  },
};

function parsePath(pathname: string): RouteState {
  if (pathname === "/analysis/new" || pathname === "/upload") {
    return { page: "new-analysis", path: "/analysis/new" };
  }

  const analysisReportMatch = pathname.match(/^\/analysis\/([^/]+)\/reports\/([^/]+)$/);

  if (analysisReportMatch) {
    const [, jobId, reportType] = analysisReportMatch;

    if (supportedReportTypes.includes(reportType as ReportType)) {
      return {
        page: "report",
        path: `/analysis/${jobId}/reports/${reportType as ReportType}`,
        reportType: reportType as ReportType,
        jobId,
      };
    }

    return { page: "analysis-job", path: `/analysis/${jobId}`, jobId };
  }

  const analysisVisionMatch = pathname.match(/^\/analysis\/([^/]+)\/vision$/);

  if (analysisVisionMatch) {
    const [, jobId] = analysisVisionMatch;
    return { page: "vision", path: `/analysis/${jobId}/vision`, jobId };
  }

  const analysisJobMatch = pathname.match(/^\/analysis\/([^/]+)$/);

  if (analysisJobMatch) {
    const [, jobId] = analysisJobMatch;
    return { page: "analysis-job", path: `/analysis/${jobId}`, jobId };
  }

  if (pathname === "/vision") {
    return { page: "vision", path: "/vision" };
  }

  if (pathname === "/training") {
    return { page: "training", path: "/training" };
  }

  if (pathname === "/hardware") {
    return { page: "hardware", path: "/hardware" };
  }

  if (pathname.startsWith("/reports/")) {
    const reportType = pathname.replace("/reports/", "") as ReportType;

    if (supportedReportTypes.includes(reportType)) {
      return { page: "report", path: `/reports/${reportType}`, reportType };
    }
  }

  return { page: "overview", path: "/" };
}

function App() {
  // 初始化路由状态
  const [route, setRoute] = useState<RouteState>(() => parsePath(window.location.pathname));

  // 自定义导航函数，支持平滑滚动到顶部
  const navigate = (path: AppPath | "/reports/landing" | "/upload") => {
    const nextRoute = parsePath(path);
    window.history.pushState({}, "", nextRoute.path);
    setRoute(nextRoute);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // 监听浏览器前进/后退事件
  useEffect(() => {
    const handlePopState = () => setRoute(parsePath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);

    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // 根据当前路由渲染对应的页面内容
  const content = useMemo(() => {
    switch (route.page) {
      case "new-analysis":
        return <NewAnalysisPage onNavigate={navigate} />;
      case "analysis-job":
        return <AnalysisJobPage jobId={route.jobId} onNavigate={navigate} />;
      case "vision":
        return <VisionPage jobId={"jobId" in route ? route.jobId : undefined} onNavigate={navigate} />;
      case "report":
        return <ReportPage jobId={"jobId" in route ? route.jobId : undefined} reportType={route.reportType} onNavigate={navigate} />;
      case "training":
        return <TrainingPage onNavigate={navigate} />;
      case "hardware":
        return <HardwarePage onNavigate={navigate} />;
      case "overview":
      default:
        return <OverviewPage onNavigate={navigate} />;
    }
  }, [route]);

  return (
    <AppShell activePath={route.path} navigation={platformNavigation} onNavigate={navigate}>
      {content}
    </AppShell>
  );
}

function PageFrame({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return (
    <div className={`mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 ${compact ? "py-8" : "py-10 lg:py-12"}`}>
      {children}
    </div>
  );
}

type NavigateFn = (path: AppPath | "/reports/landing" | "/upload") => void;

/**
 * 总览页组件
 */
function OverviewPage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid min-h-[calc(100vh-8rem)] gap-8 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-[#22C55E]/35 bg-[#22C55E]/15 px-4 py-2 text-sm font-bold text-[#168A34]">
            <Sparkles size={16} aria-hidden="true" />
            智能比赛分析 · 视频优先产品原型
          </div>
          <h1 className="mt-7 max-w-4xl text-5xl font-black leading-[0.98] text-[#14241B] sm:text-6xl xl:text-7xl">
            把每一场匹克球比赛，转化为可执行的训练洞察
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            自动拆解发球、接发、第三拍、网前对抗、失误原因与站位趋势，让赛后复盘像教练陪你看视频一样清楚。
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <button className="green-button" onClick={() => onNavigate("/analysis/new")} type="button">
              <Play size={18} fill="currentColor" aria-hidden="true" />
              分析新比赛
            </button>
            <button className="quiet-button" onClick={() => onNavigate("/reports/landing")} type="button">
              查看样例报告
              <ArrowRight size={17} aria-hidden="true" />
            </button>
          </div>

          <div className="mt-10 grid max-w-2xl grid-cols-3 gap-3">
            {[
              ["24", "已索引回合"],
              ["82", "表现评分"],
              ["4", "报告层级"],
            ].map(([value, label]) => (
              <div className="rounded-2xl border border-[#DDE9D6] bg-white/80 p-4 shadow-sm" key={label}>
                <strong className="block text-3xl font-black text-[#168A34]">{value}</strong>
                <span className="mt-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative">
          <div className="absolute -inset-4 rounded-[2.5rem] bg-[#22C55E]/10 blur-3xl" />
          <div className="relative">
            <VideoAnalysisCard
              compact
              labels={videoOverlayLabels.slice(0, 3)}
              match={matchSummary}
              players={playerMarkers}
              timeline={timelineMarkers}
              trajectories={shotTrajectories}
            />
          </div>
        </div>
      </section>

      <section className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {overviewCards.map((card) => (
          <button
            className="sport-card group p-5 text-left transition hover:-translate-y-1 hover:border-[#22C55E]/35"
            key={card.id}
            onClick={() => onNavigate(card.path)}
            type="button"
          >
            <span className="text-xs font-black uppercase tracking-[0.16em] text-[#168A34]">{card.metric}</span>
            <strong className="mt-4 block text-xl font-black text-[#14241B]">{card.title}</strong>
            <p className="mt-3 text-sm leading-6 text-slate-600">{card.body}</p>
            <span className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-slate-700 transition group-hover:text-[#168A34]">
              打开
              <ChevronRight size={16} aria-hidden="true" />
            </span>
          </button>
        ))}
      </section>
    </PageFrame>
  );
}

/**
 * 新建分析任务页组件
 */
function NewAnalysisPage({ onNavigate }: { onNavigate: NavigateFn }) {
  const today = new Date().toISOString().slice(0, 10);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [metadata, setMetadata] = useState({
    matchTitle: "匹克球训练对局",
    venue: "北京体育大学匹克球训练场",
    matchDate: today,
    matchFormat: "doubles" as AnalysisUploadMetadata["matchFormat"],
    cameraAngle: "elevated" as AnalysisUploadMetadata["cameraAngle"],
    athleteLabel: "球馆体验用户 A",
    level: "大众进阶",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = Boolean(
    selectedFile &&
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

  const handleSubmit = async () => {
    if (!selectedFile || !canSubmit) {
      setError("请选择视频并补全比赛信息。");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const job = await createAnalysisJob({
        ...metadata,
        fileName: selectedFile.name,
        fileSize: selectedFile.size,
      });
      onNavigate(`/analysis/${job.id}`);
    } catch {
      setError("创建分析任务失败，请稍后重试。");
    } finally {
      setIsSubmitting(false);
    }
  };

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
            先把上传、任务状态和结果页面跑通。当前会优先连接本地 Python API，后端未启动时使用同结构 mock 结果。
          </p>

          <div className="mt-6 grid gap-3 rounded-3xl border border-[#DDE9D6] bg-white/70 p-4">
            {[
              ["1", "上传视频", "保留原始文件和基础比赛信息"],
              ["2", "视觉分析", "预留 YOLO11 检测与 RTMPose26 姿态识别"],
              ["3", "生成报告", "输出前端可直接渲染的分析 JSON"],
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
            <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed border-[#BFD5B8] bg-[#F5FAF1] p-8 text-center transition hover:border-[#22C55E]/60 hover:bg-[#F9FFF6]">
              <input
                accept="video/*"
                className="sr-only"
                onChange={(event) => {
                  setSelectedFile(event.target.files?.[0] ?? null);
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
                {selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(1)} MB · 本地 mock 不上传原文件` : "支持常见视频格式，真实上传由后端接管"}
              </p>
            </label>
          </div>

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
              <select
                className="field-input"
                onChange={(event) => updateMetadata("matchFormat", event.target.value as AnalysisUploadMetadata["matchFormat"])}
                value={metadata.matchFormat}
              >
                <option value="doubles">双打</option>
                <option value="singles">单打</option>
              </select>
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
            <p className="mt-4 rounded-2xl border border-[#FF4D4F]/30 bg-[#FF4D4F]/10 p-3 text-sm font-semibold text-[#C92A2A]">
              {error}
            </p>
          ) : null}

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button className="green-button" disabled={!canSubmit || isSubmitting} onClick={handleSubmit} type="button">
              {isSubmitting ? "创建中..." : "开始分析"}
              <ArrowRight size={17} aria-hidden="true" />
            </button>
            <button className="quiet-button" onClick={() => onNavigate("/vision")} type="button">
              查看演示工作台
            </button>
          </div>
        </section>
      </section>
    </PageFrame>
  );
}

function Field({ children, label }: { children: ReactNode; label: string }) {
  return (
    <label className="grid gap-2">
      <span className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">{label}</span>
      {children}
    </label>
  );
}

/**
 * 分析任务状态详情页
 */
function AnalysisJobPage({ jobId, onNavigate }: { jobId: string; onNavigate: NavigateFn }) {
  const [job, setJob] = useState<AnalysisJobSummary | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    getAnalysisJob(jobId).then((nextJob) => {
      if (alive) {
        setJob(nextJob);
      }
    });

    return () => {
      alive = false;
    };
  }, [jobId]);

  if (job === undefined) {
    return <StatusState title="正在读取分析任务" body="正在连接后端或本地 mock 任务记录。" onNavigate={onNavigate} />;
  }

  if (!job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，可能是本地记录已清空。`} onNavigate={onNavigate} />;
  }

  const statusCopy = {
    uploaded: "视频已接收",
    queued: "排队中",
    processing: "分析中",
    failed: "分析失败",
    completed: "分析完成",
  } satisfies Record<AnalysisJobSummary["status"], string>;

  const isCompleted = job.status === "completed";
  const isFailed = job.status === "failed";

  return (
    <PageFrame>
      <section className="sport-card overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.42fr] lg:p-8">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-[#168A34]">分析任务</p>
            <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">{statusCopy[job.status]}</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
              {job.metadata.matchTitle} · {job.metadata.fileName} · {job.metadata.venue}
            </p>
            <p className="mt-2 text-sm font-semibold text-slate-500">任务 ID：{job.id}</p>
          </div>
          <div className="rounded-3xl border border-[#22C55E]/25 bg-[#22C55E]/10 p-6">
            <span className="text-sm font-bold text-[#168A34]">当前进度</span>
            <strong className="mt-4 block text-5xl font-black text-[#13A12C]">{job.progress}%</strong>
            <div className="mt-5 h-2 rounded-full bg-[#DFEADA]">
              <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${job.progress}%` }} />
            </div>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">任务信息</p>
          <div className="mt-5 grid gap-3 text-sm">
            {[
              ["比赛形式", job.metadata.matchFormat === "doubles" ? "双打" : "单打"],
              ["拍摄角度", cameraAngleLabel(job.metadata.cameraAngle)],
              ["球员/队伍", job.metadata.athleteLabel],
              ["水平", job.metadata.level],
              ["创建时间", new Date(job.createdAt).toLocaleString()],
            ].map(([label, value]) => (
              <div className="flex justify-between gap-4 rounded-2xl bg-[#F5FAF1] p-3" key={label}>
                <span className="text-slate-500">{label}</span>
                <strong className="text-right text-[#14241B]">{value}</strong>
              </div>
            ))}
          </div>
          {isFailed ? (
            <p className="mt-4 rounded-2xl border border-[#FF4D4F]/30 bg-[#FF4D4F]/10 p-3 text-sm font-semibold text-[#C92A2A]">
              {job.errorMessage ?? "分析任务失败，请重新上传或检查后端日志。"}
            </p>
          ) : null}
        </article>

        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">分析阶段</p>
          <div className="mt-5 grid gap-3">
            {job.stages.map((stage) => (
              <div className="flex gap-3 rounded-2xl border border-[#DDE9D6] bg-white/70 p-4" key={stage.id}>
                <span className={`mt-1 size-3 shrink-0 rounded-full ${stage.status === "done" ? "bg-[#22C55E]" : stage.status === "failed" ? "bg-[#FF4D4F]" : stage.status === "active" ? "bg-[#FF9500]" : "bg-slate-300"}`} />
                <div>
                  <strong className="text-[#14241B]">{stage.label}</strong>
                  <p className="mt-1 text-sm leading-6 text-slate-600">{stage.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="mt-6 sport-card p-5 sm:p-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">结果入口</p>
            <h2 className="mt-2 text-2xl font-black text-[#14241B]">
              {isCompleted ? "报告已经生成" : "等待分析完成后生成报告"}
            </h2>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              className="green-button px-4 py-2.5"
              disabled={!isCompleted}
              onClick={() => onNavigate(`/analysis/${job.id}/vision`)}
              type="button"
            >
              打开视频分析
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            {reportActions.map((action) => (
              <button
                className="quiet-button px-4 py-2.5"
                disabled={!isCompleted}
                key={action.type}
                onClick={() => onNavigate(`/analysis/${job.id}/reports/${action.type}`)}
                type="button"
              >
                {action.title}
              </button>
            ))}
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
              重新上传
            </button>
          </div>
        </div>
      </section>
    </PageFrame>
  );
}

function StatusState({
  body,
  onNavigate,
  title,
}: {
  body: string;
  onNavigate: NavigateFn;
  title: string;
}) {
  return (
    <PageFrame>
      <section className="sport-card p-8 text-center">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">分析任务</p>
        <h1 className="mt-3 text-4xl font-black text-[#14241B]">{title}</h1>
        <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-600">{body}</p>
        <div className="mt-6 flex justify-center gap-3">
          <button className="green-button" onClick={() => onNavigate("/analysis/new")} type="button">
            上传新视频
          </button>
          <button className="quiet-button" onClick={() => onNavigate("/vision")} type="button">
            查看演示
          </button>
        </div>
      </section>
    </PageFrame>
  );
}

function cameraAngleLabel(angle: AnalysisUploadMetadata["cameraAngle"]) {
  const labels: Record<AnalysisUploadMetadata["cameraAngle"], string> = {
    baseline: "底线视角",
    sideline: "边线视角",
    elevated: "高位俯拍",
    unknown: "未知",
  };

  return labels[angle];
}

function useAnalysisReport(jobId?: string) {
  const [loadedResult, setLoadedResult] = useState<{
    job: AnalysisJobSummary | null;
    jobId: string;
    report: AnalysisReport | null;
  } | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let alive = true;

    Promise.all([getAnalysisJob(jobId), getAnalysisReport(jobId)]).then(([nextJob, nextReport]) => {
      if (alive) {
        setLoadedResult({ job: nextJob, jobId, report: nextReport });
      }
    });

    return () => {
      alive = false;
    };
  }, [jobId]);

  if (!jobId) {
    return { job: null, report: demoReport };
  }

  if (loadedResult?.jobId !== jobId) {
    return { job: undefined, report: undefined };
  }

  return { job: loadedResult.job, report: loadedResult.report };
}

/**
 * 视觉分析工作台页组件
 */
function VisionPage({ jobId, onNavigate }: { jobId?: string; onNavigate: NavigateFn }) {
  const { job, report } = useAnalysisReport(jobId);

  if (jobId && (job === undefined || report === undefined)) {
    return <StatusState title="正在加载视觉分析" body="正在读取该任务生成的分析报告。" onNavigate={onNavigate} />;
  }

  if (jobId && !job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，无法打开视觉分析。`} onNavigate={onNavigate} />;
  }

  if (job && job.status !== "completed") {
    return (
      <StatusState
        title={job.status === "failed" ? "分析任务失败" : "视觉分析尚未生成"}
        body={job.status === "failed" ? job.errorMessage ?? "请重新上传或检查后端日志。" : "任务还在排队或处理中，完成后会开放视频分析工作台。"}
        onNavigate={onNavigate}
      />
    );
  }

  const analysis = report ?? demoReport;
  const sourceLabel = analysis.source === "demo" ? "样例数据" : `任务 ${analysis.jobId}`;
  const reportPath = (type: ReportType) =>
    (analysis.jobId ? `/analysis/${analysis.jobId}/reports/${type}` : `/reports/${type}`) as AppPath;

  return (
    <PageFrame>
      <section className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Camera size={16} aria-hidden="true" />
            智能视频分析
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">比赛分析工作台</h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
            视频回放是入口，报告和训练建议是下一步。当前数据来源：{sourceLabel}。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {analysis.reportActions.map((action) => (
            <button
              className="quiet-button px-4 py-2.5"
              key={action.type}
              onClick={() => onNavigate(reportPath(action.type))}
              type="button"
            >
              {action.title}
            </button>
          ))}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <VideoAnalysisCard
          labels={analysis.videoOverlayLabels}
          match={analysis.match}
          players={analysis.playerMarkers}
          timeline={analysis.timelineMarkers}
          trajectories={analysis.shotTrajectories}
        />
        <aside className="grid gap-5">
          <CoachNotesCard notes={analysis.coachNotes} />
          <HighlightsCard highlights={analysis.highlights} onNavigate={onNavigate} reportPath={reportPath} />
        </aside>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {analysis.reportActions.map((action) => (
          <button
            className="sport-card group p-5 text-left transition hover:-translate-y-1 hover:border-[#22C55E]/35"
            key={action.type}
            onClick={() => onNavigate(reportPath(action.type))}
            type="button"
          >
            <span className="grid size-10 place-items-center rounded-2xl border border-[#22C55E]/25 bg-[#22C55E]/12 text-[#168A34]">
              <LineChart size={18} aria-hidden="true" />
            </span>
            <strong className="mt-4 block text-lg font-black text-[#14241B]">{action.title}</strong>
            <p className="mt-2 text-sm leading-6 text-slate-600">{action.description}</p>
            <span className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-slate-700 group-hover:text-[#168A34]">
              查看报告
              <ArrowRight size={15} aria-hidden="true" />
            </span>
          </button>
        ))}
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {analysis.dashboardMetrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      <div className="mt-6 grid gap-6">
        <ShotExplorer filters={shotFilters} landingPoints={analysis.session.landingPoints} shots={analysis.shotRows} />
        <SkillRatings ratings={analysis.skillRatings} />
        <RecommendedDrills drills={analysis.drillRecommendations} onNavigate={onNavigate} />
        <ProgressChart points={analysis.progressPoints} />
      </div>
    </PageFrame>
  );
}

function CoachNotesCard({ notes }: { notes: AnalysisReport["coachNotes"] }) {
  return (
    <section className="sport-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">智能教练笔记</p>
          <h2 className="mt-2 text-xl font-black text-[#14241B]">可执行洞察</h2>
        </div>
        <Brain className="text-[#168A34]" size={22} aria-hidden="true" />
      </div>
      <div className="mt-5 grid gap-3">
        {notes.map((note) => {
          const style = toneStyles[note.tone];

          return (
            <article className={`rounded-2xl border p-4 ${style.border} ${style.bg}`} key={note.id}>
              <div className="flex items-start gap-3">
                <span className={`mt-1 size-2.5 shrink-0 rounded-full ${style.dot}`} />
                <div>
                  <strong className={`text-sm ${style.text}`}>{note.title}</strong>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{note.body}</p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function HighlightsCard({
  highlights,
  onNavigate,
  reportPath,
}: {
  highlights: AnalysisReport["highlights"];
  onNavigate: NavigateFn;
  reportPath: (type: ReportType) => AppPath;
}) {
  return (
    <section className="sport-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">关键片段</p>
          <h2 className="mt-2 text-xl font-black text-[#14241B]">关键片段</h2>
        </div>
        <Timer className="text-[#D9FF3F]" size={22} aria-hidden="true" />
      </div>
      <div className="mt-5 grid gap-3">
        {highlights.map((highlight) => {
          const style = toneStyles[highlight.tone];

          return (
            <button
              className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4 text-left transition hover:border-[#22C55E]/35 hover:bg-[#F9FFF6]"
              key={highlight.id}
              onClick={() => onNavigate(highlight.tone === "training" ? "/training" : reportPath("rally"))}
              type="button"
            >
              <div className="flex items-center justify-between gap-3">
                <strong className="text-[#14241B]">{highlight.title}</strong>
                <span className={`rounded-full px-2 py-1 text-xs font-black ${style.bg} ${style.text}`}>{highlight.time}</span>
              </div>
              <p className={`mt-2 text-xs font-black uppercase tracking-[0.12em] ${style.text}`}>
                {highlight.result}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{highlight.description}</p>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/**
 * 详细分析报告页组件
 */
function ReportPage({
  jobId,
  onNavigate,
  reportType,
}: {
  jobId?: string;
  onNavigate: NavigateFn;
  reportType: ReportType;
}) {
  const { job, report } = useAnalysisReport(jobId);

  if (jobId && (job === undefined || report === undefined)) {
    return <StatusState title="正在加载分析报告" body="正在读取该任务生成的报告数据。" onNavigate={onNavigate} />;
  }

  if (jobId && !job) {
    return <StatusState title="没有找到分析任务" body={`任务 ${jobId} 不存在，无法打开报告。`} onNavigate={onNavigate} />;
  }

  if (job && job.status !== "completed") {
    return (
      <StatusState
        title={job.status === "failed" ? "分析任务失败" : "报告尚未生成"}
        body={job.status === "failed" ? job.errorMessage ?? "请重新上传或检查后端日志。" : "任务还在排队或处理中，完成后会开放报告页面。"}
        onNavigate={onNavigate}
      />
    );
  }

  const analysis = report ?? demoReport;
  const definition = analysis.reportDefinitions.find((item) => item.type === reportType) ?? analysis.reportDefinitions[0];
  const backPath = (analysis.jobId ? `/analysis/${analysis.jobId}/vision` : "/vision") as AppPath;

  return (
    <PageFrame>
      <section className="sport-card overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.45fr] lg:p-8">
          <div>
            <button
              className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
              onClick={() => onNavigate(backPath)}
              type="button"
            >
              <ArrowRight className="rotate-180" size={16} aria-hidden="true" />
              返回视频分析
            </button>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-[#168A34]">{definition.eyebrow}</p>
            <h1 className="mt-3 max-w-4xl text-4xl font-black text-[#14241B] sm:text-5xl">{definition.title}</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">{definition.summary}</p>
            <p className="mt-3 text-sm font-semibold text-slate-500">
              {analysis.source === "demo" ? "样例报告" : `${analysis.metadata.matchTitle} · ${analysis.metadata.fileName} · ${analysis.reportId}`}
            </p>
          </div>
          <div className="rounded-3xl border border-[#22C55E]/25 bg-[#22C55E]/10 p-6">
            <span className="text-sm font-bold text-[#168A34]">{definition.heroMetricLabel}</span>
            <strong className="mt-4 block text-5xl font-black text-[#13A12C]">{definition.heroMetric}</strong>
            <button className="mt-6 green-button w-full" onClick={() => onNavigate("/training")} type="button">
              查看相关训练
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {definition.metrics.map((metric) => (
          <MetricCard key={`${definition.type}-${metric.id}`} metric={metric} />
        ))}
      </section>

      <div className="mt-6">
        <ReportVisualization
          definition={definition}
          diagnoses={analysis.diagnoses}
          landingPoints={analysis.session.landingPoints}
          movementPath={analysis.session.movementPath}
          rallies={analysis.session.rallies}
          routes={analysis.session.routes}
        />
      </div>

      <section className="mt-6 grid gap-4 lg:grid-cols-[0.78fr_1.22fr]">
        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">训练承接</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">{definition.trainingLink}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            这份报告的价值不止在解释数据，还要把弱项直接转成下一次训练任务。
          </p>
          <button className="mt-5 green-button" onClick={() => onNavigate("/training")} type="button">
            打开训练计划
            <Dumbbell size={17} aria-hidden="true" />
          </button>
        </article>
        <div className="grid gap-4 md:grid-cols-2">
          {definition.insights.map((insight) => {
            const style = toneStyles[insight.tone];

            return (
              <article className={`rounded-2xl border p-5 ${style.border} ${style.bg}`} key={insight.id}>
                <strong className={`text-base ${style.text}`}>{insight.title}</strong>
                <p className="mt-3 text-sm leading-6 text-slate-600">{insight.body}</p>
              </article>
            );
          })}
        </div>
      </section>
    </PageFrame>
  );
}

function RecommendedDrills({
  drills = drillRecommendations,
  onNavigate,
}: {
  drills?: DrillRecommendation[];
  onNavigate: NavigateFn;
}) {
  return (
    <section className="sport-card p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">推荐训练</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">数据变成训练任务</h2>
        </div>
        <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/training")} type="button">
          查看完整计划
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
      <DrillGrid drills={drills} onNavigate={onNavigate} />
    </section>
  );
}

function DrillGrid({
  drills,
  onNavigate,
}: {
  drills: DrillRecommendation[];
  onNavigate: NavigateFn;
}) {
  return (
    <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {drills.map((drill) => (
        <article
          className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4 transition hover:-translate-y-1 hover:border-[#22C55E]/35 hover:bg-[#F9FFF6]"
          key={drill.id}
        >
          <div className="flex items-start justify-between gap-3">
            <span className="rounded-full border border-[#22C55E]/30 bg-[#22C55E]/12 px-2.5 py-1 text-xs font-black text-[#168A34]">
              {drill.difficulty}
            </span>
            <span className="text-xs font-bold text-slate-500">{drill.duration}</span>
          </div>
          <h3 className="mt-4 text-lg font-black text-[#14241B]">{drill.title}</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">{drill.goal}</p>
          <p className="mt-4 rounded-2xl bg-[#F0F6EA] p-3 text-xs leading-5 text-slate-600">{drill.evidence}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="green-button px-3 py-2 text-xs" onClick={() => onNavigate("/training")} type="button">
              加入训练计划
            </button>
            <button
              className="quiet-button px-3 py-2 text-xs"
              onClick={() => onNavigate(`/reports/${drill.linkedReport}`)}
              type="button"
            >
              查看依据
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

/**
 * 训练建议页组件
 */
function TrainingPage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Dumbbell size={16} aria-hidden="true" />
            训练与进展
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">训练建议页</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            每个建议都绑定报告证据，让球员知道为什么练、怎么练、下一次如何验证。
          </p>
        </div>
        <div className="sport-card p-5">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="text-[#168A34]" size={24} aria-hidden="true" />
            <div>
              <strong className="text-xl font-black text-[#14241B]">学习 · 练习 · 复测</strong>
              <p className="mt-1 text-sm text-slate-600">报告问题 → 教学内容 → 训练任务 → 下次复测目标</p>
            </div>
          </div>
          <div className="mt-5 grid gap-3">
            {trainingRecommendations.map((item) => (
              <article className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4" key={item.id}>
                <strong className="text-[#14241B]">{item.title}</strong>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.practiceTask}</p>
                <div className="mt-3 h-2 rounded-full bg-[#DFEADA]">
                  <span
                    className="block h-full rounded-full bg-[#22C55E]"
                    style={{
                      width: `${Math.min(
                        (Math.abs(item.progress.current - item.progress.previous) /
                          Math.abs(item.progress.target - item.progress.previous || 1)) *
                          100,
                        100
                      )}%`,
                    }}
                  />
                </div>
                <p className="mt-2 text-xs font-semibold text-[#168A34]">{item.nextTarget}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6">
        <RecommendedDrills onNavigate={onNavigate} />
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-[0.75fr_1.25fr]">
        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">教学内容</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">教学视频与动作对标占位</h2>
          <div className="mt-5 aspect-video rounded-3xl border border-[#DDE9D6] bg-[#F0F7EA] p-5">
            <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-[#BFD5B8] bg-white/70">
              <div className="text-center">
                <span className="mx-auto grid size-14 place-items-center rounded-full bg-[#22C55E]/15 text-[#168A34]">
                  <Play size={26} fill="currentColor" aria-hidden="true" />
                </span>
                <strong className="mt-4 block text-[#14241B]">反手轻吊动作对标</strong>
                <p className="mt-2 text-sm text-slate-500">真实内容接入前的产品级占位</p>
              </div>
            </div>
          </div>
        </article>
        <ProgressChart points={progressPoints} />
      </section>
    </PageFrame>
  );
}

/**
 * 硬件融合预览页组件（二期规划）
 */
function HardwarePage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Cpu size={16} aria-hidden="true" />
            二期硬件融合
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">{hardwarePreview.phaseLabel}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">{hardwarePreview.disclaimer}</p>
          <button className="mt-7 quiet-button" onClick={() => onNavigate("/vision")} type="button">
            返回视频分析
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="sport-card p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">TENG 阵列</p>
              <h2 className="mt-2 text-2xl font-black text-[#14241B]">3x3 甜区触点分布</h2>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-[#22C55E]/30 bg-[#22C55E]/12 px-3 py-2 text-xs font-black text-[#168A34]">
              <ShieldCheck size={14} aria-hidden="true" />
              模拟数据
            </span>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-3 rounded-[2rem] border border-[#DDE9D6] bg-[#F0F7EA] p-4">
            {hardwarePreview.sweetZone.map((cell) => (
              <span
                className={`aspect-square rounded-2xl border ${
                  cell.id === hardwarePreview.highlightedCellId
                    ? "border-[#22C55E] bg-[#22C55E]"
                    : "border-[#DDE9D6] bg-[#22C55E]/10"
                }`}
                key={cell.id}
                style={{ opacity: Math.max(cell.intensity, 0.22) }}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {hardwarePreview.metrics.map((metric) => (
          <article className="sport-card p-5 transition hover:-translate-y-1 hover:border-[#22C55E]/35" key={metric.id}>
            <Gauge className="text-[#168A34]" size={20} aria-hidden="true" />
            <span className="mt-4 block text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{metric.label}</span>
            <strong className="mt-2 block text-3xl font-black text-[#14241B]">{metric.value}</strong>
            <p className="mt-3 text-sm leading-6 text-slate-600">{metric.detail}</p>
          </article>
        ))}
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-2">
        {hardwarePreview.fusionPoints.map((point) => (
          <article className="sport-card p-5 sm:p-6" key={point.insight}>
            <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-center">
              <FusionBlock icon={<Camera size={18} aria-hidden="true" />} label="视觉" value={point.visual} />
              <Zap className="hidden text-[#D9FF3F] md:block" size={22} aria-hidden="true" />
              <FusionBlock icon={<Radar size={18} aria-hidden="true" />} label="球拍" value={point.sensor} />
            </div>
            <p className="mt-5 rounded-2xl border border-[#22C55E]/25 bg-[#22C55E]/12 p-4 text-sm font-semibold leading-6 text-[#168A34]">
              {point.insight}
            </p>
          </article>
        ))}
      </section>

      <section className="mt-6 sport-card p-5 sm:p-6">
        <div className="flex items-start gap-4">
          <BadgeCheck className="mt-1 text-[#168A34]" size={23} aria-hidden="true" />
          <div>
            <h2 className="text-2xl font-black text-[#14241B]">未来数据替换路径</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              当前页面数值全部来自本地模拟数据。未来真实 TENG 与 IMU 数据可以替换硬件模拟数据对象，
              视觉报告数据仍保持独立，便于做视觉 + 体感融合。
            </p>
          </div>
        </div>
      </section>
    </PageFrame>
  );
}

function FusionBlock({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4">
      <span className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-[#168A34]">
        {icon}
        {label}
      </span>
      <strong className="mt-3 block text-base leading-6 text-[#14241B]">{value}</strong>
    </div>
  );
}

export default App;
