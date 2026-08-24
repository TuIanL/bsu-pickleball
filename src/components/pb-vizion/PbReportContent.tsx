// =============================================================
// PbReportContent - PB 视觉报告内容（无 Drawer / 无独立导航）
// -------------------------------------------------------------
// 四层职责中的「PB 视觉内容」层：
//   复用了 PbReportProvider + 各 Pb 视觉子模块，
//   不挂 PbPlayerDrawer / PbDrawerExpander / 独立 spacing。
//   可被 Workspace 报告 view 直接挂载，也可被 standalone shell 嵌套。
// =============================================================
import { Suspense, lazy, type ReactNode } from "react";
import type { AnalysisReport, ReconstructedBallTrajectoryArtifact } from "../../types/report";
import { PbReportProvider, usePbReport } from "../../contexts/PbReportContext";

function AsyncPlaceholder({ title }: { title: string }): ReactNode {
  return (
    <div className="pb-card p-6">
      <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--pb-text-muted,#9ca3af)]">
        {title}
      </div>
      <div className="flex h-32 animate-pulse items-center justify-center rounded-lg bg-[var(--pb-page-bg,#f0f4f2)] text-sm text-[var(--pb-text-muted,#9ca3af)]">
        组件加载中…
      </div>
    </div>
  );
}

const PbPlayerHeaderCard = lazy(() =>
  import("./PbPlayerHeaderCard").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="球员顶卡" />,
  }))
);
const PbPlayerSelector = lazy(() =>
  import("./PbPlayerSelector").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="球员切换" />,
  }))
);

/** 设计 D4：仅 demo 源显示"演示数据"标注（fail-closed 的可见反馈）。 */
function DemoDataBadge() {
  const { report } = usePbReport();
  if (report.source !== "demo") return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
      演示数据
    </span>
  );
}
const Pb3DCourtCard = lazy(() =>
  import("./Pb3DCourtCard").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="3D 球场" />,
  }))
);
const PbFilterToolbar = lazy(() =>
  import("./PbFilterToolbar").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="筛选工具栏" />,
  }))
);
const PbSkillRatingSection = lazy(() =>
  import("./PbSkillRatingSection").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="技能评分" />,
  }))
);
const PbCourtCoverage = lazy(() =>
  import("./PbCourtCoverage").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="场地覆盖" />,
  }))
);
const PbServesReturns = lazy(() =>
  import("./PbServesReturns").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="发球与接发" />,
  }))
);
const PbCoachInsight = lazy(() =>
  import("./PbCoachInsight").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="教练洞察" />,
  }))
);
const PbLegalThirds = lazy(() =>
  import("./PbLegalThirds").then((m) => ({ default: m.default })).catch(() => ({
    default: () => <AsyncPlaceholder title="合法第三拍" />,
  }))
);

export default function PbReportContent({ report, trajectoryArtifact }: { report: AnalysisReport; trajectoryArtifact?: ReconstructedBallTrajectoryArtifact | null }) {
  return (
    <PbReportProvider report={report} trajectoryArtifact={trajectoryArtifact}>
      <div className="pb-vision-theme min-h-full w-full" style={{ background: "var(--pb-page-bg, #f0f4f2)" }}>
        <div className="mx-auto flex max-w-[1400px] flex-col gap-6 px-6 py-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <PbPlayerSelector />
            <DemoDataBadge />
          </div>
          <Suspense fallback={<AsyncPlaceholder title="球员顶卡" />}>
            <PbPlayerHeaderCard />
          </Suspense>
          <Suspense fallback={<AsyncPlaceholder title="3D 球场" />}>
            <Pb3DCourtCard />
          </Suspense>
          <Suspense fallback={<AsyncPlaceholder title="筛选工具栏" />}>
            <PbFilterToolbar />
          </Suspense>
          <Suspense fallback={<AsyncPlaceholder title="技能评分" />}>
            <PbSkillRatingSection />
          </Suspense>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Suspense fallback={<AsyncPlaceholder title="场地覆盖" />}>
              <PbCourtCoverage />
            </Suspense>
            <Suspense fallback={<AsyncPlaceholder title="发球与接发" />}>
              <PbServesReturns />
            </Suspense>
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Suspense fallback={<AsyncPlaceholder title="教练洞察" />}>
              <PbCoachInsight />
            </Suspense>
            <Suspense fallback={<AsyncPlaceholder title="合法第三拍" />}>
              <PbLegalThirds />
            </Suspense>
          </div>
        </div>
      </div>
    </PbReportProvider>
  );
}
