/** useLiveCoding —— 实时编码：Outbox、Timeline、Segments、LiveCodingState */
import { useState, useRef, useCallback, useEffect } from "react";
import type { LiveCodingState, CaptureSegmentSummary, SessionTimelineEvent, CodingActionType } from "../types/report";
import {
  getLiveCodingState, listSegments, listTimelineEvents, createTimelineEvent,
} from "../services/analysisClient";
import {
  createOutboxItem, enqueueItem, createOutboxSender, getPendingItems, retryBlockedItems,
  type CodingOutboxItem,
} from "../services/codingOutbox";
import { quickEventsForMode, type QuickEventDef } from "../services/timelineQuickEvents";

type UseLiveCodingOptions = {
  fieldSessionId: string;
  captureTakeId: string | null;
  phase: string;
  elapsedMs: number;
};

export function useLiveCoding({ fieldSessionId, captureTakeId, phase, elapsedMs }: UseLiveCodingOptions) {
  const [liveCodingState, setLiveCodingState] = useState<LiveCodingState | null>(null);
  const [outboxItems, setOutboxItems] = useState<CodingOutboxItem[]>([]);
  const [outboxHealth, setOutboxHealth] = useState<"synced" | "pending" | "offline">("synced");
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);

  const outboxSenderRef = useRef<ReturnType<typeof createOutboxSender> | null>(null);
  const revisionRef = useRef(0);
  const lastTakeIdRef = useRef<string | null>(null);
  const lastActionTimeRef = useRef(0);

  const upsertById = <T extends { id: string }>(existing: T[], incoming: T[]): T[] => {
    const map = new Map(existing.map(e => [e.id, e]));
    for (const item of incoming) map.set(item.id, item);
    return [...map.values()];
  };

  const applyCodingResponse = useCallback((response: any) => {
    revisionRef.current = response.revision;
    if (response.live_state) {
      setLiveCodingState({ ...response.live_state, revision: response.revision });
    }
    if (response.created_events?.length) {
      setTimelineEvents(prev => upsertById(prev, response.created_events as SessionTimelineEvent[]));
    }
    if (response.updated_segments?.length) {
      setSegments(prev => upsertById(prev, response.updated_segments as CaptureSegmentSummary[]));
    }
  }, []);

  // 初始化/切换 CaptureTake
  useEffect(() => {
    if (!captureTakeId || captureTakeId === lastTakeIdRef.current) return;
    lastTakeIdRef.current = captureTakeId;

    outboxSenderRef.current?.stop();
    outboxSenderRef.current = null;

    setTimelineEvents([]);
    setSegments([]);

    (async () => {
      try {
        const state = await getLiveCodingState(captureTakeId);
        setLiveCodingState(state);
        revisionRef.current = state?.revision ?? 0;
      } catch { /* ignore */ }

      try {
        const segs = await listSegments(captureTakeId as any);
        setSegments(segs ?? []);
      } catch { /* ignore */ }

      try {
        const events = await listTimelineEvents({ capture_take_id: captureTakeId, limit: 200 } as any);
        setTimelineEvents(events);
      } catch { /* ignore */ }

      const pending = getPendingItems(captureTakeId);
      setOutboxItems(pending);
      setOutboxHealth(pending.length > 0 ? "pending" : "synced");

      const sender = createOutboxSender(
        captureTakeId,
        () => revisionRef.current,
        setOutboxItems,
        applyCodingResponse,
      );
      outboxSenderRef.current = sender;
      sender.flush().catch(() => {});
    })();

    return () => {
      outboxSenderRef.current?.stop();
      outboxSenderRef.current = null;
    };
  }, [captureTakeId]);

  // 加载 Timeline Events（首次 + fieldSessionId）
  useEffect(() => {
    if (!fieldSessionId || !captureTakeId) return;
    listTimelineEvents({ field_session_id: fieldSessionId, capture_take_id: captureTakeId, limit: 200 } as any)
      .then(setTimelineEvents)
      .catch(() => {});
  }, [fieldSessionId, captureTakeId]);

  const freeze = useCallback(() => {
    outboxSenderRef.current?.freeze?.();
  }, []);

  const addTimelineEvent = useCallback(async (event: QuickEventDef) => {
    if (!captureTakeId) return;
    const now = Date.now();
    if (now - lastActionTimeRef.current < 400) return;
    lastActionTimeRef.current = now;

    const timestampMs = elapsedMs;
    const action = (event.type ?? "add_note") as CodingActionType;

    const item = createOutboxItem(captureTakeId, action, timestampMs, event.payload);
    if (outboxSenderRef.current?.isFrozen?.()) return;
    enqueueItem(item);
    setOutboxItems(prev => [...prev, item]);

    try {
      await createTimelineEvent(fieldSessionId, {
        event_type: event.type as any,
        source: event.source as any,
        timestamp_ms: timestampMs,
        note: event.note,
        payload_json: event.payload,
      } as any);
    } catch {
      // 离线时通过 outbox 延迟发送
    }
    outboxSenderRef.current?.flush().catch(() => {});
  }, [captureTakeId, fieldSessionId, elapsedMs]);

  const flushWithDeadline = useCallback((timeoutMs: number) => {
    return outboxSenderRef.current?.flushWithDeadline?.(timeoutMs).catch(() => {}) ?? Promise.resolve();
  }, []);

  const retrySync = useCallback(() => {
    if (!captureTakeId) return;
    retryBlockedItems(captureTakeId);
    setOutboxItems(getPendingItems(captureTakeId));
    outboxSenderRef.current?.flush().catch(() => {});
  }, [captureTakeId]);

  const quickEvents = quickEventsForMode("match");

  return {
    liveCodingState,
    outboxItems, outboxHealth,
    segments, timelineEvents,
    quickEvents,
    freeze, addTimelineEvent, flushWithDeadline, retrySync,
    outboxSenderRef,
  };
}
