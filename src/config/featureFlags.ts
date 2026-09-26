/**
 * Product-level switches that only control whether a visualization is loaded
 * and rendered in the browser.  The backend artifact switch remains
 * independent so a deployment can stop calculation without requiring a
 * frontend rebuild, while a frontend rollout can hide the card without
 * changing persisted analysis artifacts.
 */
function envFlag(value: unknown, fallback = true): boolean {
  if (typeof value !== "string") return fallback;
  return value.trim().toLowerCase() !== "false";
}

export const kitchenArrivalCardEnabled = envFlag(import.meta.env.VITE_KITCHEN_ARRIVAL_CARD_ENABLED);

/**
 * 发球候选导航条（ServeRallyStrip）默认隐藏。
 * 发球候选的计算与 `serve_events.json` 产物保持不变，这里只控制浏览器是否渲染
 * 播放器下方的横向候选卡片条与播放器内的候选计数文案；需要临时恢复时设置
 * `VITE_SERVE_RALLY_STRIP_ENABLED=true`，无需重新计算产物。
 */
export const serveRallyStripEnabled = envFlag(import.meta.env.VITE_SERVE_RALLY_STRIP_ENABLED, false);
