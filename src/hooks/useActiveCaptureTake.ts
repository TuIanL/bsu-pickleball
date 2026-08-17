import { useCallback, useEffect, useRef, useState } from "react";
import {
  getActiveCaptureTake,
  forceFinalizeActiveCaptureTake,
  listRecordings,
  listSyncRecordings,
} from "../services/analysisClient";

/**
 * 当前活跃录制（Active CaptureTake）的摘要信息。
 * 后端 "active capture take" 接口返回，描述当前场次下是否已经有正在进行的录制。
 */
export interface ActiveCaptureTakeSummary {
  takeId: string;            // 活跃录制自身 ID
  fieldSessionId: string;    // 所属场次 ID
  captureTakeId: string;     // 关联的 CaptureTake（片段集合）ID
  sourceSessionId: string;   // 底层录制会话（recording / sync recording）ID
  sourceSessionType: string; // 底层会话类型
  startedAt: string;         // 录制开始时间（ISO 字符串）
  serverNow: string;         // 服务端当前时间（用于校正时钟）
  status: "starting" | "recording" | "stopping" | "recovering" | "finalizing"; // 录制生命周期状态
  title: string | null;      // 录制标题（可为空）
  courtName: string | null;  // 关联球场名（可为空）
  captureMode: "single" | "dual"; // 单摄 / 双摄
  videoSpec: { width?: number; height?: number; fps?: number } | null; // 视频规格（分辨率/帧率）
}

/**
 * useActiveCaptureTake —— 轮询并暴露"当前场次是否已有活跃录制"。
 *
 * 功能：
 *  1. 挂载即开始轮询后端"active capture take"接口（默认每 5s 一次），
 *     让页面重进时能自动发现并恢复展示正在进行的录制。
 *  2. 通过独立时钟（每 1s）触发一次 state 引用更新，使上层"已录制时长"等派生值平滑刷新。
 *  3. 检测"孤儿录制"：若后端已无对应 recording/sync recording 会话，则标记 isOrphan，
 *     提示用户可能存在未正常结束的录制。
 *  4. 提供 forceCancel 用于强制结束（finalize）该活跃录制。
 *
 * 参数：无（Hook 内部自行管理，不接收外部入参）。
 *
 * 返回值：
 *  - activeTake：活跃录制摘要；无活跃录制时为 null。
 *  - isLoading：首次查询是否仍在进行。
 *  - isOrphan：当前 activeTake 是否已被判为孤儿（底层会话丢失）。
 *  - forceCancel：强制结束当前活跃录制的异步方法。
 *  - forceCancelling：forceCancel 调用进行中标记。
 */
const POLL_INTERVAL = 5000;   // 活跃录制轮询间隔（毫秒）
const CLOCK_INTERVAL = 1000;  // 本地时钟刷新间隔（毫秒），用于平滑更新时长显示

export function useActiveCaptureTake() {
  const [activeTake, setActiveTake] = useState<ActiveCaptureTakeSummary | null>(null); // 当前活跃录制摘要
  const [isLoading, setIsLoading] = useState(true);  // 首次查询加载中
  const [isOrphan, setIsOrphan] = useState(false);    // 是否为孤儿录制
  const [forceCancelling, setForceCancelling] = useState(false); // 强制结束进行中
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);  // 轮询定时器引用
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);  // 时钟定时器引用
  const seqRef = useRef(0);  // 请求序号：用于丢弃过期响应，避免旧请求覆盖新状态
  const pollFnRef = useRef<(() => void) | null>(null); // 缓存 startPolling，供 visibilitychange 复用

  // 判断活跃录制是否"孤儿"：查单摄与双摄会话是否都还存在 recording 状态的底层会话
  const checkOrphan = useCallback(async (take: ActiveCaptureTakeSummary) => {
    try {
      const [singleSessions, dualSessions] = await Promise.all([
        listRecordings({ field_session_id: take.fieldSessionId, status: "recording" }).catch(() => []),
        listSyncRecordings({ field_session_id: take.fieldSessionId, status: "recording" }).catch(() => []),
      ]);
      const hasActiveSession = singleSessions.length > 0 || dualSessions.length > 0;
      setIsOrphan(!hasActiveSession); // 都不存在 → 视为孤儿
    } catch {
      setIsOrphan(false);
    }
  }, []);

  // 查询一次活跃录制；用 seqRef 防止过期响应污染最新状态
  const fetchActive = useCallback(() => {
    const seq = ++seqRef.current;
    getActiveCaptureTake()
      .then((data) => {
        if (seq !== seqRef.current) return; // 已有更新的请求，丢弃本次陈旧结果
        setActiveTake(data);
        setIsLoading(false);
        if (data) {
          void checkOrphan(data); // 有活跃录制则进一步检查是否孤儿
        } else {
          setIsOrphan(false);
        }
      })
      .catch(() => {
        if (seq !== seqRef.current) return;
        setActiveTake(null);
        setIsOrphan(false);
        setIsLoading(false);
      });
  }, [checkOrphan]);

  // 强制结束（finalize）当前活跃录制；仅在确实有 activeTake 时生效
  const forceCancel = useCallback(async () => {
    if (!activeTake) return;
    setForceCancelling(true);
    try {
      await forceFinalizeActiveCaptureTake();
      setActiveTake(null);
      setIsOrphan(false);
    } catch {
      // 失败时保持 forceCancelling 为 false，交由 UI 显示原录制
    } finally {
      setForceCancelling(false);
    }
  }, [activeTake]);

  // 停止所有轮询/时钟并递增 seq，使进行中的请求失效
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (clockRef.current) {
      clearInterval(clockRef.current);
      clockRef.current = null;
    }
    seqRef.current += 1;
  }, []);

  // 启动轮询：立即查一次，然后按 POLL_INTERVAL 周期轮询；时钟按 CLOCK_INTERVAL 触发引用更新
  const startPolling = useCallback(() => {
    stopPolling();
    fetchActive();
    pollRef.current = setInterval(fetchActive, POLL_INTERVAL);
    clockRef.current = setInterval(() => {
      // 仅返回新引用，触发重渲染以刷新"已录制时长"等基于 serverNow 的派生值
      setActiveTake((prev) => {
        if (!prev) return prev;
        return { ...prev };
      });
    }, CLOCK_INTERVAL);
  }, [fetchActive, stopPolling]);

  // 主效应：挂载即开始轮询；页面隐藏时暂停，恢复可见时重启；卸载时清理
  useEffect(() => {
    pollFnRef.current = startPolling;
    startPolling();
    const handleVisibility = () => {
      if (document.hidden) {
        stopPolling();
      } else {
        pollFnRef.current?.(); // 恢复可见时重新拉起轮询
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [startPolling, stopPolling]);

  return { activeTake, isLoading, isOrphan, forceCancel, forceCancelling };
}

// 复用底层倒计时计算工具，对外以 computeElapsedMs 名义导出
export { computeCaptureElapsedMs as computeElapsedMs } from "../components/capture/captureClock";
