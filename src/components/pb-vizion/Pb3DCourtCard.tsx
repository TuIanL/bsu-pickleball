import { useCallback, useMemo, useState } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import type { EstimatedBallTrajectory } from "../../services/ballTrajectoryVisualization";
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
  const { evidence, selectedPlayerId, stageFilter, qualityThreshold } = usePbReport();

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

  const trajectories = useMemo<EstimatedBallTrajectory[]>(() => {
    const ev = evidence?.trajectories;
    if (!ev || ev.status !== "available") return [];

    return ev.value
      .filter((t) => {
        if (
          t.averageConfidence != null &&
          t.averageConfidence * 100 < qualityThreshold
        )
          return false;

        // 阶段：仅当能按 shotId 关联到拍序时才应用；无法关联的轨迹保守保留
        if (stageFilter !== "all") {
          if (stageState.mode !== "ids") return true;
          if (t.shotId && !stageState.ids.has(t.shotId)) return false;
        }

        // 球员身份：保留归属该球员、或未归属（孤立）
        if (playerCanonical) {
          const hitter = resolveCanonicalPlayerId(t.hitterPlayerId, null);
          if (hitter && hitter !== playerCanonical) return false;
        }
        return true;
      })
      .map((t) => ({ ...t, hitterPlayerId: playerCanonical }));
  }, [evidence, playerCanonical, qualityThreshold, stageFilter, stageState]);

  const hasEvidence = evidence?.trajectories?.status === "available";
  const stageUnusable = stageFilter !== "all" && stageState.mode === "unknown";
  const noTrajectoryPoints = hasEvidence && trajectories.length === 0;

  return (
    <div className="pb-card p-3 sm:p-4">
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
            selectedShotId={selectedShotId}
            onSelectShot={handleSelectShot}
            onWebGlError={handleWebGlError}
          />
        )}
      </div>
    </div>
  );
}