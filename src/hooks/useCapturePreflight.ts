/**
 * useCapturePreflight —— 双摄录制前的同步短录测试（Preflight）。
 *
 * 功能：
 * 在正式启动双摄录制之前，对两台摄像头做一次短暂（默认 5s）的同步录制测试，
 * 校验双机位能否正常协同工作（帧同步、采集可用性等）。单摄模式不触发任何测试。
 * 结果以一段不可变状态机（idle → running → passed/failed）暴露给上层 UI。
 *
 * 参数（UseCapturePreflightOptions）：
 *   - mode：录制模式，"single" 或 "dual"。仅 "dual" 才会真正执行测试。
 *   - slots：双摄槽位选择 { cam_1, cam_2 }。任一槽位为空时无法测试。
 *
 * 返回值：
 *   - preflightState：测试状态机当前值，结构见 PreflightState。
 *       · idle：未开始（初始态，或槽位变更后重置）
 *       · running：测试中
 *       · passed：通过，附带 result（SyncTestResult 详情）
 *       · failed：失败，附带 error（可读错误文案）
 *   - runTest：手动触发一次测试的异步方法（仅 dual 且两端均选好时有效）。
 */
import { useState, useCallback, useEffect } from "react";
import type { SyncTestResult } from "../types/report";
import { runSyncTest } from "../services/analysisClient";

type UseCapturePreflightOptions = {
  mode: "single" | "dual";                 // 录制模式；仅 dual 需要 preflight
  slots?: { cam_1: string; cam_2: string }; // 双摄槽位选择
};

/** 测试状态机：表达一次 preflight 测试的完整生命周期 */
type PreflightState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "passed"; result: SyncTestResult }
  | { status: "failed"; error: string };

export function useCapturePreflight({ mode, slots }: UseCapturePreflightOptions) {
  const [state, setState] = useState<PreflightState>({ status: "idle" });

  // 当双摄槽位（任一）发生变化时，重置测试结果为 idle，避免展示过期的"通过/失败"
  useEffect(() => {
    // Camera selection is external input; reset the result when it changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- invalidates stale preflight state.
    setState({ status: "idle" });
  }, [slots?.cam_1, slots?.cam_2]);

  // 触发一次同步测试：仅 dual 且两个槽位都已选好才执行
  const runTest = useCallback(async () => {
    if (mode !== "dual" || !slots?.cam_1 || !slots?.cam_2) return;
    setState({ status: "running" });
    try {
      const result = await runSyncTest({ cam_1_id: slots.cam_1, cam_2_id: slots.cam_2, duration: 5 });
      setState({ status: "passed", result }); // 测试通过，保留结果详情
    } catch (e: unknown) {
      setState({ status: "failed", error: e instanceof Error ? e.message : "测试失败" });
    }
  }, [mode, slots]);

  return { preflightState: state, runTest };
}
