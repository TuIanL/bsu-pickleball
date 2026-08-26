import { useCallback, useMemo, useState } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import {
  buildShots,
  buildReconstructedBallTrajectoryVisualization,
  filterTrajectoriesByConfirmedPlayer,
  type EstimatedBallTrajectory,
} from "../../services/ballTrajectoryVisualization";
import { BallTrajectoryScene } from "../platform/BallTrajectoryScene";
import PbEvidenceUnavailable from "./PbEvidenceUnavailable";
import { resolveCanonicalPlayerId } from "../../evidence/playerIdentity";
import type { PbStageFilter } from "../../types/pbReport";

/** 阶段筛选的最小输入（shot 拍序） */
interface StageShot {
  id: string;
  playerId: string | null;
  ordinalInRally: number | null;
}

type StageFilterState =
  | { mode: "all" }
  | { mode: "unknown"; reason: string } // ordinal 不可靠
  | { mode: "ids"; ids: Set<string> }; // 可按拍序过滤

function ordinalQualifies(stage: PbStageFilter, ordinal: number): boolean {
  if (stage === "serves") return ordinal === 1;
  if (stage === "third") return ordinal === 3;
  return ordinal >= 5;
}

/** 方案 A + authority gate：仅当存在可靠 ordinal 时才产出可筛 shot ids。 */
function computeStageFilter(
  stage: PbStageFilter,
  exploration: StageShot[],
  playerCanonical: string | null
): StageFilterState {
  if (stage === "all") return { mode: "all" };
  if (!exploration.some((s) => s.ordinalInRally != null)) {
    return { mode: "unknown", reason: "阶段筛选暂不可用（缺 rally 拍序）" };
  }
  const ids = new Set<string>();
  for (const s of exploration) {
    if (s.ordinalInRally == null) continue;
    if (playerCanonical && s.playerId) {
      const sp = resolveCanonicalPlayerId(s.playerId, null);
      if (sp && sp !== playerCanonical) continue;
    }
    if (ordinalQualifies(stage, s.ordinalInRally)) ids.add(s.id);
  }
  return { mode: "ids", ids };
}

export default function Pb3DCourtCard() {
  const { evidence, trajectoryArtifact, selectedPlayerId, stageFilter, qualityThreshold } = usePbReport();

  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [webGlError, setWebGlError] = useState<string | null>(null);

  const handleSelectShot = useCallback((shotId: string | null) => setSelectedShotId(shotId), []);
  const handleWebGlError = useCallback((message: string) => {
    setWebGlError(message);
    if (typeof console !== "undefined") console.warn("WebGL 错误:", message);
  }, []);

  const playerCanonical = useMemo(
    () => resolveCanonicalPlayerId(selectedPlayerId, null),
    [selectedPlayerId]
  );

  const stageState = useMemo<StageFilterState>(() => {
    const exploration: StageShot[] = (evidence?.shotExploration ?? []).map((s) => ({
      id: s.id,
      playerId: s.playerId,
      ordinalInRally: s.ordinalInRally,
    }));
    return computeStageFilter(stageFilter, exploration, playerCanonical);
  }, [stageFilter, evidence, playerCanonical]);

  const reconstructedData = useMemo(
    () => buildReconstructedBallTrajectoryVisualization(trajectoryArtifact),
    [trajectoryArtifact],
  );

  const trajectories = useMemo<EstimatedBallTrajectory[]>(() => {
    const source = trajectoryArtifact
      ? reconstructedData.trajectories
      : evidence?.trajectories?.status === "available"
        ? evidence.trajectories.value
        : [];

    const playerScoped = filterTrajectoriesByConfirmedPlayer(source, playerCanonical);

    return playerScoped.trajectories
      .filter((t) => {
        if (
          t.averageConfidence != null &&
          t.averageConfidence * 100 < qualityThreshold
        )
          return false;

        // 阶段：仅当能按 shotId 关联到拍序时才应用；无法关联时保留已确认的球员 Shot
        if (stageFilter !== "all") {
          if (stageState.mode !== "ids") return true;
          if (!t.shotId || !stageState.ids.has(t.shotId)) return false;
        }
        return true;
      });
  }, [evidence, playerCanonical, qualityThreshold, reconstructedData.trajectories, stageFilter, stageState, trajectoryArtifact]);

  const visibleShots = useMemo(() => buildShots(trajectories), [trajectories]);
  const visibleShotIds = useMemo(
    () => new Set(visibleShots.map((shot) => shot.shotId)),
    [visibleShots],
  );
  const selectedShotForView = selectedShotId && visibleShotIds.has(selectedShotId)
    ? selectedShotId
    : null;

  const hasEvidence = trajectoryArtifact
    ? reconstructedData.trajectories.length > 0
    : evidence?.trajectories?.status === "available";
  // 真实 reconstructed artifact 本身已经是可展示段集合；缺少 rally 拍序时保留球路，
  // 避免报告页默认“第三拍”把整个共享 3D 视图误判为空态。存在拍序时仍按原筛选逻辑过滤。
  const stageUnusable = !trajectoryArtifact && stageFilter !== "all" && stageState.mode === "unknown";
  const noTrajectoryPoints = hasEvidence && trajectories.length === 0;
  const trajectoryCount = trajectories.length;

  return (
    <div className="pb-card p-3 sm:p-4">
      <div className="mb-3 flex items-center justify-between gap-3 px-1">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--pb-text-muted,#98a2b3)]">球路报告</p>
          <h2 className="mt-1 text-lg font-black text-[var(--pb-text-primary,#182230)]">分段球路报告</h2>
        </div>
        <span className="rounded-full bg-[#EAF8F0] px-2.5 py-1 text-xs font-bold text-[#168A34]">{trajectoryCount} 段</span>
      </div>
      <div className="pb-3d-view-btns relative overflow-hidden rounded-2xl bg-gray-50 aspect-[16/10]">
        {webGlError ? (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
            <div>
              <div className="text-lg font-bold text-red-600 mb-2">3D 渲染不可用</div>
              <div className="text-sm text-gray-600">{webGlError}</div>
            </div>
          </div>
        ) : !hasEvidence ? (
          <div className="absolute inset-0">
            <PbEvidenceUnavailable
              reason={
                evidence?.trajectories?.status === "unavailable"
                  ? evidence.trajectories.reason
                  : undefined
              }
            />
          </div>
        ) : stageUnusable ? (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
            <div className="text-sm text-[var(--pb-text-muted,#9ca3af)]">
              {stageState.mode === "unknown" ? stageState.reason : "阶段筛选暂不可用"}
            </div>
          </div>
        ) : noTrajectoryPoints ? (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
            <div className="text-sm text-[var(--pb-text-muted,#9ca3af)]">
              当前筛选下没有可显示的球路
            </div>
          </div>
        ) : (
          <BallTrajectoryScene
            trajectories={trajectories}
            selectedShotId={selectedShotForView}
            onSelectShot={handleSelectShot}
            onWebGlError={handleWebGlError}
          />
        )}
      </div>
    </div>
  );
}
