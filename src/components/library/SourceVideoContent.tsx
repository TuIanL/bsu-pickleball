import { useState } from "react";
import { getVideoStreamUrl } from "../../services/analysisClient";

/**
 * 上传视频（upload）的视频 view 内容：直接经 `GET /api/videos/{videoId}/stream` 播放源视频。
 * 只负责「播放源视频」这一个职责，不含页面级导航/标题骨架。
 */
export function SourceVideoContent({ videoId, onNavigate }: { videoId?: string; onNavigate?: (path: string) => void }) {
  const [failed, setFailed] = useState(false);
  const src = getVideoStreamUrl(videoId);

  void onNavigate;

  if (!src) {
    return (
      <div className="grid place-items-center rounded-2xl border border-dashed border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-soft,#f7faf8)] py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">
        该视频暂无法定位播放地址
      </div>
    );
  }

  if (failed) {
    return (
      <div className="grid place-items-center rounded-2xl border border-dashed border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-soft,#f7faf8)] py-24 text-sm text-[var(--capture-text-muted,#8f9d96)]">
        视频暂不可用，请稍后重试
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--capture-border-default,#d9e3dd)] bg-[var(--capture-surface-video,#24302b)]">
      <video
        key={src}
        controls
        playsInline
        preload="metadata"
        className="aspect-video w-full"
        onError={() => setFailed(true)}
      >
        <source src={src} />
        当前浏览器不支持 HTML5 视频播放。
      </video>
    </div>
  );
}