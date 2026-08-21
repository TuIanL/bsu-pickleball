// =============================================================
// Demo 演示数据（仅 report.source === "demo" 使用；隔离于真实 job）
// -------------------------------------------------------------
// 设计 D4：fake data 只存在于 Demo 数据入口，job 路径绝不引用。
// 本模块只被纯转换 buildPlayerReportEvidence 的 isDemo 分支调用。
// =============================================================

function stableHash01(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return (h % 1000) / 1000;
}

export function demoInRatePct(playerId: string): number {
  return Math.round(100 * (0.85 + stableHash01(playerId + ":in") * 0.1)) / 100;
}

export function demoBallSpeedMph(playerId: string): number {
  return Math.round((35 + (stableHash01(playerId + ":balls") - 0.5) * 4) * 10) / 10;
}

export function demoPaddleSpeedMph(playerId: string): number {
  return Math.round((27 + (stableHash01(playerId + ":paddles") - 0.5) * 4) * 10) / 10;
}