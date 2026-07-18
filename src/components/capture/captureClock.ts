export function computeCaptureElapsedMs(
  startedAt: string,
  clientNowMs = Date.now(),
): number {
  const startedMs = Date.parse(startedAt);
  if (!Number.isFinite(startedMs)) return 0;
  return Math.max(0, clientNowMs - startedMs);
}
