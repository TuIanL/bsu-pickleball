/**
 * CodingOutbox —— 前端 FIFO 发送队列，保证 coding actions 的顺序发送和幂等性。
 */

import { executeCodingAction, type CodingActionResponse } from "./analysisClient";
import type { CodingActionRequest, CodingActionType, LiveCodingState } from "../types/report";

const OUTBOX_KEY = "pre-pickleball-coding-outbox";

export interface CodingOutboxItem {
  clientActionId: string;
  captureTakeId: string;
  sequenceNumber: number;
  action: CodingActionType;
  timestampMs: number;
  clientOccurredAt: string;
  payload: Record<string, unknown>;
  status: "pending" | "sending" | "synced" | "blocked" | "failed";
  retryCount: number;
  lastError?: string;
  createdAt: number;
}

function generateActionId(): string {
  return `ac_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function loadOutbox(): CodingOutboxItem[] {
  try {
    const raw = localStorage.getItem(OUTBOX_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveOutbox(items: CodingOutboxItem[]): void {
  try {
    localStorage.setItem(OUTBOX_KEY, JSON.stringify(items));
  } catch { /* ignore */ }
}

let _sequenceCounter = 0;

export function createOutboxItem(
  captureTakeId: string,
  action: CodingActionType,
  timestampMs: number,
  payload: Record<string, unknown> = {},
): CodingOutboxItem {
  _sequenceCounter += 1;
  return {
    clientActionId: generateActionId(),
    captureTakeId,
    sequenceNumber: _sequenceCounter,
    action,
    timestampMs,
    clientOccurredAt: new Date().toISOString(),
    payload,
    status: "pending",
    retryCount: 0,
    createdAt: Date.now(),
  };
}

export function enqueueItem(item: CodingOutboxItem): void {
  const items = loadOutbox();
  items.push(item);
  saveOutbox(items);
}

export function getPendingItems(captureTakeId: string): CodingOutboxItem[] {
  return loadOutbox().filter(
    (i) => i.captureTakeId === captureTakeId && i.status !== "synced",
  ).sort((a, b) => a.sequenceNumber - b.sequenceNumber);
}

function updateItem(clientActionId: string, patch: Partial<CodingOutboxItem>): void {
  const items = loadOutbox();
  const idx = items.findIndex((i) => i.clientActionId === clientActionId);
  if (idx >= 0) {
    items[idx] = { ...items[idx], ...patch };
    saveOutbox(items);
  }
}

export type OutboxStateListener = (items: CodingOutboxItem[]) => void;

export function createOutboxSender(
  captureTakeId: string,
  getCurrentRevision: () => number,
  onStateChange: OutboxStateListener,
) {
  let _sending = false;
  let _stopped = false;

  async function flush() {
    if (_sending || _stopped) return;
    _sending = true;

    try {
      const pending = getPendingItems(captureTakeId);
      for (const item of pending) {
        if (item.status === "synced") continue;
        if (item.status === "blocked") continue;

        updateItem(item.clientActionId, { status: "sending" });
        onStateChange(getPendingItems(captureTakeId));

        const request: CodingActionRequest = {
          action: item.action,
          client_action_id: item.clientActionId,
          expected_revision: getCurrentRevision(),
          timestamp_ms: item.timestampMs,
          client_occurred_at: item.clientOccurredAt,
          payload: item.payload,
        };

        try {
          await executeCodingAction(captureTakeId, request);
          updateItem(item.clientActionId, { status: "synced" });
        } catch (error: unknown) {
          const status = (error && typeof error === "object" && "status" in error && (error as { status: number }).status === 409)
            ? (item.retryCount < 5 ? "pending" : "blocked")
            : (item.retryCount < 5 ? "pending" : "failed");
          updateItem(item.clientActionId, {
            status,
            retryCount: item.retryCount + 1,
            lastError: String(error),
          });
          if (status !== "pending") break; // block subsequent items
        }

        onStateChange(getPendingItems(captureTakeId));
      }
    } finally {
      _sending = false;
    }
  }

  return {
    flush,
    stop: () => { _stopped = true; },
  };
}

/**
 * Quick event definitions based on capture mode.
 */
export interface QuickEventDef {
  type: string;
  source: string;
  label: string;
  note: string;
  payload: Record<string, unknown>;
}

export const MATCH_QUICK_EVENTS: QuickEventDef[] = [
  { type: "start_set", source: "manual", label: "盘开始", note: "新的一盘开始", payload: {} },
  { type: "start_game", source: "manual", label: "局开始", note: "新的一局开始", payload: {} },
  { type: "start_next_rally", source: "manual", label: "下一分", note: "开始新的一分", payload: {} },
  { type: "end_rally", source: "manual", label: "结束当前分", note: "结束当前进行的分", payload: {} },
  { type: "toggle_non_play", source: "manual", label: "非比赛", note: "标记非比赛时间", payload: {} },
  { type: "change_side", source: "manual", label: "换边", note: "双方交换场地", payload: {} },
  { type: "add_note", source: "manual", label: "重点标记", note: "标记重要时刻", payload: { highlight: true } },
  { type: "undo", source: "manual", label: "撤销", note: "撤销上一步操作", payload: {} },
];
