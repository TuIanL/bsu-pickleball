import type { ReactNode } from "react";
import type { AnalysisJobSummary, AppPath } from "../types/report";

type NavigateFn = (path: AppPath | `/upload` | `/upload?${string}`) => void;

/**
 * 任务历史页面
 * 
 * 薄 wrapper：暂不在本 change 内重写任务列表内部逻辑。
 * 由于 App.tsx 中 AnalysisTasksPage 仍作为内联组件存在，TasksPage
 * 目前只是一个占位。当 AnalysisTasksPage 被提取到本文件后，此处将包含完整的任务列表逻辑。
 * 
 * 当前通过 App.tsx 的 switch statement 中 "tasks" case 直接渲染 AnalysisTasksPage。
 */
export function TasksPage({ onNavigate, recentJob }: { onNavigate: NavigateFn; recentJob?: AnalysisJobSummary | null }) {
  // 薄 wrapper — 当 AnalysisTasksPage 从 App.tsx 分离后，这里将承载完整逻辑
  return null;
}
