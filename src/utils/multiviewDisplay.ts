export type DisplayViewId = string;

export interface DisplayTimeMapping {
  offsetMs?: number | null;
  rate?: number | null;
}

export function canonicalTimeToSourceTimeMs(canonicalTimeMs: number, mapping?: DisplayTimeMapping): number {
  const offsetMs = Number(mapping?.offsetMs ?? 0);
  const rate = Number(mapping?.rate ?? 1) > 0 ? Number(mapping?.rate ?? 1) : 1;
  return Math.max(0, offsetMs + canonicalTimeMs * rate);
}

export function sourceTimeToCanonicalTimeMs(sourceTimeMs: number, mapping?: DisplayTimeMapping): number {
  const offsetMs = Number(mapping?.offsetMs ?? 0);
  const rate = Number(mapping?.rate ?? 1) > 0 ? Number(mapping?.rate ?? 1) : 1;
  return Math.max(0, (sourceTimeMs - offsetMs) / rate);
}

/** URL 中的展示机位只读解析：非法值永远回退任务 reference view。 */
export function resolveDisplayViewId(
  requested: string | null | undefined,
  available: readonly DisplayViewId[],
  referenceViewId: DisplayViewId,
): DisplayViewId {
  return requested && available.includes(requested) ? requested : referenceViewId;
}

/** 替换 displayView，不触碰已有 workspace view / analysisJob / return 参数。 */
export function withDisplayViewQuery(path: string, displayViewId: DisplayViewId): string {
  const hashIndex = path.indexOf("#");
  const hash = hashIndex >= 0 ? path.slice(hashIndex) : "";
  const withoutHash = hashIndex >= 0 ? path.slice(0, hashIndex) : path;
  const questionIndex = withoutHash.indexOf("?");
  const pathname = questionIndex >= 0 ? withoutHash.slice(0, questionIndex) : withoutHash;
  const query = questionIndex >= 0 ? withoutHash.slice(questionIndex + 1) : "";
  const params = new URLSearchParams(query);
  params.set("displayView", displayViewId);
  const serialized = params.toString();
  return `${pathname}${serialized ? `?${serialized}` : ""}${hash}`;
}
