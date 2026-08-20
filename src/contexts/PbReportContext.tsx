// =============================================================
// PB Vision 报告页 —— 全局 Context + usePbReport() hook
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
  PlayerInfo,
  TeamSubjectInfo,
} from "../types/report";
import type {
  PbReportContextValue,
  PbShotTypeFilter,
  PbStageFilter,
} from "../types/pbReport";

const PbReportContext = createContext<PbReportContextValue | null>(null);

/** 从报告里安全提取所有球员（兼容 subjects 为数组或 record 两种形态） */
function getAllSubjects(
  report: AnalysisReport
): { id: string; name: string; role?: string }[] {
  const subjects = report?.performanceInsights?.subjects;
  if (!subjects) {
    // fallback: 如果没有 performanceInsights.subjects，取 match/teams 的 teams
    const teams = (report as unknown as { teams?: unknown }).teams;
    if (Array.isArray(teams)) {
      const arr: { id: string; name: string; role?: string }[] = [];
      for (const t of teams as { players?: PlayerInfo[]; teamName?: string }[]) {
        if (t?.players) {
          for (const p of t.players) {
            if (p?.playerId) arr.push({ id: p.playerId, name: p.name || p.playerId });
          }
        }
      }
      return arr.length
        ? arr
        : [{ id: "T1", name: "球员 1" }, { id: "T2", name: "球员 2" }];
    }
    return [{ id: "T1", name: "球员 1" }, { id: "T2", name: "球员 2" }];
  }

  // subjects 可能是 TeamSubjectInfo[] 或 Record<id, TeamSubjectInfo>
  if (Array.isArray(subjects)) {
    return subjects
      .filter((s) => !!s?.id)
      .map((s) => ({
        id: s.id,
        name: s.name || s.id,
        role: (s as TeamSubjectInfo).role,
      }));
  }

  if (typeof subjects === "object" && subjects !== null) {
    return Object.entries(subjects as Record<string, TeamSubjectInfo>).map(
      ([id, s]) => ({
        id,
        name: s?.name || id,
        role: s?.role,
      })
    );
  }

  return [{ id: "T1", name: "球员 1" }];
}

// ============== Provider ==============
export function PbReportProvider(props: {
  report: AnalysisReport;
  children: ReactNode;
}) {
  const { report, children } = props;

  const subjects = useMemo(() => getAllSubjects(report), [report]);

  const [selectedPlayerId, setSelectedPlayerId] = useState<string>(
    () => subjects[0]?.id ?? "T1"
  );
  const [stageFilter, setStageFilter] = useState<PbStageFilter>("third");
  const [typeFilter, setTypeFilter] = useState<PbShotTypeFilter>("all");
  const [qualityThreshold, setQualityThreshold] = useState<number>(70);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(true);
  const toggleDrawer = useCallback(() => {
    setDrawerOpen((v) => !v);
  }, []);

  const selectedSubject = useMemo(() => {
    return subjects.find((s) => s.id === selectedPlayerId) ?? subjects[0];
  }, [subjects, selectedPlayerId]);

  const value: PbReportContextValue = {
    report,
    selectedPlayerId,
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
  };

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

/** 方便非受控场景读取所有球员列表 */
export function usePbAllSubjects() {
  const { report } = usePbReport();
  return useMemo(() => getAllSubjects(report), [report]);
}
