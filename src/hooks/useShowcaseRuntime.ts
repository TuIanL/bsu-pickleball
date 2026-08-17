import { useEffect, useState } from "react";
import { getShowcaseRuntimeStatus } from "../services/analysisClient";
import type { ShowcaseRuntimeStatus } from "../types/report";

/**
 * useShowcaseRuntime —— 轮询"展示（Showcase）运行时"状态。
 *
 * 功能：
 * 按固定间隔（1.5s）向后端拉取指定展示运行实例的实时状态，用于在对外的
 * 展示大屏 / 实时看板场景下反映分析任务的最新进度。仅在 runtimeId 存在且
 * active 为 true 时才会启动轮询；参数变化或卸载时自动清理定时器。
 *
 * 参数：
 *   - runtimeId：展示运行实例 ID；为空（undefined）时不轮询。
 *   - active：是否处于激活状态（例如所在页面/面板可见）。为 false 时不轮询。
 *
 * 返回值：
 *   - status：当前展示运行状态（ShowcaseRuntimeStatus）；当 runtimeId/active
 *             与最近一次成功加载的 loadedRuntimeId 不一致时返回 null（避免展示过期数据）。
 *   - error：最近一次拉取失败的错误文案；同样在状态不一致时返回 null。
 */
export function useShowcaseRuntime(runtimeId: string | undefined, active: boolean) {
  const [status, setStatus] = useState<ShowcaseRuntimeStatus | null>(null); // 最新一次成功拉取的展示状态
  const [error, setError] = useState<string | null>(null);                  // 拉取错误（若有）
  const [loadedRuntimeId, setLoadedRuntimeId] = useState<string | null>(null); // 最近一次"发出请求"的 runtimeId

  useEffect(() => {
    // 缺 ID 或未激活 → 不轮询，直接退出
    if (!runtimeId || !active) {
      return;
    }
    let disposed = false; // 卸载标记：防止卸载后异步回调继续写 state
    const poll = async () => {
      try {
        const next = await getShowcaseRuntimeStatus(runtimeId);
        if (!disposed) {
          setStatus(next);
          setLoadedRuntimeId(runtimeId);
          setError(null);
        }
      } catch (err) {
        if (!disposed) {
          setLoadedRuntimeId(runtimeId);
          setError(err instanceof Error ? err.message : "展示状态不可用");
        }
      }
    };
    void poll(); // 立即拉取一次
    const timer = window.setInterval(() => void poll(), 1500); // 之后每 1.5s 轮询
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [runtimeId, active]);

  // 仅当本次运行时与最近加载的 runtimeId 完全匹配时才认为数据是"当前的"
  const hasCurrentRuntime = Boolean(runtimeId && active && loadedRuntimeId === runtimeId);
  return {
    status: hasCurrentRuntime ? status : null,
    error: hasCurrentRuntime ? error : null,
  };
}
