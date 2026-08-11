import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import type { NavigateFn, NavigatePath } from "../app/navigationTypes";
import { PageFrame } from "./PageFrame";
import { DiagnosticNoticeCard } from "./DiagnosticNoticeCard";

export function StatusState({
  body,
  notice,
  onNavigate,
  backPath,
  title,
}: {
  body: string;
  notice?: DiagnosticNotice | null;
  onNavigate: NavigateFn;
  backPath?: NavigatePath;
  title: string;
}) {
  return (
    <PageFrame>
      <section className="sport-card p-8 text-center">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">分析任务</p>
        <h1 className="mt-3 text-4xl font-black text-[#14241B]">{title}</h1>
        <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-600">{body}</p>
        {notice ? (
          <div className="mx-auto mt-5 max-w-3xl text-left">
            <DiagnosticNoticeCard notice={notice} />
          </div>
        ) : null}
        <div className="mt-6 flex justify-center gap-3">
          <button className="green-button" onClick={() => onNavigate("/analysis/new")} type="button">
            上传新视频
          </button>
          <button className="quiet-button" onClick={() => onNavigate(backPath ?? "/analysis/tasks")} type="button">
            返回任务管理
          </button>
          <button className="quiet-button" onClick={() => onNavigate("/vision")} type="button">
            查看演示
          </button>
        </div>
      </section>
    </PageFrame>
  );
}
