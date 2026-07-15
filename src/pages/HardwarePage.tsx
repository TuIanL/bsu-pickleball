import { ArrowRight, BadgeCheck, Camera, Cpu, Gauge, Radar, ShieldCheck, Zap } from "lucide-react";
import type { NavigateFn } from "../app/navigationTypes";
import { PageFrame } from "../components/PageFrame";
import { FusionBlock } from "../components/FusionBlock";
import { hardwarePreview } from "../data/demoData";

export function HardwarePage({ onNavigate }: { onNavigate: NavigateFn }) {
  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Cpu size={16} aria-hidden="true" />
            二期硬件融合
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">{hardwarePreview.phaseLabel}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">{hardwarePreview.disclaimer}</p>
          <button className="mt-7 quiet-button" onClick={() => onNavigate("/vision")} type="button">
            返回视频分析
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="sport-card p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">TENG 阵列</p>
              <h2 className="mt-2 text-2xl font-black text-[#14241B]">3x3 甜区触点分布</h2>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-[#22C55E]/30 bg-[#22C55E]/12 px-3 py-2 text-xs font-black text-[#168A34]">
              <ShieldCheck size={14} aria-hidden="true" />
              模拟数据
            </span>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-3 rounded-[2rem] border border-[#DDE9D6] bg-[#F0F7EA] p-4">
            {hardwarePreview.sweetZone.map((cell) => (
              <span
                className={`aspect-square rounded-2xl border ${
                  cell.id === hardwarePreview.highlightedCellId
                    ? "border-[#22C55E] bg-[#22C55E]"
                    : "border-[#DDE9D6] bg-[#22C55E]/10"
                }`}
                key={cell.id}
                style={{ opacity: Math.max(cell.intensity, 0.22) }}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {hardwarePreview.metrics.map((metric) => (
          <article className="sport-card p-5 transition hover:-translate-y-1 hover:border-[#22C55E]/35" key={metric.id}>
            <Gauge className="text-[#168A34]" size={20} aria-hidden="true" />
            <span className="mt-4 block text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{metric.label}</span>
            <strong className="mt-2 block text-3xl font-black text-[#14241B]">{metric.value}</strong>
            <p className="mt-3 text-sm leading-6 text-slate-600">{metric.detail}</p>
          </article>
        ))}
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-2">
        {hardwarePreview.fusionPoints.map((point) => (
          <article className="sport-card p-5 sm:p-6" key={point.insight}>
            <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-center">
              <FusionBlock icon={<Camera size={18} aria-hidden="true" />} label="视觉" value={point.visual} />
              <Zap className="hidden text-[#D9FF3F] md:block" size={22} aria-hidden="true" />
              <FusionBlock icon={<Radar size={18} aria-hidden="true" />} label="球拍" value={point.sensor} />
            </div>
            <p className="mt-5 rounded-2xl border border-[#22C55E]/25 bg-[#22C55E]/12 p-4 text-sm font-semibold leading-6 text-[#168A34]">
              {point.insight}
            </p>
          </article>
        ))}
      </section>

      <section className="mt-6 sport-card p-5 sm:p-6">
        <div className="flex items-start gap-4">
          <BadgeCheck className="mt-1 text-[#168A34]" size={23} aria-hidden="true" />
          <div>
            <h2 className="text-2xl font-black text-[#14241B]">未来数据替换路径</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              当前页面数值全部来自本地模拟数据。未来真实 TENG 与 IMU 数据可以替换硬件模拟数据对象，
              视觉报告数据仍保持独立，便于做视觉 + 体感融合。
            </p>
          </div>
        </div>
      </section>
    </PageFrame>
  );
}
