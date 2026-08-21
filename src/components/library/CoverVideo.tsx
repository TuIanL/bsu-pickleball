import { useEffect, useMemo, useRef, useState } from "react";
import { Video } from "lucide-react";
import type { CSSProperties } from "react";

/**
 * 封面预览能力模块（library-cover-preview）
 *
 * 目标：让比赛库封面在「本次浏览器会话内」可复用，避免每次从其它页面切回时
 * 重新请求视频流解码首帧。实现为 module 级 dataURL 缓存 + LRU 有界淘汰。
 *
 * 可靠性约定：**展示层绝不依赖解码成功**。
 * - 未命中缓存时，直接渲染 DOM `<video muted preload="metadata">`（与既有可用的回放/占位逻辑一致），封面必然显示首帧。
 * - 缓存是尽力而为的增强：后台用离屏视频在 `loadeddata`（首帧就绪、不 seek）时绘制 dataURL 落缓存；
 *   解码失败/流不支持 seek 时仅跳过缓存，封面仍正常显示，绝不阻塞或挂起。
 */

// 会话内封面帧缓存：streamUrl -> 首帧 dataURL（module 单例，跨路由不重置）
const FRAME_CACHE = new Map<string, string>();
const CACHE_LIMIT = 200;
const THUMB_MAX_WIDTH = 480;
// 离屏解码超时：超时放弃缓存（不影响封面显示）
const CAPTURE_TIMEOUT_MS = 8000;

export const FRAME_CACHE_LIMIT = CACHE_LIMIT;

/** 测试辅助：读取缓存 */
export function getCachedFrame(src: string): string | undefined {
  return FRAME_CACHE.get(src);
}

/** 写入缓存（含 LRU 淘汰）；解码落缓存与测试共用。 */
export function setCachedFrame(src: string, dataUrl: string): void {
  // 先 delete 再 set，把该 key 更新为最新访问
  FRAME_CACHE.delete(src);
  FRAME_CACHE.set(src, dataUrl);
  while (FRAME_CACHE.size > CACHE_LIMIT) {
    const oldest = FRAME_CACHE.keys().next().value;
    if (oldest === undefined) break;
    FRAME_CACHE.delete(oldest);
  }
}

/** 清空缓存（测试用）。 */
export function clearCoverCache(): void {
  FRAME_CACHE.clear();
}

/**
 * 尽力而为地抓取首帧 dataURL（离屏 <video>，在 `loadeddata` 时取当前帧即 time=0，
 * 不做 seek，避免流不支持 range/seek 时卡住）。失败/_超时返回 null，由调用层忽略。
 */
function captureFrame(src: string): Promise<string | null> {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.crossOrigin = "anonymous";
    let done = false;

    const finish = (dataUrl: string | null) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      video.removeEventListener("loadeddata", tryCapture);
      video.removeEventListener("canplay", tryCapture);
      video.removeEventListener("error", onFail);
      video.removeAttribute("src");
      try {
        video.load();
      } catch {
        /* 忽略清理异常 */
      }
      resolve(dataUrl);
    };

    function tryCapture() {
      try {
        const w = video.videoWidth || 16;
        const h = video.videoHeight || 9;
        const scale = Math.min(1, THUMB_MAX_WIDTH / w);
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(w * scale));
        canvas.height = Math.max(1, Math.round(h * scale));
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("canvas unsupported");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        finish(canvas.toDataURL("image/jpeg", 0.7));
      } catch {
        finish(null); // 跨域未通/CORS 未放行 → 跳过缓存，封面仍由 <video> 显示
      }
    }
    function onFail() {
      finish(null);
    }

    video.addEventListener("loadeddata", tryCapture, { once: true });
    video.addEventListener("canplay", tryCapture, { once: true });
    video.addEventListener("error", onFail, { once: true });
    const timer = setTimeout(() => finish(null), CAPTURE_TIMEOUT_MS);
    video.src = src;
  });
}

// 封面渲染状态。
// 未命中缓存 → video（DOM <video> 首帧必显，可靠）；命中缓存 → img（会话内即时）；无 src → empty。
//
// 注意：状态同步部分由初始化器推导，不在 effect 内同步 setState；src 变化时由调用方用 key 重新挂载。
type CoverRenderState =
  | { kind: "img"; url: string }
  | { kind: "video" }
  | { kind: "empty" };

function initialRenderState(src: string | undefined): CoverRenderState {
  if (!src) return { kind: "empty" };
  const cached = getCachedFrame(src);
  return cached ? { kind: "img", url: cached } : { kind: "video" };
}

/** 单画面封面：优先 DOM <video> 首帧显示；命中缓存用 <img>；无 src 中性占位。 */
export function CoverVideo({ src, className }: { src?: string; className?: string }) {
  const initial = useMemo(() => initialRenderState(src), [src]);
  const [state, setState] = useState<CoverRenderState>(initial);
  const running = useRef<string | null>(null);

  useEffect(() => {
    // 仅在未命中缓存时有 src 才做离屏抓帧（尽力而为）；失败/超时不改动 state，封面继续由 <video> 提供。
    if (!src || getCachedFrame(src) || running.current === src) return;
    running.current = src;
    let alive = true;
    captureFrame(src)
      .then((dataUrl) => {
        if (!alive || !dataUrl) return;
        setCachedFrame(src, dataUrl);
        setState({ kind: "img", url: dataUrl });
      })
      .finally(() => {
        running.current = null;
      });
    return () => {
      alive = false;
    };
  }, [src]);

  if (state.kind === "img") {
    return <img src={state.url} alt="" className={className} />;
  }
  if (state.kind === "video" && src) {
    return <video muted playsInline preload="metadata" src={src} className={className} data-cover="true" />;
  }
  return (
    <div className={`grid place-items-center ${className ?? ""}`} style={{ containerType: "size" } satisfies CSSProperties}>
      <Video size={36} aria-hidden="true" className="text-[var(--capture-text-muted,#8f9d96)]/60" />
    </div>
  );
}