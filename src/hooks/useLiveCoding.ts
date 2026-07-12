/** useLiveCoding —— 实时编码：Outbox、Timeline、Segments、LiveCodingState */
import { useState, useRef, useCallback, useEffect } from "react";
import type { LiveCodingState, CaptureSegmentSummary, SessionTimelineEvent } from "../types/report";
import {
  getLiveCodingState, listSegments, listTimelineEvents, createTimelineEvent,
} from "../services/analysisClient";
import {
  createOutboxItem, enqueueItem, createOutboxSender, getPendingItems, retryBlockedItems,
  type CodingOutboxItem,
} from "../services/codingOutbox";
import { quickEventsForMode, ACTION_TO_EVENT_TYPE, type QuickEventDef } from "../services/timelineQuickEvents";

type UseLiveCodingOptions = {
  fieldSessionId: string;
  captureTakeId: string | null;
  captureMode: string;
  phase: string;
  elapsedMs: number;
  startedAt?: string;
};

function closeSegmentsByType(segments: CaptureSegmentSummary[], types: string[], endMs: number): CaptureSegmentSummary[] {
  const result = [...segments];
  for (let i = result.length - 1; i >= 0; i--) {
    const s = result[i];
    if (s.status === "open" && types.includes(s.segment_type)) {
      result[i] = { ...s, end_ms: endMs, status: "closed" as const };
    }
  }
  return result;
}

function findLatestSegment(
  segments: CaptureSegmentSummary[],
  predicate: (segment: CaptureSegmentSummary) => boolean,
): CaptureSegmentSummary | undefined {
  for (let index = segments.length - 1; index >= 0; index -= 1) {
    if (predicate(segments[index])) return segments[index];
  }
  return undefined;
}

