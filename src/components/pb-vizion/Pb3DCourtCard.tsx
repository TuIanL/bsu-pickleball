import { useCallback, useMemo, useState } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import type { EstimatedBallTrajectory } from "../../services/ballTrajectoryVisualization";
import { BallTrajectoryScene } from "../platform/BallTrajectoryScene";

export default function Pb3DCourtCard() {
  const {
    report,
    selectedPlayerId,
    stageFilter,
    typeFilter,
    qualityThreshold,
    selectedSubject,
  } = usePbReport();

  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [webGlError, setWebGlError] = useState<string | null>(null);

  const handleSelectShot = useCallback((shotId: string | null) => {
    setSelectedShotId(shotId);
  }, []);

  const handleWebGlError = useCallback((message: string) => {
    setWebGlError(message);
    if (typeof console !== "undefined") {
      console.warn("WebGL 错误:", message);
    }
  }, []);

  const subjectName = selectedSubject?.name;

  const filteredShotIds = useMemo<Set<string>>(() => {
    const ids = new Set<string>();
    const rows = report?.shotRows ?? [];

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (subjectName && row.player !== subjectName) continue;

      if (typeFilter !== "all" && row.type !== typeFilter) continue;

      const qualityPct = (row.qualityScore ?? 0) * 100;
      if (qualityPct < qualityThreshold) continue;

      const shotNumber = i + 1;
      if (stageFilter === "serves") {
        if (row.type !== "发球") continue;
      } else if (stageFilter === "third") {
        if (row.type !== "第三拍" && shotNumber !== 3) continue;
      } else if (stageFilter === "fifth_plus") {
        if (shotNumber < 5) continue;
      }

      ids.add(row.id);
    }
    return ids;
  }, [
    report?.shotRows,
    subjectName,
    typeFilter,
    qualityThreshold,
    stageFilter,
  ]);

  const trajectories = useMemo<EstimatedBallTrajectory[]>(() => {
    const raw = report?.shotTrajectories ?? [];
    const result: EstimatedBallTrajectory[] = [];
    for (const t of raw) {
      const trajectoryId = t.id;
      const shotMatch =
        filteredShotIds.size === 0 ||
        filteredShotIds.has(trajectoryId) ||
        Array.from(filteredShotIds).some((sid) => trajectoryId.includes(sid));
      if (filteredShotIds.size > 0 && !shotMatch) continue;

      result.push({
        id: t.id,
        sequence: 1,
        direction: "near-to-far",
        startTimeSeconds: 0,
        endTimeSeconds: 0.5,
        durationSeconds: 0.5,
        pointCount: 0,
        averageConfidence: 0.8,
        interpolatedRatio: 0,
        highConfidence: true,
        peakEstimatedHeightFt: null,
        points: [],
        shotId: t.id,
        hitterPlayerId: selectedPlayerId,
        hitterRenderSlot: null,
        ownershipStatus: "confirmed",
        ownershipConfidence: 0.9,
      } as unknown as EstimatedBallTrajectory);
    }
    return result;
  }, [report?.shotTrajectories, filteredShotIds, selectedPlayerId]);

  return (
    <div className="pb-card p-3 sm:p-4">
      <div className="pb-3d-view-btns relative overflow-hidden rounded-2xl bg-gray-50 aspect-[16/10]">
        {webGlError ? (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
            <div>
              <div className="text-lg font-bold text-red-600 mb-2">
                3D 渲染不可用
              </div>
              <div className="text-sm text-gray-600">{webGlError}</div>
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
