// =============================================================
// useCoachAgent —— 教学助教会话状态
// -------------------------------------------------------------
// 负责：消息流、流式文本、工具调用进度、计划版本、中断与重置。
// 不做：任何业务判断（证据与计划都来自 client 事件）。
// =============================================================
import { useCallback, useEffect, useRef, useState } from "react";
import { coachAgentMode, streamCoachTurn } from "../services/coachAgentClient";
import type {
  CoachContext,
  CoachMessage,
  CoachToolCall,
  CoachTrainingPlan,
} from "../types/coachAgent";

let messageSeq = 0;
function nextMessageId(prefix: string): string {
  messageSeq += 1;
  return `${prefix}-${messageSeq}`;
}

export interface UseCoachAgentResult {
  messages: CoachMessage[];
  plan: CoachTrainingPlan | null;
  busy: boolean;
  error: string | null;
  send: (text: string) => void;
  stop: () => void;
  reset: () => void;
}

export function useCoachAgent(context: CoachContext): UseCoachAgentResult {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [plan, setPlan] = useState<CoachTrainingPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const planRef = useRef<CoachTrainingPlan | null>(null);
  const messagesRef = useRef<CoachMessage[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchMessage = useCallback((id: string, patch: (prev: CoachMessage) => CoachMessage) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? patch(item) : item)));
  }, []);

  const send = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;

      setError(null);
      const userMessage: CoachMessage = { id: nextMessageId("user"), role: "user", text };
      const assistantId = nextMessageId("assistant");
      const assistantMessage: CoachMessage = {
        id: assistantId,
        role: "assistant",
        text: "",
        toolCalls: [],
        streaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const history = messagesRef.current
        .filter((item) => item.text.trim().length > 0)
        .slice(-6)
        .map((item) => ({ role: item.role, text: item.text }));

      const run = async () => {
        try {
          const stream = streamCoachTurn(
            { message: text, context, plan: planRef.current, history },
            coachAgentMode,
            controller.signal
          );
          for await (const event of stream) {
            switch (event.type) {
              case "tool_start":
                patchMessage(assistantId, (prev) => ({
                  ...prev,
                  toolCalls: [...(prev.toolCalls ?? []), event.call],
                }));
                break;
              case "tool_done":
                patchMessage(assistantId, (prev) => ({
                  ...prev,
                  toolCalls: (prev.toolCalls ?? []).map((call) =>
                    call.id === event.id
                      ? { ...call, status: event.status ?? ("done" as CoachToolCall["status"]), result: event.result }
                      : call
                  ),
                }));
                break;
              case "text_delta":
                patchMessage(assistantId, (prev) => ({ ...prev, text: prev.text + event.delta }));
                break;
              case "evidence":
                patchMessage(assistantId, (prev) => ({ ...prev, evidence: event.items }));
                break;
              case "plan":
                planRef.current = event.plan;
                setPlan(event.plan);
                patchMessage(assistantId, (prev) => ({ ...prev, planVersion: event.plan.version }));
                break;
              case "limitation":
                patchMessage(assistantId, (prev) => ({ ...prev, limitation: event.text }));
                break;
              default:
                break;
            }
          }
        } catch (streamError) {
          const aborted =
            streamError instanceof DOMException && streamError.name === "AbortError";
          if (!aborted) {
            const detail = streamError instanceof Error ? streamError.message : "未知错误";
            setError(detail);
            patchMessage(assistantId, (prev) => ({
              ...prev,
              text: prev.text || "这一轮没能完成，请重试。",
            }));
          }
        } finally {
          patchMessage(assistantId, (prev) => ({ ...prev, streaming: false }));
          setBusy(false);
          abortRef.current = null;
        }
      };

      void run();
    },
    [busy, context, patchMessage]
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    planRef.current = null;
    setPlan(null);
    setMessages([]);
    setBusy(false);
    setError(null);
  }, []);

  /** 中断当前一轮生成，保留已产出的内容 */
  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, plan, busy, error, send, stop, reset };
}
