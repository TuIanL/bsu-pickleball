import { CoverVideo } from "./CoverVideo";

/**
 * 封面渲染按来源分派（library-cover-preview）
 * - 单摄 / upload       → 单画面 object-cover
 * - 双摄 sync_recording → cam_1 | cam_2 左右拼接，各半幅 object-cover 裁黑边 + 「双摄」角标
 * 双摄某一路机位流缺失 → 该半幅中性占位。
 */

export type CoverSourceType = "upload" | "recording" | "sync_recording";

interface CoverLayoutInput {
  sourceType: CoverSourceType;
  cameraSetup?: "single" | "dual";
  coverVideoUrl?: string;
  cameraCoverSources?: { cam_1?: string; cam_2?: string };
}

export type CoverLayout =
  | { kind: "single"; src?: string }
  | { kind: "dual"; left?: string; right?: string };

/** 纯函数：根据素材元数据推导封面布局（可单测）。 */
export function coverLayout(item: CoverLayoutInput): CoverLayout {
  const isDual = item.cameraSetup === "dual" || item.sourceType === "sync_recording";
  const cam1 = item.cameraCoverSources?.cam_1;
  const cam2 = item.cameraCoverSources?.cam_2;
  if (isDual && (cam1 || cam2)) {
    return { kind: "dual", left: cam1, right: cam2 };
  }
  return { kind: "single", src: item.coverVideoUrl };
}

interface LibraryCoverProps {
  item: CoverLayoutInput;
}

/** 按 item 分派渲染封面；外层需提供适合版式的 aspect/object-contain 容器。 */
export function LibraryCover({ item }: LibraryCoverProps) {
  const layout = coverLayout(item);

  if (layout.kind === "dual") {
    return (
      <div className="relative flex h-full w-full items-stretch overflow-hidden">
        <CoverVideo
          key={layout.left ?? "left-empty"}
          src={layout.left}
          className="h-full w-1/2 shrink-0 object-cover"
        />
        <CoverVideo
          key={layout.right ?? "right-empty"}
          src={layout.right}
          className="h-full w-1/2 shrink-0 border-l border-white/60 object-cover"
        />
        <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-black/45 px-2 py-0.5 text-[10px] font-bold text-white">
          双摄
        </span>
      </div>
    );
  }

  return <CoverVideo key={layout.src ?? "no-src"} src={layout.src} className="h-full w-full object-cover" />;
}