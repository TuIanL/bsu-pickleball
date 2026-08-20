import { useMemo } from "react";
import { usePbReport } from "../../contexts/PbReportContext";
import type {
  AnalysisReport,
  CoachNote,
  TrainingRecommendation,
} from "../../types/report";

const THIRD_KEYWORDS = ["第三拍", "三拍", "third", "third shot"] as const;

function containsThirdKeyword(text: string): boolean {
  if (!text) return false;
  const lower = text.toLowerCase();
  return THIRD_KEYWORDS.some((kw) => lower.includes(kw.toLowerCase()));
}

function getThirdAdvice(report: AnalysisReport): string {
  const candidates: string[] = [];

  try {
    const coachNotes = report?.coachNotes;
    if (Array.isArray(coachNotes)) {
      for (const note of coachNotes as CoachNote[]) {
        const haystack = `${note?.title || ""} ${note?.body || ""}`;
        if (containsThirdKeyword(haystack)) {
          if (note?.body && note.body.trim()) candidates.push(note.body.trim());
          else if (note?.title && note.title.trim())
            candidates.push(note.title.trim());
        }
      }
    }
  } catch {
    // ignore
  }

  try {
    const recs = report?.trainingRecommendations;
    if (Array.isArray(recs)) {
      for (const r of recs as TrainingRecommendation[]) {
        const haystack = `${r?.title || ""} ${r?.learningContent || ""} ${
          r?.practiceTask || ""
        } ${r?.nextTarget || ""}`;
        if (containsThirdKeyword(haystack)) {
          if (r?.learningContent && r.learningContent.trim())
            candidates.push(r.learningContent.trim());
          else if (r?.practiceTask && r.practiceTask.trim())
            candidates.push(r.practiceTask.trim());
          else if (r?.title && r.title.trim())
            candidates.push(r.title.trim());
        }
      }
    }
  } catch {
    // ignore
  }

  try {
    const pi = report?.performanceInsights;
    if (pi?.recommendations && Array.isArray(pi.recommendations)) {
      for (const r of pi.recommendations) {
        const haystack = `${r?.title || ""} ${r?.detail || ""}`;
        if (containsThirdKeyword(haystack)) {
          if (r?.detail && r.detail.trim()) candidates.push(r.detail.trim());
          else if (r?.title && r.title.trim())
            candidates.push(r.title.trim());
        }
      }
    }
    if (pi?.findings && Array.isArray(pi.findings)) {
      for (const f of pi.findings) {
        const haystack = `${f?.title || ""} ${f?.diagnosis || ""} ${
          f?.impact || ""
        }`;
        if (containsThirdKeyword(haystack)) {
          if (f?.diagnosis && f.diagnosis.trim())
            candidates.push(f.diagnosis.trim());
          else if (f?.title && f.title.trim())
            candidates.push(f.title.trim());
        }
      }
    }
  } catch {
    // ignore
  }

  if (candidates.length > 0) {
    return candidates[0];
  }

  return "第三拍是匹克球中最关键的技术转换环节，建议使用稳定的轻吊或精准抽击把球送到对方非惯用侧过渡区，避免盲目扣杀导致被反击。若想精进第三拍，查看训练视频或咨询教练。";
}

export default function PbLegalThirds() {
  const { report } = usePbReport();

  const advice = useMemo(() => getThirdAdvice(report), [report]);

  return (
    <div className="pb-card p-5 sm:p-6">
      <div className="flex flex-row items-start gap-0">
        <div
          className="rounded-2xl inline-flex items-center justify-center shrink-0"
          style={{
            width: 48,
            height: 48,
            backgroundColor: "#FEF3C7",
            fontSize: 28,
            lineHeight: 1,
          }}
          aria-hidden
        >
          💡
        </div>

        <div className="flex-1 pl-4 min-w-0">
          <h3
            className="font-bold text-2xl"
            style={{ color: "var(--pb-text-primary, #111827)" }}
          >
            合法第三拍率
          </h3>
          <div className="mt-3 h-px bg-[var(--pb-card-border,#e5e7eb)]" />

          <p
            className="mt-4 text-sm leading-relaxed"
            style={{ color: "var(--pb-text-secondary, #6b7280)" }}
          >
            {advice}
          </p>

          <div className="mt-6 flex justify-end">
            <a
              href="#"
              className="pb-btn-primary inline-flex items-center gap-1.5 text-sm"
              onClick={(e) => {
                e.preventDefault();
                console.warn(
                  "合法第三拍跳转占位"
                );
              }}
            >
              查看你的击球数据
              <span aria-hidden>→</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
