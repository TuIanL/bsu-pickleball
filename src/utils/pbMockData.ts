// =============================================================
// PB Vision 报告页 Mock 数据
// ------------------------------------------------------------------
// 本文件集中封装所有后端尚未返回字段的前端 mock 逻辑，
// 未来真实 API 就绪时仅需修改本文件内部实现，无需改动组件。
// =============================================================
import type {
  PbDepthDistribution,
  PbServeReturnDepth,
  PbServeReturnStats,
  PbSpeedPercentileResult,
} from "../types/pbReport";

/** 根据 playerId 字符串哈希出一个稳定的 0~1 数值（保证同一场报告同一球员每次刷新 mock 一致） */
function stableHash01(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return (h % 1000) / 1000;
}

/**
 * Mock 进区率 (In%)
 * @returns 0.85 ~ 0.95 之间的两位小数
 */
export function mockInPercent(playerId: string): number {
  const r = stableHash01(playerId + ":in");
  const pct = 0.85 + r * 0.1;
  return Math.round(pct * 100) / 100;
}

/**
 * Mock 速度百分位（Ball Speed / Paddle Speed 共用）
 * @param kind  用于区分同一球员 ball 和 paddle 不同百分位
 * @returns { percentile: 60~90 整数, label: '第84百分位' 格式 }
 */
export function mockSpeedPercentile(
  playerId: string,
  kind: "ball" | "paddle"
): PbSpeedPercentileResult {
  const r = stableHash01(playerId + ":" + kind);
  const p = 60 + Math.round(r * 30); // 60 ~ 90
  return {
    percentile: p,
    label: `第${p}百分位`,
  };
}

/**
 * Mock Serves & Returns 的 In/Out/Net 统计
 * 默认总数 9，和 PB Vision 截图保持一致量级
 */
export function mockServeReturnStats(playerId: string): PbServeReturnStats {
  const rs = stableHash01(playerId + ":sr");
  // Serves: In 100%（9/9）
  const serveTotal = 9;
  const serveIn = serveTotal; // 全部 In（100%）
  // Returns: In 88% ~ 91%，剩下 1 个 Net / 0 个 Out
  const returnTotal = 9;
  const returnInBase = 8; // 保底 8 个 In
  const extra = Math.floor(rs * 2); // 0 或 1
  const returnIn = returnInBase + extra; // 8 或 9
  const returnNet = Math.max(0, returnTotal - returnIn); // 1 或 0

  return {
    serves: { total: serveTotal, in: serveIn, out: 0, net: 0 },
    returns: { total: returnTotal, in: returnIn, out: 0, net: returnNet },
  };
}

/**
 * Mock Serve Depth / Return Depth 的 Deep / Medium / Shallow 百分比分布
 * 返回值每个字段都是 0~100 整数，和 === 100
 */
function normalizeDepth(
  deepRatio: number,
  medRatio: number
): PbDepthDistribution {
  const deep = Math.round(deepRatio * 100);
  const medium = Math.round(medRatio * 100);
  const shallow = 100 - deep - medium;
  return { deep, medium, shallow };
}

export function mockServeReturnDepth(playerId: string): PbServeReturnDepth {
  const rd = stableHash01(playerId + ":depth");
  // Serve Depth: PB Vision 参考 22% Deep / 56% Medium / 22% Shallow
  const serve = normalizeDepth(
    0.2 + rd * 0.06, // 0.20 ~ 0.26
    0.52 + rd * 0.08 // 0.52 ~ 0.60
  );
  // Return Depth: PB Vision 参考 13% Deep / 63% Medium / 25% Shallow
  const rt = stableHash01(playerId + ":returndepth");
  const return_ = normalizeDepth(
    0.1 + rt * 0.08, // 0.10 ~ 0.18
    0.60 + rt * 0.08 // 0.60 ~ 0.68
  );
  return { serve, return_ };
}
