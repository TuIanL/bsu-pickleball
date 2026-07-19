import { describe, expect, it, beforeEach, vi } from "vitest";
import {
  createOutboxItem,
  enqueueItem,
  getPendingItems,
  retryBlockedItems,
  type CodingOutboxItem,
} from "./codingOutbox";

// mock localStorage for node environment
function mockLocalStorage() {
  const store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    clear: () => { Object.keys(store).forEach(k => delete store[k]); },
    removeItem: (key: string) => { delete store[key]; },
    get length() { return Object.keys(store).length; },
    key: (index: number) => Object.keys(store)[index] ?? null,
  };
}

beforeEach(() => {
  vi.stubGlobal("localStorage", mockLocalStorage());
});

const TAKE_ID = "take_test_001";

describe("codingOutbox sequenceNumber", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("starts at 1 for new take", () => {
    const item = createOutboxItem(TAKE_ID, "start_set", 1000);
    expect(item.sequenceNumber).toBe(1);
    expect(item.captureTakeId).toBe(TAKE_ID);
    expect(item.status).toBe("pending");
  });

  it("increments within same take", () => {
    const a = createOutboxItem(TAKE_ID, "start_set", 1000);
    enqueueItem(a);
    const b = createOutboxItem(TAKE_ID, "start_game", 2000);
    enqueueItem(b);
    const c = createOutboxItem(TAKE_ID, "start_next_rally", 3000);
    enqueueItem(c);
    expect(a.sequenceNumber).toBe(1);
    expect(b.sequenceNumber).toBe(2);
    expect(c.sequenceNumber).toBe(3);
  });

  it("independent sequence per take ID", () => {
    const takeA = createOutboxItem("take_A", "start_set", 1000);
    enqueueItem(takeA);
    const takeB = createOutboxItem("take_B", "start_set", 1000);
    enqueueItem(takeB);
    expect(takeA.sequenceNumber).toBe(1);
    expect(takeB.sequenceNumber).toBe(1);
  });

  it("survives page refresh: new item > old pending max", () => {
    // simulate existing pending items in localStorage
    const oldItems: CodingOutboxItem[] = [
      {
        clientActionId: "old_1", captureTakeId: TAKE_ID, sequenceNumber: 5,
        action: "start_set", timestampMs: 1000, clientOccurredAt: "",
        payload: {}, status: "pending", retryCount: 0, createdAt: 100,
      },
      {
        clientActionId: "old_2", captureTakeId: TAKE_ID, sequenceNumber: 8,
        action: "start_game", timestampMs: 2000, clientOccurredAt: "",
        payload: {}, status: "pending", retryCount: 0, createdAt: 200,
      },
    ];
    localStorage.setItem("pre-pickleball-coding-outbox", JSON.stringify(oldItems));

    // simulate page refresh: create a new item
    const fresh = createOutboxItem(TAKE_ID, "start_next_rally", 3000);
    expect(fresh.sequenceNumber).toBe(9);
  });
});

describe("getPendingItems FIFO order", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns items sorted by sequenceNumber ascending", () => {
    const a = createOutboxItem(TAKE_ID, "start_set", 1000);
    enqueueItem(a);
    const b = createOutboxItem(TAKE_ID, "start_game", 2000);
    enqueueItem(b);
    const c = createOutboxItem(TAKE_ID, "start_next_rally", 3000);
    enqueueItem(c);

    const pending = getPendingItems(TAKE_ID);
    expect(pending).toHaveLength(3);
    expect(pending[0].sequenceNumber).toBeLessThan(pending[1].sequenceNumber);
    expect(pending[1].sequenceNumber).toBeLessThan(pending[2].sequenceNumber);
  });

  it("excludes synced items", () => {
    const a = createOutboxItem(TAKE_ID, "start_set", 1000);
    const b = createOutboxItem(TAKE_ID, "start_game", 2000);
    enqueueItem(a);
    enqueueItem(b);
    // manually mark a as synced in localStorage
    const raw = JSON.parse(localStorage.getItem("pre-pickleball-coding-outbox")!);
    raw[0].status = "synced";
    localStorage.setItem("pre-pickleball-coding-outbox", JSON.stringify(raw));
    const pending = getPendingItems(TAKE_ID);
    expect(pending).toHaveLength(1);
    expect(pending[0].clientActionId).toBe(b.clientActionId);
  });
});

describe("createOutboxSender FIFO execution", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("sends items in order, calling onResponse each time", async () => {
    const a = createOutboxItem(TAKE_ID, "start_set", 1000);
    enqueueItem(a);
    const b = createOutboxItem(TAKE_ID, "start_game", 2000);
    enqueueItem(b);
    const c = createOutboxItem(TAKE_ID, "start_next_rally", 3000);
    enqueueItem(c);

    const ordered = getPendingItems(TAKE_ID);
    expect(ordered.map(i => i.action)).toEqual(["start_set", "start_game", "start_next_rally"]);
  });

  it("onResponse receives server revision and it increments for next item", () => {
    const a = createOutboxItem(TAKE_ID, "start_set", 1000);
    enqueueItem(a);
    const b = createOutboxItem(TAKE_ID, "start_game", 2000);
    expect(b.sequenceNumber).toBe(a.sequenceNumber + 1);
  });
});

describe("revision conflict handling", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("blocks subsequent items on revision_conflict", () => {
    const blockedItems: CodingOutboxItem[] = [
      {
        clientActionId: "conflict_item", captureTakeId: TAKE_ID, sequenceNumber: 3,
        action: "start_game", timestampMs: 2000, clientOccurredAt: "",
        payload: {}, status: "blocked", retryCount: 0, lastError: "revision_conflict", createdAt: 100,
      },
      {
        clientActionId: "after_item", captureTakeId: TAKE_ID, sequenceNumber: 4,
        action: "start_next_rally", timestampMs: 3000, clientOccurredAt: "",
        payload: {}, status: "blocked", retryCount: 0, createdAt: 200,
      },
    ];
    localStorage.setItem("pre-pickleball-coding-outbox", JSON.stringify(blockedItems));

    // retryBlockedItems should unblock them
    retryBlockedItems(TAKE_ID);
    const pending = getPendingItems(TAKE_ID);
    expect(pending).toHaveLength(2);
    expect(pending.every(i => i.status === "pending")).toBe(true);
  });

  it("retryBlockedItems only unblocks matching takeId", () => {
    const items: CodingOutboxItem[] = [
      {
        clientActionId: "b1", captureTakeId: "other_take", sequenceNumber: 1,
        action: "start_set", timestampMs: 1000, clientOccurredAt: "",
        payload: {}, status: "blocked", retryCount: 0, createdAt: 100,
      },
      {
        clientActionId: "b2", captureTakeId: TAKE_ID, sequenceNumber: 2,
        action: "start_set", timestampMs: 2000, clientOccurredAt: "",
        payload: {}, status: "blocked", retryCount: 0, createdAt: 200,
      },
    ];
    localStorage.setItem("pre-pickleball-coding-outbox", JSON.stringify(items));
    retryBlockedItems(TAKE_ID);
    const pendingForTake = getPendingItems(TAKE_ID);
    expect(pendingForTake).toHaveLength(1);
    expect(pendingForTake[0].status).toBe("pending");
    // other_take should still be blocked
    const allItems = JSON.parse(localStorage.getItem("pre-pickleball-coding-outbox")!);
    const otherBlocked = allItems.find((i: CodingOutboxItem) => i.captureTakeId === "other_take");
    expect(otherBlocked.status).toBe("blocked");
  });
});
