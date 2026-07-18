/**
 * CodingOutbox —— 前端 FIFO 发送队列，保证 coding actions 的顺序发送和幂等性。
 */

import { executeCodingAction } from "./analysisClient";
import type { CodingActionRequest, CodingActionType, CodingActionResponse } from "../types/report";

const OUTBOX_KEY = "pre-pickleball-coding-outbox";
const DRAIN_TIMEOUT_MS = 10000;

/** Outbox 队列中的一条待发送动作 */
export interface CodingOutboxItem {
  clientActionId: string;          // 客户端生成的动作 ID（幂等键）
  captureTakeId: string;           // 所属 CaptureTake
  sequenceNumber: number;          // 序号（递增，用于检测冲突）
  action: CodingActionType;        // 动作类型
  timestampMs: number;             // 动作时间戳（毫秒）
  clientOccurredAt: string;        // 客户端发生时间 ISO 字符串
  payload: Record<string, unknown>;     // 附加载荷
  status: "pending" | "sending" | "synced" | "blocked" | "failed";  // 发送状态
  retryCount: number;              // 重试次数
  lastError?: string;              // 最近一次错误
  createdAt: number;               // 创建时间戳
}

/** 生成客户端唯一动作 ID */
function generateActionId(): string {
  return `ac_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/** 从 localStorage 加载全部 Outbox */
function loadOutbox(): CodingOutboxItem[] {
  try {
    const raw = localStorage.getItem(OUTBOX_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** 持久化 Outbox 到 localStorage */
function saveOutbox(items: CodingOutboxItem[]): void {
  try {
    localStorage.setItem(OUTBOX_KEY, JSON.stringify(items));
  } catch { /* ignore */ }
}

/** 计算该 CaptureTake 的下一个序号 */
function nextSequenceNumber(captureTakeId: string): number {
  const items = loadOutbox();
  const takeItems = items.filter(i => i.captureTakeId === captureTakeId);
  const maxSeq = takeItems.reduce((max, i) => Math.max(max, i.sequenceNumber), 0);
  return maxSeq + 1;
}

/** 创建一条新的 Outbox 待发送项 */
export function createOutboxItem(
  captureTakeId: string,
  action: CodingActionType,
  timestampMs: number,
  payload: Record<string, unknown> = {},
): CodingOutboxItem {
  return {
    clientActionId: generateActionId(),
    captureTakeId,
    sequenceNumber: nextSequenceNumber(captureTakeId),
    action,
    timestampMs,
    clientOccurredAt: new Date().toISOString(),
    payload,
    status: "pending",
    retryCount: 0,
    createdAt: Date.now(),
  };
}

/** 入队一条待发送项 */
export function enqueueItem(item: CodingOutboxItem): void {
  const items = loadOutbox();
  items.push(item);
  saveOutbox(items);
}

/** 获取该 CaptureTake 下所有未同步的项，按序号排序 */
export function getPendingItems(captureTakeId: string): CodingOutboxItem[] {
  return loadOutbox().filter(
    (i) => i.captureTakeId === captureTakeId && i.status !== "synced",
  ).sort((a, b) => a.sequenceNumber - b.sequenceNumber);
}

/** 局部更新一条 Outbox 项 */
function updateItem(clientActionId: string, patch: Partial<CodingOutboxItem>): void {
  const items = loadOutbox();
  const idx = items.findIndex((i) => i.clientActionId === clientActionId);
  if (idx >= 0) {
    items[idx] = { ...items[idx], ...patch };
    saveOutbox(items);
  }
}

/** 将被阻断的项重置为待发送状态 */
export function retryBlockedItems(captureTakeId: string): void {
  const items = loadOutbox();
  let changed = false;
  for (const item of items) {
    if (item.captureTakeId === captureTakeId && (item.status === "blocked" || item.status === "failed")) {
      item.status = "pending";
      item.retryCount = 0;
      item.lastError = undefined;
      changed = true;
    }
  }
  if (changed) saveOutbox(items);
}

/** 阻断该序号之后的所有待发送项（revision 冲突处理） */
function blockAllSubsequentItems(captureTakeId: string, fromSequence: number): void {
  const items = loadOutbox();
  let changed = false;
  for (const item of items) {
    if (item.captureTakeId === captureTakeId && item.sequenceNumber >= fromSequence && item.status === "pending") {
      item.status = "blocked";
      changed = true;
    }
  }
  if (changed) saveOutbox(items);
}

export type OutboxStateListener = (items: CodingOutboxItem[]) => void;
export type CodingResponseHandler = (response: CodingActionResponse) => void;

export function createOutboxSender(
  captureTakeId: string,
  getCurrentRevision: () => number,
  onStateChange: OutboxStateListener,
  onResponse: CodingResponseHandler,
) {
  let _sending = false;
  let _stopped = false;
  let _draining = false;
  let _frozen = false;

  async function flush() {
    if (_sending) return;
    if (_stopped && !_draining) return;
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
          const response = await executeCodingAction(captureTakeId, request);
          updateItem(item.clientActionId, { status: "synced" });
          onResponse(response);
        } catch (error: unknown) {
          const err = error && typeof error === "object" ? error as Record<string, unknown> : {};
          const statusCode = err.status as number | undefined;

          if (statusCode === 409) {
            const detail = err.detail as Record<string, unknown> | undefined;
            const errorType = typeof detail === "object" && detail && "error" in detail
              ? detail.error as string
              : typeof err.detail === "string"
                ? err.detail
                : "";

            if (errorType === "revision_conflict" || typeof errorType === "string" && errorType.includes("revision")) {
              updateItem(item.clientActionId, { status: "blocked", lastError: "revision_conflict" });
              blockAllSubsequentItems(captureTakeId, item.sequenceNumber);
              onStateChange(getPendingItems(captureTakeId));
              break;
            }

            if (errorType === "duplicate_action" || item.retryCount >= 5) {
              updateItem(item.clientActionId, { status: "failed", lastError: String(error) });
              onStateChange(getPendingItems(captureTakeId));
              break;
            }

            updateItem(item.clientActionId, {
              status: "pending",
              retryCount: item.retryCount + 1,
              lastError: String(error),
            });
          } else {
            const nextStatus = item.retryCount < 5 ? "pending" : "failed";
            updateItem(item.clientActionId, {
              status: nextStatus,
              retryCount: item.retryCount + 1,
              lastError: String(error),
            });
            if (nextStatus !== "pending") break;
          }
        }

        onStateChange(getPendingItems(captureTakeId));
      }
    } finally {
      _sending = false;
    }
  }

  async function drain(): Promise<{ unsynced: number }> {
    _draining = true;
    try {
      await flushWithTimeout(DRAIN_TIMEOUT_MS);
    } catch {
      // timeout — return current state
    }
    _draining = false;
    const remaining = getPendingItems(captureTakeId);
    return { unsynced: remaining.filter(i => i.status === "failed" || i.status === "blocked").length };
  }

  async function flushWithTimeout(timeoutMs: number): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        _sending = false;
        reject(new Error("drain timeout"));
      }, timeoutMs);

      flush().then(() => {
        clearTimeout(timer);
        const remaining = getPendingItems(captureTakeId);
        if (remaining.length === 0 || remaining.every(i => i.status === "synced" || i.status === "failed" || i.status === "blocked")) {
          resolve();
        } else {
          clearTimeout(timer);
          resolve();
        }
      }).catch(() => {
        clearTimeout(timer);
        resolve();
      });
    });
  }

  return {
    flush,
    drain,
    stop: () => { _stopped = true; },
    freeze: () => { _frozen = true; },
    isFrozen: () => _frozen,
    flushWithDeadline: (timeoutMs: number) => flushWithTimeout(timeoutMs),
  };
}

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
  { type: "start_next_rally", source: "manual", label: "开始下一分", note: "开始新的一分", payload: {} },
  { type: "end_rally", source: "manual", label: "结束当前分", note: "结束当前进行的分", payload: {} },
  { type: "start_timeout", source: "manual", label: "战术暂停", note: "进入战术暂停", payload: {} },
  { type: "change_side", source: "manual", label: "换边", note: "双方交换场地", payload: {} },
  { type: "add_note", source: "manual", label: "重点标记", note: "标记重要时刻", payload: { highlight: true } },
  { type: "undo", source: "manual", label: "撤销", note: "撤销上一步操作", payload: {} },
];
