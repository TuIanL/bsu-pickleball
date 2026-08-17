/**
 * useCameraSetup —— 录制前摄像机配置的唯一所有者（单一数据源）。
 *
 * 功能：
 * 管理"本次录制要使用哪一台（单摄）或哪两台（双摄）摄像机"的全部前端状态，
 * 包括摄像头列表加载、单台摄像头的连接探测（probe）、单摄选择以及双摄槽位选择，
 * 并在此基础上派生出三个供上层使用的计算结果：
 *   - previewTracks：预览轨道列表（描述将要录制的机位与角色）
 *   - startIntent：启动录制的意图对象（直接传给录制接口）
 *   - isReady：配置是否就绪（可点击"开始录制"）
 *
 * 参数（UseCameraSetupOptions）：
 *   - sessionId：场次 ID。双摄模式下用于在 sessionStorage 中按场次持久化槽位选择，
 *                避免刷新页面后丢失已选摄像头。
 *   - mode：录制模式，"single"（单摄）或 "dual"（双摄），决定使用单摄选择还是双摄槽位。
 *
 * 返回值：见文件底部 return 语句处的逐字段注释，涵盖摄像头列表 / 探测状态 /
 * 单摄与双摄选择状态 / 派生轨道 / 启动意图 / 就绪标志，以及对应的 setter 与操作方法。
 */
import { useState, useEffect, useCallback } from "react";
import type { CameraInfo, ProbeResult } from "../types/report";
import type { CaptureStartIntent, CaptureTrackRuntime } from "../types/capture";
import { listCameras, probeCamera } from "../services/analysisClient";

/** useCameraSetup 配置参数 */
type UseCameraSetupOptions = {
  sessionId: string;        // 场次 ID（用于持久化插槽选择）
  mode: "single" | "dual";  // 单摄 / 双摄
};

/**
 * 主 Hook。挂载时自动加载摄像头列表，并根据 mode 维护单摄或双摄的选择状态。
 * 详见上方文件头注释了解参数含义与整体功能。
 */
export function useCameraSetup({ sessionId, mode }: UseCameraSetupOptions) {
  const [cameras, setCameras] = useState<CameraInfo[]>([]);                    // 摄像头列表：后端返回的全部可用摄像头
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResult>>({});   // 检测结果：按 cameraId 索引最近一次探测详情
  const [probeLoading, setProbeLoading] = useState<Record<string, boolean>>({});        // 检测中：按 cameraId 索引是否正在探测
  const [probeErrors, setProbeErrors] = useState<Record<string, string>>({});           // 检测错误：按 cameraId 索引探测失败原因

  // 单摄：当前选中的摄像头 ID
  const [selectedCameraId, setSelectedCameraId] = useState("");
  // 双摄：两个槽位各自选中的摄像头 ID（cam_1 为主机位，cam_2 为辅机位）
  const [selectedSlots, setSelectedSlots] = useState<{ cam_1: string; cam_2: string }>(() => {
    // 初始化时优先从 sessionStorage 读取本场次已保存的槽位选择，实现刷新后保留
    try {
      const stored = sessionStorage.getItem(`capture.slots.${sessionId}`);
      if (stored) return JSON.parse(stored);
    } catch { /* ignore */ }
    return { cam_1: "", cam_2: "" };
  });
  // 双摄：当前正在交互选择的是哪个槽位（用于 UI 弹层状态）
  const [slotSelecting, setSlotSelecting] = useState<"cam_1" | "cam_2" | null>(null);

  // 从后端拉取摄像头列表，失败静默忽略（不影响其余 UI）
  const loadCameras = useCallback(async () => {
    try { setCameras(await listCameras()); } catch { /* ignore */ }
  }, []);

  // 组件挂载后自动加载一次摄像头列表
  useEffect(() => { loadCameras(); }, [loadCameras]);

  // 双摄：选择一个槽位对应的摄像头，并同步持久化到 sessionStorage
  const selectSlot = useCallback((slot: "cam_1" | "cam_2", cameraId: string) => {
    setSelectedSlots(prev => {
      const next = { ...prev, [slot]: cameraId };
      // 落盘保存，保证刷新页面后仍记得该场次选了哪台摄像头
      sessionStorage.setItem(`capture.slots.${sessionId}`, JSON.stringify(next));
      return next;
    });
    setSlotSelecting(null); // 选择完成后关闭槽位选择弹层
  }, [sessionId]);

  // 对指定摄像头发起一次连接探测（probe），实时维护 loading / error / 结果三态
  const runProbe = useCallback(async (cameraId: string) => {
    setProbeLoading(prev => ({ ...prev, [cameraId]: true }));   // 进入探测中
    setProbeErrors(prev => {                                       // 清除该摄像头旧错误
      const next = { ...prev };
      delete next[cameraId];
      return next;
    });
    try {
      const r = await probeCamera(cameraId);                     // 调用后端探测接口
      setProbeResults(prev => ({ ...prev, [cameraId]: r }));     // 保存探测结果
    } catch (e) {
      // 捕获异常并写入可读的错误信息
      setProbeErrors(prev => ({
        ...prev,
        [cameraId]: e instanceof Error ? e.message : "检测请求失败",
      }));
    } finally {
      setProbeLoading(prev => ({ ...prev, [cameraId]: false }));  // 无论成败都结束"探测中"
    }
  }, []);

  // 派生：预览轨道列表。单摄仅含主轨道；双摄含 cam_1（default）与 cam_2（supplementary）
  const previewTracks: CaptureTrackRuntime[] = mode === "single"
    ? (selectedCameraId ? [{ slot: "single", cameraId: selectedCameraId, analysisRole: "default" }] : [])
    : [
        ...(selectedSlots.cam_1 ? [{ slot: "cam_1" as const, cameraId: selectedSlots.cam_1, analysisRole: "default" as const }] : []),
        ...(selectedSlots.cam_2 ? [{ slot: "cam_2" as const, cameraId: selectedSlots.cam_2, analysisRole: "supplementary" as const }] : []),
      ];

  // 派生：启动录制意图。两个槽位都选好才构成合法意图，否则为 null（禁用开始按钮）
  const startIntent: CaptureStartIntent | null = mode === "single"
    ? (selectedCameraId ? { mode: "single", cameraId: selectedCameraId, fps: 60, autoAnalyze: false } : null)
    : (selectedSlots.cam_1 && selectedSlots.cam_2
        ? { mode: "dual", slots: { cam_1: selectedSlots.cam_1, cam_2: selectedSlots.cam_2 }, fps: 60, autoAnalyze: false }
        : null);

  // 派生：是否就绪。单摄需已选摄像头；双摄需两个槽位都选且不能是同一台摄像头
  const isReady = mode === "single" ? !!selectedCameraId
    : !!(selectedSlots.cam_1 && selectedSlots.cam_2 && selectedSlots.cam_1 !== selectedSlots.cam_2);

  return {
    cameras, setCameras, loadCameras,                // 摄像头列表与加载
    probeResults, probeLoading, probeErrors, runProbe,  // 连接检测（结果 / 进行中 / 错误 / 触发方法）
    selectedCameraId, setSelectedCameraId,            // 单摄选择状态与 setter
    selectedSlots, selectSlot, slotSelecting, setSlotSelecting,  // 双摄槽位：状态 / 选择方法 / 弹层状态
    previewTracks, startIntent, isReady,              // 预览轨道 / 启动意图 / 是否就绪
  };
}