function makeSegment(
  segType: string,
  startMs: number,
  label: string,
  ordinal: number,
  parentSegmentId?: string,
): CaptureSegmentSummary {
  return {
    id: `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    segment_type: segType as "set" | "game" | "rally",
    ordinal,
    label,
    start_ms: startMs,
    status: "open",
    source: "manual",
    edit_version: 0,
    edit_status: "active",
    is_highlight: false,
    parent_segment_id: parentSegmentId,
  };
}

export function useLiveCoding({ fieldSessionId, captureTakeId, captureMode, phase, elapsedMs, startedAt }: UseLiveCodingOptions) {
  const [liveCodingState, setLiveCodingState] = useState<LiveCodingState | null>(null);
  const [outboxItems, setOutboxItems] = useState<CodingOutboxItem[]>([]);
  const [outboxHealth, setOutboxHealth] = useState<"synced" | "pending" | "offline">("synced");
  const [segments, setSegments] = useState<CaptureSegmentSummary[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);

  const outboxSenderRef = useRef<ReturnType<typeof createOutboxSender> | null>(null);
  const revisionRef = useRef(0);
  const lastTakeIdRef = useRef<string | null>(null);
  const lastActionTimeRef = useRef(0);
  const optimisticRef = useRef({ nonPlay: false });
  const undoStackRef = useRef<{segments: CaptureSegmentSummary[]; events: SessionTimelineEvent[]}[]>([]);
  const segmentsRef = useRef<CaptureSegmentSummary[]>([]);
  const eventsRef = useRef<SessionTimelineEvent[]>([]);
  const startedAtRef = useRef(startedAt);
  const initialNonPlayRef = useRef(false);

  startedAtRef.current = startedAt;

  const nowMs = useCallback(() => {
    if (startedAtRef.current) {
      return Math.max(0, Date.now() - Date.parse(startedAtRef.current));
    }
    return elapsedMs;
  }, [elapsedMs]);

  // 同步 ref 跟踪最新 state
  useEffect(() => { segmentsRef.current = segments; }, [segments]);
  useEffect(() => { eventsRef.current = timelineEvents; }, [timelineEvents]);

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
    if (Array.isArray(response.timeline_events)) {
      setTimelineEvents(response.timeline_events as SessionTimelineEvent[]);
    } else if (response.created_events?.length) {
      setTimelineEvents(prev => upsertById(prev, response.created_events as SessionTimelineEvent[]));
    }
    if (Array.isArray(response.segments)) {
      setSegments(response.segments as CaptureSegmentSummary[]);
    } else if (response.updated_segments?.length) {
      setSegments(prev => upsertById(prev, response.updated_segments as CaptureSegmentSummary[]));
    }
  }, []);

  // 加载 Timeline Events：仅在有 captureTakeId 时加载，避免混入历史事件
  useEffect(() => {
    setTimelineEvents([]);
    if (!fieldSessionId || !captureTakeId) return;
    listTimelineEvents(fieldSessionId, { capture_take_id: captureTakeId } as any)
      .then(setTimelineEvents)
      .catch(() => {});
  }, [fieldSessionId, captureTakeId]);

  // 初始化/切换 CaptureTake
  useEffect(() => {
    if (!captureTakeId || captureTakeId === lastTakeIdRef.current) return;
    lastTakeIdRef.current = captureTakeId;

    outboxSenderRef.current?.stop();
    outboxSenderRef.current = null;

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

  // 录制开始后自动创建初始 non_play_start（t=0，表示录制开始后处于非比赛状态）
  useEffect(() => {
    if (phase !== "recording" || captureTakeId || initialNonPlayRef.current || !fieldSessionId) return;
    initialNonPlayRef.current = true;

    const ts = nowMs();
    createTimelineEvent(fieldSessionId, {
      event_type: "non_play_start",
      source: "manual",
      timestamp_ms: ts,
      note: "",
      payload_json: { intermission_kind: "between_rallies" },
    } as any).then(created => {
      if (created) {
        setTimelineEvents(prev => upsertById(prev, [created as SessionTimelineEvent]));
      }
    }).catch(() => {});
  }, [phase, captureTakeId, fieldSessionId, nowMs]);

  // 退出录制时重置 initialNonPlayRef
  useEffect(() => {
    if (phase !== "recording") {
      initialNonPlayRef.current = false;
    }
  }, [phase]);

  const freeze = useCallback(() => {
    outboxSenderRef.current?.freeze?.();
  }, []);

  const createEventLocal = useCallback(async (fieldSessionId: string, payload: Record<string, unknown>) => {
    try {
      const created = await createTimelineEvent(fieldSessionId, payload as any);
      if (created) {
        setTimelineEvents(prev => upsertById(prev, [created as SessionTimelineEvent]));
      }
    } catch { /* ignore */ }
  }, []);

  const addTimelineEvent = useCallback(async (event: QuickEventDef) => {
    const now = Date.now();
    if (now - lastActionTimeRef.current < 400) return;
    lastActionTimeRef.current = now;
    const timestampMs = nowMs();

    if (captureTakeId) {
      const item = createOutboxItem(captureTakeId, event.type, timestampMs, event.payload);
      if (outboxSenderRef.current?.isFrozen?.()) return;
      enqueueItem(item);
      setOutboxItems(prev => [...prev, item]);
      outboxSenderRef.current?.flush().catch(() => {});
      return;
    }

    if (!fieldSessionId) return;

    // 快照当前状态到撤销栈
    if (event.type !== "undo") {
      undoStackRef.current.push({
        segments: [...segmentsRef.current],
        events: [...eventsRef.current],
      });
      if (undoStackRef.current.length > 50) undoStackRef.current.shift();
    }

    const opt = optimisticRef.current;

    // start_timeout / change_side / toggle_non_play / start_next_rally / end_rally 不走通用事件创建
    const skipGeneric = event.type === "toggle_non_play" || event.type === "start_timeout" || event.type === "undo" || event.type === "start_next_rally" || event.type === "end_rally" || event.type === "change_side";
    if (!skipGeneric) {
      const eventType = ACTION_TO_EVENT_TYPE[event.type];
      if (eventType) {
        await createEventLocal(fieldSessionId, {
          event_type: eventType,
          source: event.source,
          timestamp_ms: timestampMs,
          note: event.note,
          payload_json: event.payload,
        });
      }
    }

    switch (event.type) {
      case "start_set": {
        setSegments(prev => {
          let next = closeSegmentsByType(prev, ["rally", "game", "set"], timestampMs);
          next = [...next, makeSegment("set", timestampMs, event.label, prev.filter(s => s.segment_type === "set").length + 1)];
          return next;
        });
        break;
      }
      case "start_game": {
        setSegments(prev => {
          let next = closeSegmentsByType(prev, ["rally", "game"], timestampMs);
          let activeSet = findLatestSegment(next, s => s.segment_type === "set" && s.status === "open");
          if (!activeSet) {
            const setOrdinal = next.filter(s => s.segment_type === "set").length + 1;
            activeSet = makeSegment("set", timestampMs, `第${setOrdinal}盘`, setOrdinal);
            next = [...next, activeSet];
          }
          const gameOrdinal = next.filter(s => s.segment_type === "game" && s.parent_segment_id === activeSet.id).length + 1;
          next = [...next, makeSegment("game", timestampMs, `第${gameOrdinal}局`, gameOrdinal, activeSet.id)];
          return next;
        });
        break;
      }
      case "start_next_rally": {
        setSegments(prev => {
          let next = closeSegmentsByType(prev, ["rally"], timestampMs);
          let activeSet = findLatestSegment(next, s => s.segment_type === "set" && s.status === "open");
          if (!activeSet) {
            const setOrdinal = next.filter(s => s.segment_type === "set").length + 1;
            activeSet = makeSegment("set", timestampMs, `第${setOrdinal}盘`, setOrdinal);
            next = [...next, activeSet];
          }

          let activeGame = findLatestSegment(next, s =>
            s.segment_type === "game" && s.status === "open" && s.parent_segment_id === activeSet!.id,
          );
          if (!activeGame) {
            const gameOrdinal = next.filter(s => s.segment_type === "game" && s.parent_segment_id === activeSet!.id).length + 1;
            activeGame = makeSegment("game", timestampMs, `第${gameOrdinal}局`, gameOrdinal, activeSet.id);
            next = [...next, activeGame];
          }

          const rallyOrdinal = next.filter(s => s.segment_type === "rally" && s.parent_segment_id === activeGame!.id).length + 1;
          next = [...next, makeSegment("rally", timestampMs, `第${rallyOrdinal}分`, rallyOrdinal, activeGame.id)];
          return next;
        });
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_end",
          source: event.source,
          timestamp_ms: timestampMs,
          note: "",
          payload_json: {},
        });
        break;
      }
      case "end_rally": {
        setSegments(prev => closeSegmentsByType(prev, ["rally"], timestampMs));
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_start",
          source: event.source,
          timestamp_ms: timestampMs,
          note: "",
          payload_json: { intermission_kind: "between_rallies" },
        });
        break;
      }
      case "end_game": {
        setSegments(prev => closeSegmentsByType(prev, ["rally", "game"], timestampMs));
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_start",
          source: event.source,
          timestamp_ms: timestampMs,
          note: "",
          payload_json: { intermission_kind: "between_rallies" },
        });
        break;
      }
      case "end_set": {
        setSegments(prev => closeSegmentsByType(prev, ["rally", "game", "set"], timestampMs));
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_start",
          source: event.source,
          timestamp_ms: timestampMs,
          note: "",
          payload_json: { intermission_kind: "between_rallies" },
        });
        break;
      }
      case "change_side": {
        setSegments(prev => closeSegmentsByType(prev, ["rally"], timestampMs));
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_end",
          source: event.source,
          timestamp_ms: timestampMs,
          note: "",
          payload_json: {},
        });
        await createEventLocal(fieldSessionId, {
          event_type: "side_change",
          source: event.source,
          timestamp_ms: timestampMs,
          note: event.note,
          payload_json: {},
        });
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_start",
          source: event.source,
          timestamp_ms: timestampMs,
          note: "",
          payload_json: { intermission_kind: "side_change" },
        });
        break;
      }
      case "start_timeout": {
        setSegments(prev => closeSegmentsByType(prev, ["rally"], timestampMs));
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_end",
          source: event.source,
          timestamp_ms: timestampMs,
          note: "",
          payload_json: {},
        });
        await createEventLocal(fieldSessionId, {
          event_type: "non_play_start",
          source: event.source,
          timestamp_ms: timestampMs,
          note: event.note,
          payload_json: { intermission_kind: "timeout" },
        });
        break;
      }
      case "toggle_non_play": {
        if (opt.nonPlay) {
          await createEventLocal(fieldSessionId, {
            event_type: "non_play_end",
            source: event.source,
            timestamp_ms: timestampMs,
            note: "",
            payload_json: {},
          });
        } else {
          await createEventLocal(fieldSessionId, {
            event_type: "non_play_start",
            source: event.source,
            timestamp_ms: timestampMs,
            note: "",
            payload_json: { intermission_kind: "between_rallies" },
          });
        }
        opt.nonPlay = !opt.nonPlay;
        break;
      }
      case "undo": {
        if (undoStackRef.current.length === 0) break;
        const snapshot = undoStackRef.current.pop()!;
        setSegments(snapshot.segments);
        setTimelineEvents(snapshot.events);
        break;
      }
      default:
        break;
    }
  }, [captureTakeId, fieldSessionId, nowMs, createEventLocal]);

  const flushWithDeadline = useCallback((timeoutMs: number) => {
    return outboxSenderRef.current?.flushWithDeadline?.(timeoutMs).catch(() => {}) ?? Promise.resolve();
  }, []);

  const retrySync = useCallback(() => {
    if (captureTakeId) {
      retryBlockedItems(captureTakeId);
      setOutboxItems(getPendingItems(captureTakeId));
      outboxSenderRef.current?.flush().catch(() => {});
    } else if (fieldSessionId) {
      listTimelineEvents(fieldSessionId, {} as any)
        .then(setTimelineEvents)
        .catch(() => {});
    }
  }, [captureTakeId, fieldSessionId]);

  const quickEvents = quickEventsForMode(captureMode);

  return {
    liveCodingState,
    outboxItems, outboxHealth,
    segments, timelineEvents,
    quickEvents,
    freeze, addTimelineEvent, flushWithDeadline, retrySync,
    outboxSenderRef,
  };
}
