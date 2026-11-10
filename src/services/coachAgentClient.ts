// =============================================================
// 教学助教 Agent —— 客户端
// -------------------------------------------------------------
// 两种模式：
//   demo —— 本地剧本，逐事件回放（比赛演示期默认，不依赖模型与网络）
//   live —— POST /api/coach/chat，读取 SSE 事件流（接入真实后端后启用）
//
// 切换方式：设置 VITE_COACH_AGENT_MODE=live，或在面板上传入 mode。
// 事件协议两边一致，UI 不需要知道当前是哪种模式。
// =============================================================
import {
  coachDemoScenes,
  coachFallbackAnswer,
  type CoachDemoScene,
  type CoachDemoToolSpec,
} from "../data/coachAgentDemo";
import type {
  CoachStreamEvent,
  CoachToolCall,
  CoachTrainingPlan,
  CoachTurnRequest,
} from "../types/coachAgent";

export type CoachAgentMode = "demo" | "live";

/** 与 analysisClient 保持同一后端入口：dev 下由 vite 代理到 127.0.0.1:8000 并注入 token */
const API_BASE_URL = import.meta.env.VITE_ANALYSIS_API_URL ?? "/__analysis_api";

/** 默认走真实模型；显式设置 VITE_COACH_AGENT_MODE=demo 可退回本地剧本 */
export const coachAgentDefaultMode: CoachAgentMode =
  (import.meta.env.VITE_COACH_AGENT_MODE as CoachAgentMode | undefined) === "demo" ? "demo" : "live";

/** @deprecated 使用 coachAgentDefaultMode；保留别名避免旧引用断裂 */
export const coachAgentMode = coachAgentDefaultMode;

/** 面板上的快捷问题（与剧本一一对应，保证演示顺序可控） */
export const coachSuggestedQuestions = coachDemoScenes.map((scene) => ({
  id: scene.id,
  text: scene.chip,
  shortText: scene.shortChip,
}));

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException("aborted", "AbortError"));
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** 按特异性排序匹配剧本：越具体的场景越先命中 */
function resolveScene(message: string): CoachDemoScene | null {
  const text = message.trim();
  for (const scene of coachDemoScenes) {
    if (scene.match.test(text)) return scene;
  }
  return null;
}

function toolCallFromSpec(spec: CoachDemoToolSpec, playerLabel: string, index: number): CoachToolCall {
  return {
    id: `tool-${index}-${spec.name}`,
    name: spec.name,
    title: spec.title,
    argument: spec.argument.replace(/\{\{player\}\}/g, playerLabel),
    result: "",
    status: "running",
  };
}

function withVersion(plan: CoachTrainingPlan, version: number): CoachTrainingPlan {
  return { ...plan, version, savedAt: new Date().toISOString() };
}

/** demo 模式：把剧本回放成事件流 */
async function* streamDemoTurn(
  request: CoachTurnRequest,
  signal?: AbortSignal
): AsyncGenerator<CoachStreamEvent> {
  const scene = resolveScene(request.message);
  const playerLabel = request.context.playerLabel || "该球员";

  if (!scene) {
    yield* streamText(coachFallbackAnswer, signal);
    return;
  }

  // 1) 工具调用：逐个 running → done，让教师看见 Agent 取了什么
  for (let index = 0; index < scene.tools.length; index += 1) {
    const spec = scene.tools[index];
    const call = toolCallFromSpec(spec, playerLabel, index);
    yield { type: "tool_start", call };
    await sleep(560 + index * 180, signal);
    yield { type: "tool_done", id: call.id, result: spec.result };
  }

  // 2) 回答正文（流式）
  const answer = !request.plan && scene.answerWithoutPlan ? scene.answerWithoutPlan : scene.answer;
  yield* streamText(answer.replace(/\{\{player\}\}/g, playerLabel), signal);

  // 3) 证据引用
  if (scene.evidence?.length) {
    yield { type: "evidence", items: scene.evidence };
  }

  // 4) 计划更新（版本号按当前会话递增，不写死）
  if (scene.plan) {
    const nextVersion = (request.plan?.version ?? 0) + 1;
    yield { type: "plan", plan: withVersion(scene.plan, nextVersion) };
  }

  // 5) 边界说明
  if (scene.limitation) {
    yield { type: "limitation", text: scene.limitation };
  }
}

/** 把一段文本拆成小片段流式吐出，模拟模型逐字输出 */
async function* streamText(text: string, signal?: AbortSignal): AsyncGenerator<CoachStreamEvent> {
  const chunkSize = 2;
  for (let i = 0; i < text.length; i += chunkSize) {
    yield { type: "text_delta", delta: text.slice(i, i + chunkSize) };
    // 标点处稍作停顿，读起来更像在组织语言
    const tail = text.slice(Math.max(0, i - 1), i + chunkSize);
    const pause = /[。！？\n]/.test(tail) ? 150 : 24;
    await sleep(pause, signal);
  }
}

/** live 模式：读取后端 SSE（每行一个 JSON 事件） */
async function* streamLiveTurn(
  request: CoachTurnRequest,
  signal?: AbortSignal
): AsyncGenerator<CoachStreamEvent> {
  const response = await fetch(`${API_BASE_URL}/api/coach/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok || !response.body) {
    // 503 通常表示本地代理缺 PICKLEBALL_API_TOKEN；404 表示后端未启动
    const hint =
      response.status === 503
        ? "本地代理未配置访问令牌，请用 npm run app:start 启动"
        : response.status === 404
          ? "后端未启动或未注册教学助教路由"
          : "请检查后端日志";
    throw new Error(`教学助教接口返回 ${response.status}（${hint}）`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed === "data: [DONE]") continue;
      const payload = trimmed.startsWith("data:") ? trimmed.slice(5).trim() : trimmed;
      try {
        yield JSON.parse(payload) as CoachStreamEvent;
      } catch {
        // 单行解析失败不打断整轮
      }
    }
  }
}

/** 统一入口：UI 只调它 */
export function streamCoachTurn(
  request: CoachTurnRequest,
  mode: CoachAgentMode = coachAgentDefaultMode,
  signal?: AbortSignal
): AsyncGenerator<CoachStreamEvent> {
  return mode === "live" ? streamLiveTurn(request, signal) : streamDemoTurn(request, signal);
}
