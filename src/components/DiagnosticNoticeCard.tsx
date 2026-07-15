import type { DiagnosticNotice } from "../services/analysisDiagnostics";

export function DiagnosticNoticeCard({ notice, tone = "error" }: { notice: DiagnosticNotice; tone?: "error" | "info" }) {
  const visibleDetails = (notice.detailItems ?? []).filter(
    (item): item is [string, string | number] => item[1] !== undefined && item[1] !== null && `${item[1]}`.trim() !== ""
  );
  const toneClass =
    tone === "error"
      ? "border-[#FF4D4F]/30 bg-[#FF4D4F]/10 text-[#C92A2A]"
      : "border-[#2F80ED]/25 bg-[#2F80ED]/10 text-[#1E63B6]";

  return (
    <div className={`rounded-2xl border p-3 text-sm ${toneClass}`}>
      <strong className="font-black">{notice.title}</strong>
      <p className="mt-1 font-semibold leading-6">{notice.body}</p>
      {visibleDetails.length ? (
        <dl className="mt-3 grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
          {visibleDetails.map(([label, value]) => (
            <div className="rounded-xl bg-white/65 p-2" key={label}>
              <dt className="font-black text-slate-500">{label}</dt>
              <dd className="mt-1 break-words font-semibold text-[#14241B]">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
