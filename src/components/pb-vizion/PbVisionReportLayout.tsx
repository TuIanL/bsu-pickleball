// =============================================================
// PB Vision 报告页 - 整页容器骨架
// ------------------------------------------------------------
// 2.1 挂载 .pb-vision-theme + PbReportContext.Provider
// 2.3 控制 drawerOpen 与主内容 padding
// 7.1 在主内容区按顺序串联所有子模块（后续在 7.1 任务中填实）
// =============================================================
import { Suspense, type ReactNode } from "react";
import type { AnalysisReport, ReconstructedBallTrajectoryArtifact } from "../../types/report";
import { PbReportProvider, usePbReport } from "../../contexts/PbReportContext";
import PbPlayerDrawer, { PbDrawerExpander } from "./PbPlayerDrawer";

// ---- 子模块引入占位（后续任务中逐步替换为真实组件） ----
// 用 async component 形式避免 circular import；暂时 fallback 到 skeleton
function AsyncPlaceholder({ title }: { title: string }): ReactNode {
  return (
    <div className="pb-card p-6">
      <div className="text-xs font-semibold text-[var(--pb-text-muted,#9ca3af)] uppercase tracking-wider mb-3">
        {title}
      </div>
      <div className="h-32 rounded-lg bg-[var(--pb-page-bg,#f0f4f2)] animate-pulse flex items-center justify-center text-sm text-[var(--pb-text-muted,#9ca3af)]">
        组件加载中…
      </div>
    </div>
  );
}

// 懒加载子组件（等文件创建后即可命中）
import { lazy } from "react";
const PbPlayerHeaderCard = lazy(() =>
  import("./PbPlayerHeaderCard").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="球员顶卡" /> })
  )
);
const PbSkillRatingSection = lazy(() =>
  import("./PbSkillRatingSection").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="技能评分" /> })
  )
);
const Pb3DCourtCard = lazy(() =>
  import("./Pb3DCourtCard").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="3D 球场" /> })
  )
);
const PbFilterToolbar = lazy(() =>
  import("./PbFilterToolbar").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="筛选工具栏" /> })
  )
);
const PbCourtCoverage = lazy(() =>
  import("./PbCourtCoverage").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="场地覆盖" /> })
  )
);
const PbServesReturns = lazy(() =>
  import("./PbServesReturns").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="发球与接发" /> })
  )
);
const PbCoachInsight = lazy(() =>
  import("./PbCoachInsight").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="教练洞察" /> })
  )
);
const PbLegalThirds = lazy(() =>
  import("./PbLegalThirds").then((m) => ({ default: m.default })).catch(
    () => ({ default: () => <AsyncPlaceholder title="合法第三拍" /> })
  )
);

// 主内容区域（读取 drawerOpen 决定 padding）
function MainContentInner({ trajectoryArtifact }: { trajectoryArtifact?: ReconstructedBallTrajectoryArtifact | null }) {
  const { drawerOpen } = usePbReport();
  const pl = drawerOpen ? "pl-[260px]" : "pl-0";

  return (
    <div className={"min-h-screen transition-[padding] duration-200 " + pl}>
      <div className="max-w-[1400px] mx-auto px-6 py-8 flex flex-col gap-6">
        {/* 7.1 按顺序渲染：顶卡 → 3D Court → Filter → Skill Rating → 两列栅格 → 两列栅格 */}
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

        {/* 两列栅格 1：Court Coverage | Serves & Returns */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Suspense fallback={<AsyncPlaceholder title="场地覆盖" />}>
            <PbCourtCoverage />
          </Suspense>
          <Suspense fallback={<AsyncPlaceholder title="发球与接发" />}>
            <PbServesReturns />
          </Suspense>
        </div>

        {/* 两列栅格 2：Coach's Insight | Legal Thirds */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Suspense fallback={<AsyncPlaceholder title="教练洞察" />}>
            <PbCoachInsight />
          </Suspense>
          <Suspense fallback={<AsyncPlaceholder title="合法第三拍" />}>
            <PbLegalThirds />
          </Suspense>
        </div>
      </div>
    </div>
  );
}

// 外层根：挂 .pb-vision-theme + Provider
export default function PbVisionReportLayout(props: {
  report: AnalysisReport;
  trajectoryArtifact?: ReconstructedBallTrajectoryArtifact | null;
}) {
  const { report, trajectoryArtifact } = props;
  return (
    <PbReportProvider report={report} trajectoryArtifact={trajectoryArtifact}>
      <div
        className="pb-vision-theme min-h-screen w-full"
        style={{ background: "var(--pb-page-bg, #f0f4f2)" }}
      >
        <PbPlayerDrawer />
        <PbDrawerExpander />
        <MainContentInner trajectoryArtifact={trajectoryArtifact} />
      </div>
    </PbReportProvider>
  );
}
