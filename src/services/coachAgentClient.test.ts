import { afterEach, describe, expect, it, vi } from "vitest";
import { streamCoachTurn } from "./coachAgentClient";
import type { CoachStreamEvent, CoachTurnRequest } from "../types/coachAgent";

const request: CoachTurnRequest = {
  message: "解释移动数据",
  plan: null,
  history: [],
  context: { taskLabel: "样例", playerLabel: "A", source: "demo", dataQuality: "样例", evidence: [], hasInsights: false },
};

async function collect() {
  const events: CoachStreamEvent[] = [];
  for await (const event of streamCoachTurn(request, "live")) events.push(event);
  return events;
}

afterEach(() => vi.restoreAllMocks());

describe("live coach API", () => {
  it("reads a real SSE response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      'data: {"type":"text_delta","delta":"在线回复"}\n\ndata: [DONE]\n\n',
      { headers: { "content-type": "text/event-stream; charset=utf-8" } },
    ));
    expect(await collect()).toEqual([{ type: "text_delta", delta: "在线回复" }]);
  });

  it("reports cloud limits with the server's user-facing message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      JSON.stringify({ detail: "教学助教正在回答其他问题，请稍后再试。" }),
      { status: 429, headers: { "content-type": "application/json" } },
    ));
    await expect(collect()).rejects.toThrow("正在回答其他问题");
  });

  it("rejects an HTML SPA fallback instead of silently treating it as a successful model response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<!doctype html><div id=root></div>", {
      headers: { "content-type": "text/html" },
    }));
    await expect(collect()).rejects.toThrow("未返回模型事件流");
  });
});
