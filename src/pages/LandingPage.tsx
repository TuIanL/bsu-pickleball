import { Camera, Sparkles, Upload, Zap } from "lucide-react";
import type { ReactNode } from "react";
import { VideoAnalysisCard } from "../components/platform/VideoAnalysisCard";
import {
  matchSummary,
  playerMarkers,
  timelineMarkers,
  videoOverlayLabels,
} from "../data/demoData";
import type { NavigateFn } from "../app/navigationTypes";

function PageFrame({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return (
    <div className={`mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 ${compact ? "py-8" : "py-10 lg:py-12"}`}>
      {children}
    </div>
  );
}

export function LandingPage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      {/* Hero 区 */}
      <section className="grid min-h-[calc(100vh-8rem)] gap-8 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-[#22C55E]/35 bg-[#22C55E]/15 px-4 py-2 text-sm font-bold text-[#168A34]">
            <Sparkles size={16} aria-hidden="true" />
            智能比赛分析 · 真实产品与科研平台
          </div>
          <h1 className="mt-7 max-w-4xl text-5xl font-black leading-[0.98] text-[#14241B] sm:text-6xl xl:text-7xl">
            把每一场匹克球比赛，转化为可执行的训练洞察
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            上传已有比赛视频或连接摄像头现场录制，系统自动完成人员检测、姿态叠加、移动轨迹和球场热力图分析。
          </p>

          {/* CTA 入口 */}
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <button
              className="green-button flex items-center gap-2 px-8 py-4 text-lg font-bold"
              onClick={() => onNavigate("/capture")}
              type="button"
            >
              <Camera size={22} aria-hidden="true" />
              进入开始使用
            </button>
          </div>

          {/* 统计卡片 */}
          <div className="mt-10 grid max-w-2xl grid-cols-3 gap-3">
            {[
              ["20×44", "标准球场"],
              ["82", "表现评分"],
              ["2", "报告类型"],
            ].map(([value, label]) => (
              <div className="rounded-2xl border border-[#DDE9D6] bg-white/80 p-4 shadow-sm" key={label}>
                <strong className="block text-3xl font-black text-[#168A34]">{value}</strong>
                <span className="mt-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 右侧视频分析卡片 */}
        <div className="relative">
          <div className="absolute -inset-4 rounded-[2.5rem] bg-[#22C55E]/10 blur-3xl" />
          <div className="relative">
            <VideoAnalysisCard
              compact
              labels={videoOverlayLabels.slice(0, 3)}
              match={matchSummary}
              players={playerMarkers}
              timeline={timelineMarkers}
            />
          </div>
        </div>
      </section>

      {/* 能力介绍卡片（纯展示，无跳转） */}
      <section className="mt-12 grid gap-4 md:grid-cols-3">
        <div className="sport-card p-6 text-left">
          <div className="mb-3 grid size-10 place-items-center rounded-xl bg-[#22C55E]/12 text-[#168A34]">
            <Upload size={20} aria-hidden="true" />
          </div>
          <strong className="block text-lg font-black text-[#14241B]">视频上传分析</strong>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            上传已有比赛视频，系统自动完成人员检测、姿态识别、轨迹追踪，生成移动指标、热力图和表现报告。
          </p>
        </div>

        <div className="sport-card p-6 text-left">
          <div className="mb-3 grid size-10 place-items-center rounded-xl bg-[#2F80ED]/12 text-[#2F80ED]">
            <Camera size={20} aria-hidden="true" />
          </div>
          <strong className="block text-lg font-black text-[#14241B]">球场现场采集</strong>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            连接网络摄像头，在球场边完成录制、场边事件标记和现场分析，每次采集都会形成可追踪的任务记录。
          </p>
        </div>

        <div className="sport-card p-6 text-left">
          <div className="mb-3 grid size-10 place-items-center rounded-xl bg-[#FF9500]/12 text-[#FF9500]">
            <Zap size={20} aria-hidden="true" />
          </div>
          <strong className="block text-lg font-black text-[#14241B]">训练结果沉淀</strong>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            每次分析都会保留完整的执行记录和产物，支撑赛后复盘、阶段对比和后续科研产出。
          </p>
        </div>
      </section>
    </PageFrame>
  );
}
