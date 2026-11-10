// =============================================================
// 训练计划卡 —— 教学助教生成的计划（带版本，可连续改写）
// -------------------------------------------------------------
// 目标 / 时长 / 人数 / 分步安排 / 每步依据 / 下次复测指标
// =============================================================
import { CalendarClock, CheckCircle2, ClipboardList, Clock3, Target, Users } from "lucide-react";
import type { CoachEvidenceItem, CoachTrainingPlan } from "../../types/coachAgent";

function Pill({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--pb-card-border)] bg-[var(--pb-page-bg)] px-2.5 py-1 text-xs font-semibold text-[var(--pb-text-secondary)]">
      {icon}
      {children}
    </span>
  );
}

function EvidenceTag({
  ids,
  evidenceById,
}: {
  ids: string[];
  evidenceById: Map<string, CoachEvidenceItem>;
}) {
  if (!ids.length) return null;
  return (
    <span className="mt-1.5 flex flex-wrap gap-1">
      {ids.map((id) => {
        const item = evidenceById.get(id);
        return (
          <span
            key={id}
            title={item ? `${item.metric} ${item.value} · ${item.detail}` : id}
            className="rounded border border-[var(--pb-primary)]/30 bg-[var(--pb-primary)]/8 px-1.5 py-[1px] font-mono text-[10px] font-bold text-[var(--pb-primary-dark)]"
          >
            {id}
          </span>
        );
      })}
    </span>
  );
}

export default function PbCoachPlanCard({
  plan,
  evidence,
}: {
  plan: CoachTrainingPlan | null;
  evidence: CoachEvidenceItem[];
}) {
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));

  if (!plan) {
    return (
      <div className="flex h-full min-h-[280px] flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--pb-card-border)] bg-[var(--pb-page-bg)]/60 p-6 text-center">
        <span className="grid size-11 place-items-center rounded-full bg-[var(--pb-primary)]/10 text-[var(--pb-primary-dark)]">
          <ClipboardList size={22} aria-hidden="true" />
        </span>
        <p className="mt-3 text-sm font-bold text-[var(--pb-text-primary)]">还没有训练计划</p>
        <p className="mt-1.5 max-w-[26ch] text-xs leading-5 text-[var(--pb-text-secondary)]">
          先提一个训练目标，Agent 会检索练习库、绑定本次证据，保存成可继续改写的版本。
        </p>
      </div>
    );
  }

  return (
    <div
      key={plan.version}
      className="pb-coach-plan flex h-full flex-col rounded-2xl border border-[var(--pb-card-border)] bg-[var(--pb-card-bg)] p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-[var(--pb-primary)]/12 text-[var(--pb-primary-dark)]">
            <ClipboardList size={16} aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-bold text-[var(--pb-text-primary)]">训练计划</p>
            <p className="text-[11px] text-[var(--pb-text-muted)]">教学助教生成 · 教师可改</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-[var(--pb-primary)]/12 px-2 py-0.5 font-mono text-[11px] font-bold text-[var(--pb-primary-dark)]">
          v{plan.version}
        </span>
      </div>

      <p className="mt-3 text-sm leading-6 font-semibold text-[var(--pb-text-primary)]">{plan.goal}</p>

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        <Pill icon={<Clock3 size={12} aria-hidden="true" />}>{plan.totalMinutes} 分钟</Pill>
        <Pill icon={<Users size={12} aria-hidden="true" />}>{plan.groupSize}</Pill>
        <Pill icon={<Target size={12} aria-hidden="true" />}>{plan.level}</Pill>
      </div>

      <div className="mt-4 flex-1">
        {plan.steps.map((item, index) => {
          const last = index === plan.steps.length - 1;
          return (
            <div className="flex gap-2.5" key={item.id}>
              <div className="flex flex-col items-center pt-1.5">
                <span
                  className="size-2.5 shrink-0 rounded-full"
                  style={{
                    background: last ? "transparent" : "var(--pb-primary)",
                    border: last ? "2px solid var(--pb-primary)" : "none",
                  }}
                />
                {!last && <span className="my-1 w-px flex-1 bg-[var(--pb-card-border)]" />}
              </div>
              <div className="min-w-0 flex-1 pb-3.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[13px] leading-5 font-bold text-[var(--pb-text-primary)]">{item.title}</p>
                  <span className="shrink-0 font-mono text-[11px] font-bold text-[var(--pb-primary-dark)]">
                    {item.minutes}′
                  </span>
                </div>
                {item.note ? (
                  <p className="mt-0.5 text-[11.5px] leading-[1.45] text-[var(--pb-text-secondary)]">{item.note}</p>
                ) : null}
                <EvidenceTag ids={item.evidenceIds} evidenceById={evidenceById} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-1 rounded-xl border border-dashed border-[var(--pb-primary)]/35 bg-[var(--pb-primary)]/[0.06] p-3">
        <p className="flex items-center gap-1.5 text-[11px] font-bold tracking-wide text-[var(--pb-primary-dark)]">
          <CalendarClock size={12} aria-hidden="true" />
          下次复测
        </p>
        <ul className="mt-1.5 space-y-1">
          {plan.reassess.map((item) => (
            <li key={item} className="flex gap-1.5 text-[11.5px] leading-[1.45] text-[var(--pb-text-secondary)]">
              <span className="mt-[5px] size-1 shrink-0 rounded-full bg-[var(--pb-primary)]" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-[var(--pb-card-border)] pt-2.5">
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--pb-primary-dark)]">
          <CheckCircle2 size={12} aria-hidden="true" />
          已保存 · 可继续修改
        </span>
        <span className="font-mono text-[10px] text-[var(--pb-text-muted)]">
          证据 {plan.evidenceIds.join(" · ") || "—"}
        </span>
      </div>
    </div>
  );
}
