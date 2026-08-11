import { useEffect, useState } from "react";
import { getCameraPreviewUrl, getShowcaseRuntimeStatus, getShowcaseStreamUrl } from "../services/analysisClient";
import type { AppPath } from "../app/navigationTypes";
import type { ShowcaseRuntimeStatus } from "../types/report";

type Props = { runtimeId: string; onNavigate: (path: AppPath) => void };

export function ShowcaseDisplayPage({ runtimeId }: Props) {
  const [status, setStatus] = useState<ShowcaseRuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamFailed, setStreamFailed] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let disposed = false;
    const poll = async () => {
      try {
        const next = await getShowcaseRuntimeStatus(runtimeId);
        if (!disposed) { setStatus(next); setError(null); }
      } catch (err) {
        if (!disposed) setError(err instanceof Error ? err.message : "展示旁路已停止");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [runtimeId]);

  const cameras = ["cam_1", "cam_2"] as const;
  return (
    <main className="min-h-screen bg-[#101512] p-4 text-white sm:p-6">
      <header className="mb-4 flex items-center justify-between gap-4">
        <div><p className="text-xs uppercase tracking-[0.18em] text-[#8FA99A]">Pickleball Live Showcase</p><h1 className="mt-1 text-xl font-black">双摄实时展示</h1></div>
        <div className="text-right text-xs text-[#B9C9BF]">{status ? `${status.status} · 目标 ${status.target_inference_fps} fps` : "连接展示旁路…"}<br />{status?.degradation_reasons.join("；")}</div>
      </header>
      {error && <div className="mb-4 rounded-lg border border-[#D9943C]/50 bg-[#3A2814] px-3 py-2 text-sm text-[#FFD6A0]">展示流不可用：{error}。录制和录制后分析不受影响。</div>}
      <div className="grid min-h-[calc(100vh-120px)] gap-4 lg:grid-cols-2">
        {cameras.map((slot) => {
          const camera = status?.cameras[slot];
          const stream = status && !streamFailed[slot] ? getShowcaseStreamUrl(runtimeId, slot) : camera?.camera_id ? getCameraPreviewUrl(camera.camera_id) : undefined;
          return (
            <section key={slot} className="relative flex min-h-[38vh] flex-col overflow-hidden rounded-lg border border-[#33473B] bg-[#17221B]">
              {stream ? <img className="min-h-0 flex-1 object-contain" src={stream} alt={`${slot} 实时展示`} onError={() => setStreamFailed((current) => ({ ...current, [slot]: true }))} /> : <div className="grid flex-1 place-items-center text-sm text-[#8FA99A]">等待 {slot} 展示流</div>}
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#33473B] px-3 py-2 text-xs text-[#C9D8CF]">
                <strong>{slot === "cam_1" ? "机位 A" : "机位 B"}</strong>
                <span>{camera ? `${camera.person_status} · ${camera.actual_inference_fps.toFixed(1)} fps · ${camera.track_count} 人` : "未连接"}</span>
                <span>球：{camera?.ball_status ?? "未启用"}</span>
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}
