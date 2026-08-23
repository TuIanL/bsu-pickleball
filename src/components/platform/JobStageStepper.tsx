import {
  Activity,
  Bone,
  Camera,
  Clock,
  Crosshair,
  FileText,
  FileVideo,
  Film,
  Footprints,
  Frame,
  GitMerge,
  Ruler,
  Scan,
  Upload,
} from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import type { AnalysisStage } from "../../types/report";

/**
 * 任务分析阶段"胶囊式横向 stepper"。
 *
 * 将 API 返回的当前模式阶段压缩为一行可横向滑动的胶囊节点（图标 + 短标签 + 连接线），
 * 已完成=绿、当前=橙呼吸、失败=红、跳过=灰、待办=浅灰；容器自动把
 * active（无则 failed）节点滚动到可视区，默认聚焦当前运行阶段。
 *
 * `compact` 模式（任务列表卡使用）：只渲染状态圆点，不渲染图标与文字。
 */
export function JobStageStepper({
  stages,
  compact = false,
  ariaLabel = "分析阶段进度",
  className = "",
}: {
  stages: AnalysisStage[];
  compact?: boolean;
  ariaLabel?: string;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const targetIndex = stages.findIndex(
    (stage) => stage.status === "active" || stage.status === "failed",
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container || targetIndex < 0) {
      return;
    }
    const target = stages[targetIndex];
    const node = nodeRefs.current[target.id];
    if (!node) {
      return;
    }
    const prefersReducedMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const targetLeft = Math.max(
      0,
      node.offsetLeft - container.clientWidth / 2 + node.clientWidth / 2,
    );
    if (typeof container.scrollTo === "function") {
      container.scrollTo({
        left: targetLeft,
        behavior: prefersReducedMotion ? "auto" : "smooth",
      });
    } else {
      container.scrollLeft = targetLeft;
    }
  }, [stages, targetIndex]);

  return (
    <div
      aria-label={ariaLabel}
      className={`scrollbar-none overflow-x-auto overscroll-x-contain scroll-smooth ${className}`}
      data-testid="job-stage-stepper"
      ref={containerRef}
      role="list"
    >
      <ol
        className={`flex w-max items-center ${compact ? "gap-1.5" : "gap-1"}`}
        style={{ minWidth: "100%" }}
      >
        {stages.map((stage, index) => {
          const isTarget = index === targetIndex;
          return (
            <li className="flex items-center" key={stage.id}>
              {index > 0 ? (
                <span
                  aria-hidden="true"
                  className={`h-px w-2.5 shrink-0 sm:w-3 ${
                    stage.status === "pending"
                      ? "bg-[#DCE5D6]"
                      : stage.status === "failed"
                        ? "bg-[#FF4D4F]/60"
                        : "bg-[#22C55E]/50"
                  }`}
                />
              ) : null}
              {compact ? (
                <div
                  className={`size-2.5 shrink-0 rounded-full ${stageDotClass(stage.status)} ${
                    isTarget ? "scale-150 shadow-[0_0_8px_rgba(255,149,0,0.6)]" : ""
                  }`}
                  data-stage-active={isTarget ? "true" : undefined}
                  data-stage-status={stage.status}
                  data-testid="stage-dot"
                  ref={(node) => {
                    nodeRefs.current[stage.id] = node;
                  }}
                  role="listitem"
                  title={stage.label}
                />
              ) : (
                <div
                  className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-1 text-[0.7rem] font-bold transition-colors sm:px-2.5 ${
                    isTarget
                      ? "scale-110 border-[#FF9500]/50 bg-[#FF9500]/12 text-[#A45A00] shadow-[0_0_16px_rgba(255,149,0,0.25)] stage-pulse"
                      : stageCapusuleClass(stage.status)
                  }`}
                  data-stage-active={isTarget ? "true" : undefined}
                  data-stage-status={stage.status}
                  data-testid="stage-capsule"
                  ref={(node) => {
                    nodeRefs.current[stage.id] = node;
                  }}
                  role="listitem"
                  title={stage.label}
                >
                  <StageIcon stageId={stage.id} status={stage.status} />
                  <span className="max-w-24 truncate">{stage.label}</span>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function stageDotClass(status: AnalysisStage["status"]): string {
  switch (status) {
    case "done":
    case "partial":
      return "bg-[#22C55E]";
    case "active":
      return "bg-[#FF9500] stage-pulse";
    case "failed":
      return "bg-[#FF4D4F]";
    case "canceled":
      return "bg-slate-500";
    case "skipped":
    case "unavailable":
      return "bg-slate-400";
    default:
      return "bg-slate-300";
  }
}

function stageCapusuleClass(status: AnalysisStage["status"]): string {
  switch (status) {
    case "done":
    case "partial":
      return "border-[#22C55E]/35 bg-[#22C55E]/10 text-[#168A34]";
    case "active":
      return "border-[#FF9500]/50 bg-[#FF9500]/12 text-[#A45A00] stage-pulse";
    case "failed":
      return "border-[#FF4D4F]/40 bg-[#FF4D4F]/10 text-[#C92A2A]";
    case "canceled":
      return "border-slate-400/40 bg-slate-100 text-slate-600";
    case "skipped":
    case "unavailable":
      return "border-slate-300/60 bg-slate-50 text-slate-400";
    default:
      return "border-[#DDE9D6] bg-white/70 text-slate-400";
  }
}

function StageIcon({
  stageId,
  status,
}: {
  stageId: string;
  status: AnalysisStage["status"];
}) {
  if (status === "done" || status === "partial") {
    return <CheckDot />;
  }
  const icon = STAGE_ICONS[stageId] ?? <Frame size={13} aria-hidden="true" />;
  return <span aria-hidden="true">{icon}</span>;
}

function CheckDot() {
  return (
    <svg aria-hidden="true" className="size-3" fill="none" viewBox="0 0 12 12">
      <path
        d="M2.5 6.2 5 8.7l4.5-5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.6"
      />
    </svg>
  );
}

const STAGE_ICONS: Record<string, ReactNode> = {
  upload: <Upload size={13} aria-hidden="true" />,
  queue: <Clock size={13} aria-hidden="true" />,
  calibration: <Ruler size={13} aria-hidden="true" />,
  "video-read": <FileVideo size={13} aria-hidden="true" />,
  "frame-sampling": <Frame size={13} aria-hidden="true" />,
  detection: <Scan size={13} aria-hidden="true" />,
  pose: <Bone size={13} aria-hidden="true" />,
  tracking: <Footprints size={13} aria-hidden="true" />,
  projection: <Crosshair size={13} aria-hidden="true" />,
  metrics: <Activity size={13} aria-hidden="true" />,
  visualization: <Film size={13} aria-hidden="true" />,
  report: <FileText size={13} aria-hidden="true" />,
  "multiview-input-check": <Ruler size={13} aria-hidden="true" />,
  "multiview-view-a": <Camera size={13} aria-hidden="true" />,
  "multiview-view-b": <Camera size={13} aria-hidden="true" />,
  "multiview-fusion": <GitMerge size={13} aria-hidden="true" />,
  "multiview-joint": <Activity size={13} aria-hidden="true" />,
  "multiview-metrics": <Activity size={13} aria-hidden="true" />,
  "multiview-visualization": <Film size={13} aria-hidden="true" />,
  "multiview-report": <FileText size={13} aria-hidden="true" />,
};
