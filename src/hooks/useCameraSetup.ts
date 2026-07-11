/** useCameraSetup —— 摄像机配置唯一所有者 */
import { useState, useEffect, useCallback } from "react";
import type { CameraInfo, ProbeResult } from "../types/report";
import type { CaptureStartIntent, CaptureTrackRuntime } from "../types/capture";
import { listCameras, probeCamera } from "../services/analysisClient";

type UseCameraSetupOptions = {
  sessionId: string;
  mode: "single" | "dual";
};

export function useCameraSetup({ sessionId, mode }: UseCameraSetupOptions) {
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResult>>({});

  // 单摄
  const [selectedCameraId, setSelectedCameraId] = useState("");
  // 双摄
  const [selectedSlots, setSelectedSlots] = useState<{ cam_1: string; cam_2: string }>(() => {
    try {
      const stored = sessionStorage.getItem(`capture.slots.${sessionId}`);
      if (stored) return JSON.parse(stored);
    } catch { /* ignore */ }
    return { cam_1: "", cam_2: "" };
  });
  const [slotSelecting, setSlotSelecting] = useState<"cam_1" | "cam_2" | null>(null);

  const loadCameras = useCallback(async () => {
    try { setCameras(await listCameras()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadCameras(); }, [loadCameras]);

  const selectSlot = useCallback((slot: "cam_1" | "cam_2", cameraId: string) => {
    setSelectedSlots(prev => {
      const next = { ...prev, [slot]: cameraId };
      sessionStorage.setItem(`capture.slots.${sessionId}`, JSON.stringify(next));
      return next;
    });
    setSlotSelecting(null);
  }, [sessionId]);

  const runProbe = useCallback(async (cameraId: string) => {
    try {
      const r = await probeCamera(cameraId);
      setProbeResults(prev => ({ ...prev, [cameraId]: r }));
    } catch { /* ignore */ }
  }, []);

  const previewTracks: CaptureTrackRuntime[] = mode === "single"
    ? (selectedCameraId ? [{ slot: "single", cameraId: selectedCameraId, analysisRole: "default" }] : [])
    : [
        ...(selectedSlots.cam_1 ? [{ slot: "cam_1" as const, cameraId: selectedSlots.cam_1, analysisRole: "default" as const }] : []),
        ...(selectedSlots.cam_2 ? [{ slot: "cam_2" as const, cameraId: selectedSlots.cam_2, analysisRole: "supplementary" as const }] : []),
      ];

  const startIntent: CaptureStartIntent | null = mode === "single"
    ? (selectedCameraId ? { mode: "single", cameraId: selectedCameraId, fps: 60, autoAnalyze: false } : null)
    : (selectedSlots.cam_1 && selectedSlots.cam_2
        ? { mode: "dual", slots: { cam_1: selectedSlots.cam_1, cam_2: selectedSlots.cam_2 }, fps: 60, autoAnalyze: false }
        : null);

  const isReady = mode === "single" ? !!selectedCameraId
    : !!(selectedSlots.cam_1 && selectedSlots.cam_2 && selectedSlots.cam_1 !== selectedSlots.cam_2);

  return {
    cameras, setCameras, loadCameras,
    probeResults, runProbe,
    selectedCameraId, setSelectedCameraId,
    selectedSlots, selectSlot, slotSelecting, setSlotSelecting,
    previewTracks, startIntent, isReady,
  };
}
