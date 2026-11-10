// =============================================================
// 教学助教 Agent 面板 —— 报告页内的教育场景入口
// -------------------------------------------------------------
// 叙事顺序：当前上下文 → 提问 → 工具调用 → 依据 → 训练计划 → 复测目标
// 数据边界：只引用可核对指标；不具备的维度显式说明，不编造。
// =============================================================
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  Bot,
  Check,
  CircleAlert,
  GraduationCap,
  Loader2,
  RotateCcw,
  Sparkles,
  Wrench,
} from "lucide-react";
import { useCoachAgent } from "../../hooks/useCoachAgent";
import { usePlayerReportEvidence } from "../../hooks/usePlayerReportEvidence";
import { coachAgentDefaultMode, coachSuggestedQuestions, type CoachAgentMode } from "../../services/coachAgentClient";
import { buildCoachContext } from "../../services/coachAgentContext";
import type { AnalysisReport } from "../../types/report";
import type { CoachEvidenceItem, CoachMessage, CoachToolCall } from "../../types/coachAgent";
import PbCoachPlanCard from "./PbCoachPlanCard";
import PbCoachRichText from "./PbCoachRichText";

function QualityDot({ quality }: { quality: CoachEvidenceItem["quality"] }) {
  const color =
    quality === "high" ? "var(--pb-success)" : quality === "medium" ? "var(--pb-warning)" : "var(--pb-error)";
  return <span className="size-1.5 shrink-0 rounded-full" style={{ background: color }} />;
}

function ToolCallRow({ call }: { call: CoachToolCall }) {
  const running = call.status === "running";
  return (
    <div className="rounded-lg border border-[var(--pb-card-border)] bg-[var(--pb-page-bg)]/70 px-2.5 py-1.5">
      <div className="flex items-center gap-1.5">
        {running ? (
          <Loader2 size={12} className="animate-spin text-[var(--pb-primary-dark)]" aria-hidden="true" />
        ) : call.status === "failed" ? (
          <CircleAlert size={12} className="text-[var(--pb-error)]" aria-hidden="true" />
        ) : (
          <Check size={12} className="text-[var(--pb-success)]" aria-hidden="true" />
        )}
        <span className="text-[11px] font-bold text-[var(--pb-text-primary)]">{call.title}</span>
        <span className="min-w-0 truncate text-[10.5px] text-[var(--pb-text-muted)]">{call.argument}</span>
      </div>
      {call.result ? (
        <p className="mt-0.5 pl-[18px] text-[10.5px] leading-[1.4] text-[var(--pb-text-secondary)]">{call.result}</p>
      ) : null}
    </div>
  );
}

