// =============================================================
// 教学助教独立页 —— 无球员报告时的落点
// -------------------------------------------------------------
// 场景：样例报告 / 未完成球员确认的任务。此时球员报告为空，
// 仍要让教师（和评委）看到一个完整、边界清楚的教学复盘入口。
// =============================================================
import { Database, ShieldCheck, Workflow } from "lucide-react";
import type { AnalysisReport } from "../../types/report";
import PbCoachAgent from "./PbCoachAgent";

const FLOW_NOTES = [
  {
    icon: Database,
    title: "数据从哪来",
    body: "人员检测、姿态与轨迹投影产出的移动距离、站位覆盖、回位间隔。不含球拍数据与球路推断。",
  },
  {
    icon: Workflow,
    title: "Agent 做什么",
    body: "读取本次证据 → 检索教学练习库 → 保存带版本的计划。每次改写保留原目标与证据引用，不覆盖历史。",
  },
  {
    icon: ShieldCheck,
    title: "明确边界",
    body: "击球类型、甜区命中率、战术评价当前不产出。问到这些，Agent 会直接说明判断不了，不给近似数字。",
  },
];

export default function PbCoachAgentStandalone({ report }: { report: AnalysisReport }) {
  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5 px-6 py-8">
      <header>
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--pb-primary-dark)]">
          Education · Coaching Assistant
        </p>
        <h1 className="mt-2 text-2xl font-black text-[var(--pb-text-primary)] sm:text-3xl">教学复盘</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--pb-text-secondary)]">
          把一次已分析的训练，转成看得见依据、可复测的练习计划。教师提问，Agent 取证据、选练习、存计划；
          改时长或人数时，原目标与依据不丢。
        </p>
      </header>

      <PbCoachAgent report={report} />

      <div className="grid gap-4 md:grid-cols-3">
        {FLOW_NOTES.map((note) => {
          const Icon = note.icon;
          return (
            <article className="pb-card p-4" key={note.title}>
              <span className="grid size-8 place-items-center rounded-lg bg-[var(--pb-primary)]/12 text-[var(--pb-primary-dark)]">
                <Icon size={16} aria-hidden="true" />
              </span>
              <h2 className="mt-2.5 text-sm font-bold text-[var(--pb-text-primary)]">{note.title}</h2>
              <p className="mt-1.5 text-[12px] leading-[1.6] text-[var(--pb-text-secondary)]">{note.body}</p>
            </article>
          );
        })}
      </div>

      <p className="text-[11px] leading-5 text-[var(--pb-text-muted)]">
        {report.source === "demo"
          ? "当前为脱敏样例报告：指标为示例值，用于演示完整链路。绑定真实分析任务后，证据区自动替换为该任务的可核对指标与表现洞察。"
          : "本次任务未识别到可报告的球员主体，因此未展示球员报告。在任务里补齐球员确认后重新打开本页，即可看到完整报告。"}
      </p>
    </div>
  );
}
