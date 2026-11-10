/** Pixel-space overlays must follow the selected camera, never another view's fallback. */
export function selectVisualOverlay<T extends object>(
  artifact: (T & { reference_view_id?: string; views?: Record<string, Partial<T>> }) | null | undefined,
  viewId?: string,
  fallbackReferenceViewId = "cam_1",
): T | null {
  if (!artifact) return null;
  const reference = artifact.reference_view_id ?? fallbackReferenceViewId;
  if (!viewId || viewId === reference) return artifact;
  const view = artifact.views?.[viewId];
  return view ? { ...artifact, ...view } : null;
}
