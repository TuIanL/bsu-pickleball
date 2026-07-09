import type { ReactNode } from "react";
import type { AppPath } from "../types/report";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

function PageFrame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-[1480px] px-4 sm:px-6 lg:px-8 py-10 lg:py-12">
      {children}
    </div>
  );
}

/**
 * 上传模式页面组件
 * 薄 wrapper，直接渲染现有 NewAnalysisPage 逻辑
 * 接收 ?videoId=xxx&source=recording 参数，转交给 NewAnalysisPage
 */
export function UploadModePage({ onNavigate }: { onNavigate: NavigateFn }) {
  // 注意：此组件在 App.tsx 的路由解析中，upload route 的 videoId/source 已经在 RouteState 中
  // 由于 NewAnalysisPage 直接在 App.tsx 的 switch 中渲染，此处 UploadModePage 暂时不需要额外逻辑
  // 当 App.tsx 的 NewAnalysisPage 迁移到此文件后，此处将包含完整的上传分析逻辑
  return null;
}