function EvidenceChips({ items }: { items: CoachEvidenceItem[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item.id}
          title={`${item.detail}${item.windowLabel ? ` · 可回放 ${item.windowLabel}` : ""}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-[var(--pb-card-border)] bg-[var(--pb-card-bg)] px-2 py-[3px] text-[10.5px] text-[var(--pb-text-secondary)]"
        >
          <QualityDot quality={item.quality} />
          <span className="font-mono font-bold text-[var(--pb-primary-dark)]">{item.id}</span>
          <span>{item.metric}</span>
          <span className="font-semibold text-[var(--pb-text-primary)]">{item.value}</span>
        </span>
      ))}
    </div>
  );
}

function AssistantBubble({ message, evidence }: { message: CoachMessage; evidence: CoachEvidenceItem[] }) {
  const refs = message.evidence?.length ? message.evidence : evidence;
  return (
    <div className="pb-coach-bubble flex gap-2">
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[var(--pb-primary)]/12 text-[var(--pb-primary-dark)]">
        <Bot size={15} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        {message.toolCalls?.length ? (
          <div className="mb-2 space-y-1">
            {message.toolCalls.map((call) => (
              <ToolCallRow call={call} key={call.id} />
            ))}
          </div>
        ) : null}

        {message.text ? (
          <PbCoachRichText text={message.text} streaming={message.streaming} />
        ) : message.streaming ? (
          <p className="text-[12px] text-[var(--pb-text-muted)]">正在读取证据…</p>
        ) : null}

        {message.text ? <EvidenceChips items={refs} /> : null}

        {message.limitation ? (
          <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-[var(--pb-warning)]/35 bg-[var(--pb-warning)]/8 px-2.5 py-1.5">
            <CircleAlert size={12} className="mt-[2px] shrink-0 text-[var(--pb-warning)]" aria-hidden="true" />
            <span className="text-[11px] leading-[1.45] text-[var(--pb-text-secondary)]">
              {message.limitation}
            </span>
          </div>
        ) : null}

        {message.planVersion ? (
          <p className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--pb-primary-dark)]">
            <Sparkles size={11} aria-hidden="true" />
            训练计划已更新为 v{message.planVersion}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default function PbCoachAgent({
  report,
  initialMode = coachAgentDefaultMode,
}: {
  report: AnalysisReport;
  /** 默认模式：模型模式调后端工具链；演示模式回放本地剧本（也是测试入口） */
  initialMode?: CoachAgentMode;
}) {
  const subject = useMemo(() => {
    const players = report.performanceInsights?.subjects?.filter((item) => item.kind === "player") ?? [];
    const first = players[0];
    return {
      id: first?.id ?? report.playerMarkers?.[0]?.id ?? "",
      name: first?.label ?? report.metadata?.athleteLabel ?? "该球员",
    };
  }, [report]);

  const evidence = usePlayerReportEvidence(report.jobId, report, subject.id);
  const context = useMemo(
    () => buildCoachContext(report, subject, evidence),
    [report, subject, evidence]
  );

  const [mode, setMode] = useState<CoachAgentMode>(initialMode);
  const { messages, plan, busy, error, send, reset, stop } = useCoachAgent(context, mode);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const isDemo = context.source === "demo";

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages]);

  const switchMode = (next: CoachAgentMode) => {
    if (next === mode) return;
    reset();
    setMode(next);
  };

  const submit = (text: string) => {
    if (!text.trim() || busy) return;
    send(text);
    setDraft("");
  };

  return (
    <section className="pb-coach-agent pb-card overflow-hidden">
      {/* 头部：身份 + 数据来源 */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--pb-card-border)] px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-[var(--pb-primary)] to-[var(--pb-primary-dark)] text-white">
            <GraduationCap size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-bold text-[var(--pb-text-primary)]">AI 教学助教</h2>
              <span className="rounded-full bg-[var(--pb-primary)]/12 px-2 py-0.5 text-[10px] font-bold text-[var(--pb-primary-dark)]">
                教育场景
              </span>
              <span
                className={
                  isDemo
                    ? "rounded-full bg-[var(--pb-warning)]/15 px-2 py-0.5 text-[10px] font-bold text-[var(--pb-warning)]"
                    : "rounded-full bg-[var(--pb-success)]/15 px-2 py-0.5 text-[10px] font-bold text-[var(--pb-success)]"
                }
              >
                {isDemo ? "演示样例数据" : "真实分析证据"}
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-[var(--pb-text-secondary)]">
              读取本次分析证据 → 检索教学练习 → 保存可复测的训练计划
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="flex items-center rounded-lg border border-[var(--pb-card-border)] p-0.5 text-[10.5px] font-semibold"
            title="模型模式：调用 DeepSeek V4.1-Flash 并执行工具；演示模式：回放本地剧本"
          >
            {([
              { key: "live" as const, label: "模型" },
              { key: "demo" as const, label: "演示" },
            ]).map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => switchMode(item.key)}
                className={
                  mode === item.key
                    ? "rounded-md bg-[var(--pb-primary)]/14 px-2 py-1 text-[var(--pb-primary-dark)]"
                    : "rounded-md px-2 py-1 text-[var(--pb-text-muted)] transition hover:text-[var(--pb-text-secondary)]"
                }
              >
                {item.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--pb-card-border)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--pb-text-secondary)] transition hover:border-[var(--pb-primary)]/40 hover:text-[var(--pb-primary-dark)]"
          >
            <RotateCcw size={12} aria-hidden="true" />
            重新开始
          </button>
        </div>
      </div>

      {/* 上下文条：让教师知道 Agent 读的是哪份数据 */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-[var(--pb-card-border)] bg-[var(--pb-page-bg)]/50 px-5 py-2 text-[11px] text-[var(--pb-text-secondary)]">
        <span>
          <span className="text-[var(--pb-text-muted)]">任务 </span>
          {context.taskLabel}
        </span>
        <span>
          <span className="text-[var(--pb-text-muted)]">球员 </span>
          {context.playerLabel}
        </span>
        <span className="min-w-0 truncate">
          <span className="text-[var(--pb-text-muted)]">数据 </span>
          {context.dataQuality}
        </span>
      </div>

      <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1.16fr)_minmax(0,0.84fr)]">
        {/* 左：对话 */}
        <div className="flex min-h-[420px] flex-col">
          <div ref={scrollRef} className="max-h-[430px] min-h-[300px] flex-1 space-y-3 overflow-y-auto pr-1">
            {messages.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[var(--pb-card-border)] bg-[var(--pb-page-bg)]/60 p-4">
                <p className="text-[13px] font-bold text-[var(--pb-text-primary)]">
                  我是本次训练的教学助教，只基于这份报告能核对的指标作答。
                </p>
                <p className="mt-1.5 text-[12px] leading-[1.6] text-[var(--pb-text-secondary)]">
                  能读到的：移动距离、站位覆盖、回位间隔、进区率。读不到的：击球类型、甜区命中率——这些会直接说
                  「判断不了」，不给你一个看起来合理的数字。
                </p>
                <div className="mt-3 grid gap-1.5">
                  {coachSuggestedQuestions.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => submit(item.text)}
                      className="group flex items-center gap-2 rounded-lg border border-[var(--pb-card-border)] bg-[var(--pb-card-bg)] px-3 py-2 text-left text-[12px] text-[var(--pb-text-primary)] transition hover:border-[var(--pb-primary)]/45 hover:bg-[var(--pb-primary)]/[0.04]"
                    >
                      <Sparkles
                        size={12}
                        className="shrink-0 text-[var(--pb-primary)] transition group-hover:scale-110"
                        aria-hidden="true"
                      />
                      {item.text}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((message) =>
                message.role === "user" ? (
                  <div className="pb-coach-bubble flex justify-end" key={message.id}>
                    <p className="max-w-[82%] rounded-2xl rounded-tr-sm bg-[var(--pb-primary-dark)] px-3.5 py-2 text-[13px] leading-[1.6] text-white">
                      {message.text}
                    </p>
                  </div>
                ) : (
                  <AssistantBubble message={message} evidence={context.evidence} key={message.id} />
                )
              )
            )}
          </div>

          {error ? (
            <p className="mt-2 rounded-lg bg-[var(--pb-error)]/10 px-2.5 py-1.5 text-[11px] text-[var(--pb-error)]">
              请求失败：{error}
            </p>
          ) : null}

          <form
            className="mt-3 flex items-center gap-2 rounded-xl border border-[var(--pb-card-border)] bg-[var(--pb-card-bg)] px-3 py-2 focus-within:border-[var(--pb-primary)]/50"
            onSubmit={(event) => {
              event.preventDefault();
              submit(draft);
            }}
          >
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="例如：只有 8 分钟，而且是两个人一起练"
              className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--pb-text-primary)] outline-none placeholder:text-[var(--pb-text-muted)]"
              aria-label="向教学助教提问"
            />
            {busy ? (
              <button
                type="button"
                onClick={stop}
                className="shrink-0 rounded-lg border border-[var(--pb-card-border)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--pb-text-secondary)]"
              >
                停止
              </button>
            ) : (
              <button
                type="submit"
                disabled={!draft.trim()}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-[var(--pb-primary-dark)] px-2.5 py-1.5 text-[11px] font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-40"
              >
                发送
                <ArrowUp size={12} aria-hidden="true" />
              </button>
            )}
          </form>

          {messages.length > 0 && !busy ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {coachSuggestedQuestions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => submit(item.text)}
                  className="rounded-full border border-[var(--pb-card-border)] bg-[var(--pb-page-bg)] px-2.5 py-1 text-[10.5px] font-semibold text-[var(--pb-text-secondary)] transition hover:border-[var(--pb-primary)]/45 hover:text-[var(--pb-primary-dark)]"
                >
                  {item.shortText}
                </button>
              ))}
            </div>
          ) : null}

          <p className="mt-1.5 flex items-center gap-1 text-[10.5px] text-[var(--pb-text-muted)]">
            <Wrench size={10} aria-hidden="true" />
            依据来自后端工具调用；计划随对话迭代，不覆盖历史版本
          </p>
        </div>

        {/* 右：计划 */}
        <PbCoachPlanCard plan={plan} evidence={context.evidence} />
      </div>
    </section>
  );
}
