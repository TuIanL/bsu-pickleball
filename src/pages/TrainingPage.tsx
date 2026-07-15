import { CheckCircle2, Dumbbell, Play } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { PageFrame } from "../components/PageFrame";
import { ProgressChart } from "../components/platform/ProgressChart";
import { RecommendedDrills } from "../components/RecommendedDrills";
import { progressPoints, trainingRecommendations } from "../data/demoData";

export function TrainingPage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Dumbbell size={16} aria-hidden="true" />
            训练与进展
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">训练建议页</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            每个建议都绑定报告证据，让球员知道为什么练、怎么练、下一次如何验证。
          </p>
        </div>
        <div className="sport-card p-5">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="text-[#168A34]" size={24} aria-hidden="true" />
            <div>
              <strong className="text-xl font-black text-[#14241B]">学习 · 练习 · 复测</strong>
              <p className="mt-1 text-sm text-slate-600">报告问题 → 教学内容 → 训练任务 → 下次复测目标</p>
            </div>
          </div>
          <div className="mt-5 grid gap-3">
            {trainingRecommendations.map((item) => (
              <article className="rounded-2xl border border-[#DDE9D6] bg-white/70 p-4" key={item.id}>
                <strong className="text-[#14241B]">{item.title}</strong>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.practiceTask}</p>
                <div className="mt-3 h-2 rounded-full bg-[#DFEADA]">
                  <span
                    className="block h-full rounded-full bg-[#22C55E]"
                    style={{
                      width: `${Math.min(
                        (Math.abs(item.progress.current - item.progress.previous) /
                          Math.abs(item.progress.target - item.progress.previous || 1)) *
                          100,
                        100
                      )}%`,
                    }}
                  />
                </div>
                <p className="mt-2 text-xs font-semibold text-[#168A34]">{item.nextTarget}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6">
        <RecommendedDrills onNavigate={onNavigate} />
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-[0.75fr_1.25fr]">
        <article className="sport-card p-5 sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#168A34]">教学内容</p>
          <h2 className="mt-2 text-2xl font-black text-[#14241B]">教学视频与动作对标占位</h2>
          <div className="mt-5 aspect-video rounded-3xl border border-[#DDE9D6] bg-[#F0F7EA] p-5">
            <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-[#BFD5B8] bg-white/70">
              <div className="text-center">
                <span className="mx-auto grid size-14 place-items-center rounded-full bg-[#22C55E]/15 text-[#168A34]">
                  <Play size={26} fill="currentColor" aria-hidden="true" />
                </span>
                <strong className="mt-4 block text-[#14241B]">反手轻吊动作对标</strong>
                <p className="mt-2 text-sm text-slate-500">真实内容接入前的产品级占位</p>
              </div>
            </div>
          </div>
        </article>
        <ProgressChart points={progressPoints} />
      </section>
    </PageFrame>
  );
}
