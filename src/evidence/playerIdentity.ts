// =============================================================
// 全局身份解析（设计 D1）
// -------------------------------------------------------------
// 两个职责不同的函数，禁止合并：
//   - normalizeCanonicalPlayerAlias：纯语法归一化（P1/p1/player_1 → Player_1）
//   - resolveGlobalPlayerId：仅经 global-player-roster.v1 的语义映射
//     （禁止按尾号猜；无映射 → null）
// =============================================================

const CANONICAL_RE = /^player[_ -]?(\d+)$/i;

/** 语法别名归一化：P1 / p1 / player_1 / Player_1 → "Player_1"。非 canonical/别名形态返回 null。 */
export function normalizeCanonicalPlayerAlias(id: string | null | undefined): string | null {
  if (!id) return null;
  const trimmed = id.trim();
  if (CANONICAL_RE.test(trimmed)) {
    const n = trimmed.match(/_?(\d+)$/i)?.[1];
    if (n) return `Player_${Number(n)}`;
  }
  // 形如 P1 / GlobalP1
  const p = trimmed.match(/^[Pp](\d+)$/);
  if (p) return `Player_${Number(p[1])}`;
  return null;
}

/** 全局身份是否属于 global_player_N */
export function isGlobalPlayerId(id: string | null | undefined): boolean {
  return typeof id === "string" && /^global_player_\d+$/i.test(id.trim());
}

/**
 * 内部全局身份解析：仅经 roster 映射到 canonical。
 * 禁止因为尾号 N 猜测为 Player_N。无映射（或无量表）→ null（unresolved）。
 */
export function resolveGlobalPlayerId(
  id: string | null | undefined,
  roster: Record<string, string> | null | undefined
): string | null {
  if (!id) return null;
  if (!isGlobalPlayerId(id)) return null;
  if (!roster) return null;
  const mapped = roster[id.trim()];
  if (!mapped) return null;
  return normalizeCanonicalPlayerAlias(mapped) ?? mapped;
}

/**
 * 把任意身份解析为 canonical player id（供跨模块统一关联）：
 *   - global_player_N → roster 映射
 *   - P1 / player_1 / Player_1 → 语法归一化
 *   - 已是 Player_N → 原样
 * 解析不到 → null。
 */
export function resolveCanonicalPlayerId(
  id: string | null | undefined,
  roster: Record<string, string> | null | undefined
): string | null {
  if (!id) return null;
  if (isGlobalPlayerId(id)) return resolveGlobalPlayerId(id, roster);
  return normalizeCanonicalPlayerAlias(id);
}

/** 判断两个身份是否指向同一 canonical 球员（容忍 legacy/全局别名）。 */
export function sameCanonicalPlayer(
  a: string | null | undefined,
  b: string | null | undefined,
  roster: Record<string, string> | null | undefined
): boolean {
  if (!a || !b) return false;
  const ca = resolveCanonicalPlayerId(a, roster);
  const cb = resolveCanonicalPlayerId(b, roster);
  if (!ca || !cb) return false;
  return ca === cb;
}