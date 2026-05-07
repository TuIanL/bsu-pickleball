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
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell } from "./components/platform/AppShell";
import { MetricCard } from "./components/platform/MetricCard";
import { ProgressChart } from "./components/platform/ProgressChart";
import { ReportVisualization } from "./components/platform/ReportVisualization";
import { ShotExplorer } from "./components/platform/ShotExplorer";
import { SkillRatings } from "./components/platform/SkillRatings";
import { VideoAnalysisCard } from "./components/platform/VideoAnalysisCard";
import {
  coachNotes,
  dashboardMetrics,
  diagnoses,
  drillRecommendations,
  hardwarePreview,
  highlights,
  matchSummary,
  overviewCards,
  platformNavigation,
  playerMarkers,
  progressPoints,
  reportActions,
  reportDefinitions,
  reportSession,
  shotFilters,
  shotRows,
  shotTrajectories,
  skillRatings,
  timelineMarkers,
  trainingRecommendations,
  videoOverlayLabels,
} from "./data/demoData";
import type { AppPath, DrillRecommendation, InsightTone, ReportType } from "./types/report";

type RouteState =
  | { page: "overview"; path: "/" }
  | { page: "vision"; path: "/vision" }
  | { page: "report"; path: `/reports/${ReportType}`; reportType: ReportType }
  | { page: "training"; path: "/training" }
  | { page: "hardware"; path: "/hardware" };

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
  const [route, setRoute] = useState<RouteState>(() => parsePath(window.location.pathname));

  const navigate = (path: AppPath | "/reports/landing") => {
    const nextRoute = parsePath(path);
    window.history.pushState({}, "", nextRoute.path);
    setRoute(nextRoute);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  useEffect(() => {
    const handlePopState = () => setRoute(parsePath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);

    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const content = useMemo(() => {
    switch (route.page) {
      case "vision":
        return <VisionPage onNavigate={navigate} />;
      case "report":
        return <ReportPage reportType={route.reportType} onNavigate={navigate} />;
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

function OverviewPage({ onNavigate }: { onNavigate: (path: AppPath | "/reports/landing") => void }) {
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
            <button className="green-button" onClick={() => onNavigate("/vision")} type="button">
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

function VisionPage({ onNavigate }: { onNavigate: (path: AppPath | "/reports/landing") => void }) {
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
            视频回放是入口，报告和训练建议是下一步。这里用模拟视频层展示球路轨迹、站位热力和关键片段。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {reportActions.map((action) => (
            <button
              className="quiet-button px-4 py-2.5"
              key={action.type}
              onClick={() => onNavigate(action.path)}
              type="button"
            >
              {action.title}
            </button>
          ))}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <VideoAnalysisCard
          labels={videoOverlayLabels}
          match={matchSummary}
          players={playerMarkers}
          timeline={timelineMarkers}
          trajectories={shotTrajectories}
        />
        <aside className="grid gap-5">
          <CoachNotesCard />
          <HighlightsCard onNavigate={onNavigate} />
        </aside>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {reportActions.map((action) => (
          <button
            className="sport-card group p-5 text-left transition hover:-translate-y-1 hover:border-[#22C55E]/35"
            key={action.type}
            onClick={() => onNavigate(action.path)}
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
        {dashboardMetrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      <div className="mt-6 grid gap-6">
        <ShotExplorer filters={shotFilters} landingPoints={reportSession.landingPoints} shots={shotRows} />
        <SkillRatings ratings={skillRatings} />
        <RecommendedDrills onNavigate={onNavigate} />
        <ProgressChart points={progressPoints} />
      </div>
    </PageFrame>
  );
}

function CoachNotesCard() {
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
        {coachNotes.map((note) => {
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

function HighlightsCard({ onNavigate }: { onNavigate: (path: AppPath | "/reports/landing") => void }) {
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
              onClick={() => onNavigate(highlight.tone === "training" ? "/training" : "/reports/rally")}
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

function ReportPage({
  onNavigate,
  reportType,
}: {
  onNavigate: (path: AppPath | "/reports/landing") => void;
  reportType: ReportType;
}) {
  const definition = reportDefinitions.find((item) => item.type === reportType) ?? reportDefinitions[0];

  return (
    <PageFrame>
      <section className="sport-card overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.45fr] lg:p-8">
          <div>
            <button
              className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-[#168A34]"
              onClick={() => onNavigate("/vision")}
              type="button"
            >
              <ArrowRight className="rotate-180" size={16} aria-hidden="true" />
              返回视频分析
            </button>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-[#168A34]">{definition.eyebrow}</p>
            <h1 className="mt-3 max-w-4xl text-4xl font-black text-[#14241B] sm:text-5xl">{definition.title}</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">{definition.summary}</p>
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
          diagnoses={diagnoses}
          landingPoints={reportSession.landingPoints}
          movementPath={reportSession.movementPath}
          rallies={reportSession.rallies}
          routes={reportSession.routes}
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

function RecommendedDrills({ onNavigate }: { onNavigate: (path: AppPath | "/reports/landing") => void }) {
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
      <DrillGrid drills={drillRecommendations} onNavigate={onNavigate} />
    </section>
  );
}

function DrillGrid({
  drills,
  onNavigate,
}: {
  drills: DrillRecommendation[];
  onNavigate: (path: AppPath | "/reports/landing") => void;
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

function TrainingPage({ onNavigate }: { onNavigate: (path: AppPath | "/reports/landing") => void }) {
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

function HardwarePage({ onNavigate }: { onNavigate: (path: AppPath | "/reports/landing") => void }) {
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
