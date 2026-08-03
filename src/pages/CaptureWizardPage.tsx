import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Camera,
  CheckCircle2,
  Cpu,
  FileVideo,
  Sparkles,
  Zap,
} from "lucide-react";
import type { AppPath, FieldSessionCreate } from "../types/report";
import { createFieldSession } from "../services/analysisClient";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

type AnalysisIntent = "auto_analyze" | "ask_after_recording" | "save_only";

interface WizardForm {
  title: string;
  court_name: string;
  venue: string;
  capture_mode: string;
  match_format: string;
  camera_setup: string;
  notes: string;
  analysisIntent: AnalysisIntent;
  selectedCameraId: string;
}

const STEPS = ["采集场景", "摄像头方案", "分析设置"];

export function CaptureWizardPage({ onNavigate }: { onNavigate: NavigateFn }) {
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<WizardForm>({
    title: "",
    court_name: "",
    venue: "",
    capture_mode: "practice",
    match_format: "doubles",
    camera_setup: "single",
    notes: "",
    analysisIntent: "ask_after_recording",
    selectedCameraId: "",
  });

  const update = (patch: Partial<WizardForm>) => setForm((f) => ({ ...f, ...patch }));

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const fsPayload: FieldSessionCreate = {
        title: form.title || `${captureModeLabel[form.capture_mode]} - ${matchFormatLabel[form.match_format]}`,
        court_name: form.court_name,
        venue: form.venue,
        capture_mode: form.capture_mode,
        match_format: form.match_format,
        camera_setup: form.camera_setup,
        notes: form.notes,
      };

      const session = await createFieldSession(fsPayload);

      // 将 analysisIntent 存入 sessionStorage 作为刷新兜底
      try {
        sessionStorage.setItem(`capture.analysisIntent.${session.id}`, form.analysisIntent);
        if (form.selectedCameraId) {
          sessionStorage.setItem(`capture.selectedCameraId.${session.id}`, form.selectedCameraId);
        }
        sessionStorage.setItem(`capture.cameraSetup.${session.id}`, form.camera_setup);
      } catch {
        // sessionStorage 可能不可用，不影响主流程
      }

      onNavigate(`/capture/${session.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建采集任务失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[780px] px-4 sm:px-6 lg:px-8 py-10 lg:py-12">
      {/* 步骤指示器 */}
      <div className="mb-8">
        <div className="flex items-center justify-center gap-3">
          {STEPS.map((label, index) => (
            <div key={label} className="flex items-center gap-3">
              <div
                className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-bold transition ${
                  index === step
                    ? "bg-[#17231D] text-white shadow-sm"
                    : index < step
                      ? "bg-[#22C55E]/12 text-[#168A34]"
                      : "bg-slate-100 text-slate-400"
                }`}
              >
                <span className="grid size-5 place-items-center rounded-full bg-white/20 text-xs">
                  {index < step ? <CheckCircle2 size={14} /> : index + 1}
                </span>
                {label}
              </div>
              {index < STEPS.length - 1 && (
                <div className={`h-px w-8 ${index < step ? "bg-[#22C55E]/30" : "bg-slate-200"}`} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-6 rounded-xl border border-[#FF4D4F]/20 bg-[#FF4D4F]/8 px-4 py-3 text-sm font-medium text-[#C92A2A]">
          {error}
        </div>
      )}

      {/* Step 1: 采集场景 */}
      {step === 0 && (
        <div className="space-y-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="grid size-10 place-items-center rounded-xl bg-[#22C55E]/12 text-[#168A34]">
              <Camera size={20} />
            </div>
            <div>
              <h2 className="text-xl font-black text-[#14241B]">采集场景</h2>
              <p className="text-sm text-slate-500">描述这次球场采集的基本信息</p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-bold text-slate-700 mb-1.5">场地名称</label>
            <input
              className="field-input w-full"
              placeholder="例：北京体育大学匹克球训练场"
              value={form.court_name}
              onChange={(e) => update({ court_name: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-sm font-bold text-slate-700 mb-1.5">场馆</label>
            <input
              className="field-input w-full"
              placeholder="例：北京体育大学体育馆"
              value={form.venue}
              onChange={(e) => update({ venue: e.target.value })}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-1.5">采集类型</label>
              <div className="flex gap-2">
                {[
                  { value: "practice", label: "自由练习" },
                  { value: "match", label: "记分比赛" },
                  { value: "engineering", label: "工程测试" },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    className={`rounded-xl px-4 py-2.5 text-sm font-bold transition ${
                      form.capture_mode === opt.value
                        ? "bg-[#17231D] text-white"
                        : "border border-[#DDE9D6] bg-white text-slate-600 hover:border-[#22C55E]/30"
                    }`}
                    onClick={() => update({ capture_mode: opt.value })}
                    type="button"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-bold text-slate-700 mb-1.5">人数模式</label>
              <div className="flex gap-2">
                {[
                  { value: "singles", label: "单打" },
                  { value: "doubles", label: "双打" },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    className={`rounded-xl px-4 py-2.5 text-sm font-bold transition ${
                      form.match_format === opt.value
                        ? "bg-[#17231D] text-white"
                        : "border border-[#DDE9D6] bg-white text-slate-600 hover:border-[#22C55E]/30"
                    }`}
                    onClick={() => update({ match_format: opt.value })}
                    type="button"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-bold text-slate-700 mb-1.5">备注（选填）</label>
            <textarea
              className="field-input w-full min-h-[80px]"
              placeholder="任意备注信息…"
              value={form.notes}
              onChange={(e) => update({ notes: e.target.value })}
            />
          </div>
        </div>
      )}

      {/* Step 2: 摄像头方案 */}
      {step === 1 && (
        <div className="space-y-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="grid size-10 place-items-center rounded-xl bg-[#2F80ED]/12 text-[#2F80ED]">
              <Cpu size={20} />
            </div>
            <div>
              <h2 className="text-xl font-black text-[#14241B]">摄像头方案</h2>
              <p className="text-sm text-slate-500">选择采集使用的摄像头方案（具体摄像头在控制台中确认）</p>
            </div>
          </div>

          <div className="grid gap-4">
            {[
              {
                value: "single",
                title: "单摄模式",
                desc: "底线高机位单摄像头采集，适合快速部署。一个摄像头覆盖全场。",
                icon: Camera,
              },
              {
                value: "dual",
                title: "双摄模式",
                desc: "底线高机位 + 侧面机位双视角采集，提供更完整的球场覆盖。",
                icon: Camera,
              },
              {
                value: "debug_single",
                title: "工程调试",
                desc: "仅连接某一路摄像头，用于设备调试和测试。",
                icon: Cpu,
              },
            ].map((opt) => (
              <button
                key={opt.value}
                className={`sport-card flex items-start gap-4 p-5 text-left transition ${
                  form.camera_setup === opt.value
                    ? "border-[#2F80ED]/40 bg-[#2F80ED]/6"
                    : "hover:border-[#22C55E]/25"
                }`}
                onClick={() => update({ camera_setup: opt.value })}
                type="button"
              >
                <div
                  className={`grid size-10 shrink-0 place-items-center rounded-xl ${
                    form.camera_setup === opt.value
                      ? "bg-[#2F80ED]/15 text-[#2F80ED]"
                      : "bg-slate-100 text-slate-400"
                  }`}
                >
                  <opt.icon size={20} />
                </div>
                <div className="min-w-0">
                  <strong className="block text-base font-black text-[#14241B]">{opt.title}</strong>
                  <p className="mt-1 text-sm text-slate-500">{opt.desc}</p>
                </div>
                {form.camera_setup === opt.value && (
                  <div className="ml-auto grid size-6 shrink-0 place-items-center rounded-full bg-[#2F80ED] text-white">
                    <CheckCircle2 size={14} />
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Step 3: 分析设置 */}
      {step === 2 && (
        <div className="space-y-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="grid size-10 place-items-center rounded-xl bg-[#FF9500]/12 text-[#FF9500]">
              <Sparkles size={20} />
            </div>
            <div>
              <h2 className="text-xl font-black text-[#14241B]">分析设置</h2>
              <p className="text-sm text-slate-500">选择录制结束后的默认处理方式</p>
            </div>
          </div>

          <div className="grid gap-4">
            {[
              {
                value: "auto_analyze" as AnalysisIntent,
                title: "自动创建分析任务",
                desc: "停止录制后系统立即自动创建分析任务，无需手动操作。适合标准化采集中对效率要求高的场景。",
                icon: Zap,
              },
              {
                value: "ask_after_recording" as AnalysisIntent,
                title: "录制完成后再决定",
                desc: "停止录制后由你手动决定是否创建分析任务，灵活度最高。",
                icon: FileVideo,
              },
              {
                value: "save_only" as AnalysisIntent,
                title: "仅保存视频",
                desc: "仅保存录制视频文件，不自动创建分析任务。可在后期随时从任务历史中创建分析。",
                icon: Camera,
              },
            ].map((opt) => (
              <button
                key={opt.value}
                className={`sport-card flex items-start gap-4 p-5 text-left transition ${
                  form.analysisIntent === opt.value
                    ? "border-[#FF9500]/40 bg-[#FF9500]/6"
                    : "hover:border-[#22C55E]/25"
                }`}
                onClick={() => update({ analysisIntent: opt.value })}
                type="button"
              >
                <div
                  className={`grid size-10 shrink-0 place-items-center rounded-xl ${
                    form.analysisIntent === opt.value
                      ? "bg-[#FF9500]/15 text-[#FF9500]"
                      : "bg-slate-100 text-slate-400"
                  }`}
                >
                  <opt.icon size={20} />
                </div>
                <div className="min-w-0">
                  <strong className="block text-base font-black text-[#14241B]">{opt.title}</strong>
                  <p className="mt-1 text-sm text-slate-500">{opt.desc}</p>
                </div>
                {form.analysisIntent === opt.value && (
                  <div className="ml-auto grid size-6 shrink-0 place-items-center rounded-full bg-[#FF9500] text-white">
                    <CheckCircle2 size={14} />
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 底部导航按钮 */}
      <div className="mt-10 flex items-center justify-between">
        {step > 0 ? (
          <button
            className="quiet-button inline-flex items-center gap-2 px-5 py-2.5"
            onClick={() => setStep((s) => s - 1)}
            type="button"
          >
            <ArrowLeft size={16} />
            上一步
          </button>
        ) : (
          <div />
        )}

        {step < 2 ? (
          <button
            className="green-button inline-flex items-center gap-2 px-5 py-2.5"
            onClick={() => setStep((s) => s + 1)}
            type="button"
          >
            下一步
            <ArrowRight size={16} />
          </button>
        ) : (
          <button
            className="green-button inline-flex items-center gap-2 px-5 py-2.5"
            onClick={handleSubmit}
            disabled={submitting}
            type="button"
          >
            {submitting ? "创建中…" : "创建采集任务"}
            {!submitting && <CheckCircle2 size={16} />}
          </button>
        )}
      </div>
    </div>
  );
}

const captureModeLabel: Record<string, string> = {
  practice: "自由练习",
  match: "记分比赛",
  engineering: "工程测试",
};

const matchFormatLabel: Record<string, string> = {
  singles: "单打",
  doubles: "双打",
};
