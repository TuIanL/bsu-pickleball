// =============================================================
// PB Vision 报告页 —— 全局 Context + usePbReport() hook
// -------------------------------------------------------------
// 设计 D1：报告主体只允许 canonical player（kind === "player"）。
// 设计 D2：通过 usePlayerReportEvidence 提供证据层，PB 组件统一消费。
// =============================================================
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type {
  AnalysisReport,
  PerformanceSubject,
} from "../types/report";
import type {
  PbReportContextValue,
  PbShotTypeFilter,
  PbStageFilter,
} from "../types/pbReport";
import { usePlayerReportEvidence } from "../hooks/usePlayerReportEvidence";
import { resolveCanonicalPlayerId } from "../evidence/playerIdentity";

const PbReportContext = createContext<PbReportContextValue | null>(null);

/** 从报告里提取 PLAYER-ONLY 主体（kind === "player"），team 永不进入 player report。 */
function getAllPlayerSubjects(
  report: AnalysisReport
): { id: string; name: string; role?: string }[] {
  const subjects = report?.performanceInsights?.subjects as
    | PerformanceSubject[]
    | undefined;
  if (Array.isArray(subjects) && subjects.length) {
    return subjects
      .filter((s) => !!s?.id && s.kind === "player")
      .map((s) => ({ id: s.id, name: s.label || s.id }));
  }
  // 无 player subject → 返回空（调用方显示"暂无可用球员主体"，不把 team/占位当默认）
  return [];
}

// ============== Provider ==============
export function PbReportProvider(props: {
  report: AnalysisReport;
  children: ReactNode;
}) {
  const { report, children } = props;

  const players = useMemo(() => getAllPlayerSubjects(report), [report]);

  const [selectedPlayerId, setSelectedPlayerId] = useState<string>(
    () => players[0]?.id ?? ""
  );
  const [stageFilter, setStageFilter] = useState<PbStageFilter>("third");
  const [typeFilter, setTypeFilter] = useState<PbShotTypeFilter>("all");
  const [qualityThreshold, setQualityThreshold] = useState<number>(70);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(true);
  const toggleDrawer = useCallback(() => {
    setDrawerOpen((v) => !v);
  }, []);

  // 同步：report 变化后，若当前选中的不是合法 player，回退到第一个 player
  const effectivePlayerId = useMemo(() => {
    if (players.some((p) => p.id === selectedPlayerId)) return selectedPlayerId;
    return players[0]?.id ?? "";
  }, [players, selectedPlayerId]);

  const selectedSubject = useMemo(() => {
    return players.find((p) => p.id === effectivePlayerId) ?? players[0];
  }, [players, effectivePlayerId]);

  // 证据层（IO hook）：jobId 传 report.jobId，供后续 artifact 抓取
  const evidence = usePlayerReportEvidence(report.jobId, report, effectivePlayerId || resolveCanonicalPlayerId(report.playerMarkers?.[0]?.id ?? "", null) || "");

  const value: PbReportContextValue = {
    report,
    selectedPlayerId: effectivePlayerId,
    setSelectedPlayerId,
    stageFilter,
    setStageFilter,
    typeFilter,
    setTypeFilter,
    qualityThreshold,
    setQualityThreshold,
    drawerOpen,
    setDrawerOpen,
    toggleDrawer,
    selectedSubject,
    evidence,
  };

  if (!effectivePlayerId) {
    // 无 player subject：只显示空态，不渲染整份报告（避免出现"球员 0 击球"的幻影主体）
    return (
      <PbReportContext.Provider value={value}>
        <div className="pb-vision-theme flex min-h-[40vh] items-center justify-center p-8">
          <div className="pb-card max-w-md p-6 text-center">
            <div className="text-lg font-bold text-[var(--pb-text-primary,#111827)]">
              暂无可用球员主体
            </div>
            <div className="mt-2 text-sm text-[var(--pb-text-secondary,#6b7280)]">
              本次分析未识别到具体球员，无法生成球员报告。
            </div>
          </div>
        </div>
      </PbReportContext.Provider>
    );
  }

  return (
    <PbReportContext.Provider value={value}>
      {children}
    </PbReportContext.Provider>
  );
}

// ============== Hook ==============
export function usePbReport(): PbReportContextValue {
  const ctx = useContext(PbReportContext);
  if (!ctx) {
    throw new Error(
      "usePbReport() 必须在 <PbReportProvider> 内部使用。请检查 PbVisionReportLayout 是否已挂载 Provider。"
    );
  }
  return ctx;
}

/** 方便非受控场景读取所有球员列表（Player-only） */
export function usePbAllSubjects() {
  const { report } = usePbReport();
  return useMemo(() => getAllPlayerSubjects(report), [report]);
}