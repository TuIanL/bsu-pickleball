import { useEffect, useRef, useState } from "react";
import { requestJson } from "../services/analysisClient";
import type { OverlayPlaybackIndex } from "../types/report";

type PagedOverlay = {
  playback?: OverlayPlaybackIndex;
  reference_view_id?: string;
  frames: unknown[];
  views?: Record<string, { frames: unknown[] }>;
};

/** Retain at most three 20-second, single-camera shards per overlay layer. */
export function useOverlayPlayback<T extends PagedOverlay>(artifact: T | null | undefined, viewId: string | undefined, seconds: number) {
  const index = artifact?.playback;
  const view = viewId ?? artifact?.reference_view_id ?? "";
  const bucket = index ? Math.max(0, Math.floor(seconds / index.chunk_seconds)) : 0;
  const identity = index ? `${index.url}:${index.generation}` : "";
  const key = `${identity}:${view}:${bucket}`;
  const cache = useRef(new Map<string, unknown[]>());
  const cacheIdentity = useRef("");
  const [loaded, setLoaded] = useState<{ key: string; frames: unknown[] } | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  useEffect(() => {
    if (!index) return;
    if (cacheIdentity.current !== identity) {
      cache.current.clear();
      cacheIdentity.current = identity;
    }
    let disposed = false;
    const controller = new AbortController();
    async function load(chunk: number) {
      const chunkKey = `${identity}:${view}:${chunk}`;
      if (cache.current.has(chunkKey)) return cache.current.get(chunkKey)!;
      const query = new URLSearchParams({ playback: "true", chunk: String(chunk), view_id: view, generation: index!.generation });
      const data = index!.chunks[view]?.includes(chunk)
        ? await requestJson<{ frames: unknown[] }>(`${index!.url}?${query}`, { signal: controller.signal })
        : { frames: [] };
      if (!disposed) {
        cache.current.set(chunkKey, data.frames);
        while (cache.current.size > 3) cache.current.delete(cache.current.keys().next().value!);
      }
      return data.frames;
    }
    void load(bucket).then((frames) => {
      if (disposed) return;
      setLoaded({ key, frames });
      setFailure(null);
      // Prefetch only the next window. Seeking or changing cameras aborts it.
      if (index.chunks[view]?.includes(bucket + 1)) void load(bucket + 1).catch(() => undefined);
    }).catch((error: unknown) => {
      if (!disposed) setFailure({ key, message: error instanceof Error ? error.message : "叠加数据加载失败" });
    });
    return () => { disposed = true; controller.abort(); };
  }, [identity, index, key, bucket, view]);
  if (!artifact || !index) return { artifact, loading: false, error: null };
  const frames = loaded?.key === key ? loaded.frames : [];
  const active = { ...artifact,
    frames: view === artifact.reference_view_id ? frames : [],
    views: { ...artifact.views, ...(artifact.views?.[view] ? { [view]: { ...artifact.views[view], frames } } : {}) },
  } as T;
  return { artifact: active, loading: loaded?.key !== key && failure?.key !== key,
    error: failure?.key === key ? failure.message : null };
}
