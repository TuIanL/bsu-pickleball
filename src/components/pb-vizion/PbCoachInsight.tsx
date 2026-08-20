import { useMemo } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import type {
  AnalysisReport,
  CoachNote,
  ProjectedFinding,
} from "../../types/report";

function getCoachSuggestion(report: AnalysisReport): string {
  const fallback = "保持第三拍进区率，优先过渡而非硬攻";

  try {
    const pi = report?.performanceInsights;
    if (pi?.findings && Array.isArray(pi.findings) && pi.findings.length > 0) {
      const top = pi.findings[0] as ProjectedFinding;
      if (top?.title && typeof top.title === "string" && top.title.trim()) {
        return top.title;
      }
    }
  } catch {
    // ignore
  }

  try {
    const findings = (report as unknown as { findings?: ProjectedFinding[] })
      .findings;
    if (Array.isArray(findings) && findings.length > 0) {
      const top = findings[0];
      if (top?.title && typeof top.title === "string" && top.title.trim()) {
        return top.title;
      }
    }
  } catch {
    // ignore
  }

  try {
    const notes = report?.coachNotes;
    if (Array.isArray(notes) && notes.length > 0) {
      const top = notes[0] as CoachNote;
      if (top?.title && typeof top.title === "string" && top.title.trim()) {
        return top.title;
      }
    }
  } catch {
    // ignore
  }

  return fallback;
}

function CoachAvatar3D() {
  return (
    <div
      className="rounded-full flex items-center justify-center text-white font-black shadow-lg shrink-0"
      style={{
        width: 120,
        height: 120,
        fontSize: 52,
        background:
          "linear-gradient(135deg, #F59E0B 0%, #FBBF24 40%, #FEF3C7 100%)",
        boxShadow:
          "0 8px 24px rgba(245, 158, 11, 0.25), inset 0 -4px 8px rgba(0,0,0,0.08)",
        border: "3px solid #FDE68A",
      }}
    >
      K
    </div>
  );
}

function Court3DPreview() {
  return (
    <div className="relative w-full" style={{ maxWidth: 380 }}>
      <svg
        viewBox="0 0 300 200"
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id="court-floor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ECFDF5" />
            <stop offset="100%" stopColor="#D1FAE5" />
          </linearGradient>
          <linearGradient id="trajectory" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#EF4444" />
            <stop offset="100%" stopColor="#FCA5A5" />
          </linearGradient>
        </defs>

        <polygon
          points="30,60 270,60 290,180 10,180"
          fill="url(#court-floor)"
          stroke="#14241B"
          strokeWidth="1.2"
        />
        <polygon
          points="30,60 270,60 260,95 40,95"
          fill="#FEF3C7"
          opacity="0.7"
        />
        <line
          x1="30"
          y1="60"
          x2="270"
          y2="60"
          stroke="#14241B"
          strokeWidth="1.5"
        />
        <line
          x1="40"
          y1="95"
          x2="260"
          y2="95"
          stroke="#22C55E"
          strokeWidth="1"
          strokeDasharray="4,3"
        />
        <line
          x1="50"
          y1="125"
          x2="250"
          y2="125"
          stroke="#22C55E"
          strokeWidth="1"
          strokeDasharray="4,3"
        />
        <line
          x1="150"
          y1="60"
          x2="150"
          y2="180"
          stroke="#14241B"
          strokeWidth="0.8"
        />

        <line
          x1="60"
          y1="30"
          x2="240"
          y2="30"
          stroke="#374151"
          strokeWidth="2"
        />
        <line
          x1="60"
          y1="30"
          x2="60"
          y2="60"
          stroke="#374151"
          strokeWidth="1.2"
        />
        <line
          x1="240"
          y1="30"
          x2="240"
          y2="60"
          stroke="#374151"
          strokeWidth="1.2"
        />
        <line
          x1="60"
          y1="30"
          x2="240"
          y2="30"
          stroke="#9ca3af"
          strokeWidth="0.6"
          strokeDasharray="2,2"
        />

        <path
          d="M 80,140 Q 150,30 220,110"
          stroke="url(#trajectory)"
          strokeWidth="2.5"
          fill="none"
          strokeLinecap="round"
        />
        <circle cx="80" cy="140" r="3.5" fill="#EF4444" />
        <circle cx="220" cy="110" r="3.5" fill="#EF4444" opacity="0.7" />

        <circle cx="70" cy="105" r="3" fill="#00FF41" opacity="0.95" />
        <circle cx="130" cy="150" r="3.2" fill="#00FF41" opacity="0.95" />
        <circle cx="190" cy="85" r="2.8" fill="#00FF41" opacity="0.95" />
        <circle cx="230" cy="165" r="3" fill="#00FF41" opacity="0.95" />
        <circle cx="110" cy="75" r="2.5" fill="#00FF41" opacity="0.8" />
        <circle cx="210" cy="135" r="2.6" fill="#00FF41" opacity="0.85" />
      </svg>

      <div className="absolute bottom-2 right-2 flex items-center gap-1.5 bg-white/90 backdrop-blur px-2.5 py-1.5 rounded-lg border border-slate-200 shadow-sm">
        <span className="text-sm" aria-hidden>
          🔒
        </span>
        <span className="text-xs font-medium text-slate-600">
          解锁 3D 控制
        </span>
      </div>
    </div>
  );
}

export default function PbCoachInsight() {
  const { report } = usePbReport();

  const suggestion = useMemo(() => getCoachSuggestion(report), [report]);

  return (
    <div
      className="rounded-2xl p-5 sm:p-6"
      style={{
        background: "var(--pb-coach-bg, #FFF7E6)",
        border: "1px solid var(--pb-coach-border, #FDE68A)",
        boxShadow: "0 1px 3px rgba(245, 158, 11, 0.06)",
      }}
    >
      <div className="flex flex-col md:flex-row items-start md:items-center gap-6 md:gap-8">
        <div className="w-full md:w-1/3 flex flex-col items-center md:items-start text-center md:text-left gap-4">
          <CoachAvatar3D />

          <div>
            <p className="font-bold text-base text-amber-900">教练指导</p>
            <p className="text-xs text-amber-700/80">匹克球认证教练 · 8 年经验</p>
          </div>

          <div className="w-full">
            <p className="font-semibold text-xs uppercase tracking-widest text-amber-700">
              教练洞察
            </p>
            <h3 className="mt-2 text-xl font-black leading-snug text-[#14241B]">
              {suggestion}
            </h3>
          </div>
        </div>

        <div className="flex-1 flex justify-center md:justify-end w-full md:w-2/3">
          <Court3DPreview />
        </div>
      </div>
    </div>
  );
}
