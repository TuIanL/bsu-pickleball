## 1. Toast 组件

- [x] 1.1 新增 `src/components/platform/DeleteToast.tsx`：`DeleteToast({ kind: "success" | "attention"; message: string; onClose: () => void })`；success 绿色 + `useEffect` 内 `setTimeout(onClose, 3000)` 自动消失（清理函数 `clearTimeout`，无倒计时/进度条）；attention 琥珀色 + × 关闭按钮手动关闭（不启动定时器）；容器 `fixed bottom-4 right-4 z-50`；`role="status"` + `aria-live="polite"` + 关闭按钮 `aria-label`
- [x] 1.2 `index.css` 为 toast 添加最小淡入过渡（挂载淡入；可退化为无动画）

## 2. AnalysisTasksPage 改造

- [x] 2.1 状态收敛：移除 `deleteNotice`、`batchDeleteResult`、`fieldSessionBatchResult` 三个内联状态，新增单一 `deleteToast: { kind: DeleteToastKind; message: string } | null`
- [x] 2.2 分析任务删除回调：把 `deleted/blocked/missing/failed` 折叠成一行文案并 `setDeleteToast`——全成功 → `已删除 N 个任务`；受阻 → `已删除 N 个，M 个未删除` + 非零原因（`受保护 X · 未找到 Y · 失败 Z`）
- [x] 2.3 录制批量删除回调：`deleted/blocked/failed` → `已删除 N 个录制` 或 `已删除 N 个录制，M 个未删除（受保护/失败）`
- [x] 2.4 采集批量删除回调：同上 → `已删除 N 个采集任务` 或 `已删除 N 个采集任务，M 个未删除（受保护/失败）`
- [x] 2.5 移除 3 处内联渲染 JSX（`deleteNotice` 的 `DiagnosticNoticeCard` 块、`batchDeleteResult` 内联 div、`fieldSessionBatchResult` 内联 div），页面根挂载 `<DeleteToast />`；原 `setDeleteNotice(null)` 重置点改为 `setDeleteToast(null)`
- [x] 2.6 `loadError` 分支与 `DiagnosticNoticeCard` 组件保持不变（持久错误仍内联）

## 3. 验证

- [x] 3.1 `tsc -b` 与 `vite build` 通过
- [x] 3.2 手工验证：全成功 toast 3 秒自动消失且无倒计时、受阻 toast 需手动关闭、三处删除文案正确、`loadError` 仍内联展示
