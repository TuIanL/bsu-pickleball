## Why

任务管理页删除任务后，删除结果以内联大块占满版面：分析任务删除用 `DiagnosticNoticeCard` 显示"已删除/受保护/未找到/失败"4 格明细，录制批量删除与采集批量删除各用一整块内联色块。这些提示挤压列表内容、需等下一次操作才消失，对一个"3 秒就能看完"的一次性结果来说过于笨重。

## What Changes

- **新增轻量浮动 Toast**：右下角固定定位（`fixed bottom-4 right-4`）的紧凑删除结果提示，不占任何版面空间，不加第三方依赖。
- **统一 3 处删除结果**：分析任务删除、录制批量删除、采集任务批量删除的结果提示全部改用同一个 toast 机制，移除内联的 `DiagnosticNoticeCard` 与两个批量删除结果 div。
- **无受阻自动消失**：全部删除成功时显示绿色单行"已删除 N 个任务"，3 秒后自动消失，**不显示倒计时/进度条**。
- **有受阻手动关闭**：存在受保护/未找到/失败时显示琥珀色提示（单行简述删除数与受阻项），带 × 关闭按钮，需用户手动关闭。
- **loadError 保留内联**：页面加载失败红块是持久错误状态，不改为 toast，维持现状。
- **不动后端**：数据沿用删除函数已返回的 `deleted/blocked/failed` 计数，`delete` API 与响应结构不变。

## Capabilities

### New Capabilities
- `delete-result-toast`: 定义轻量右下角浮动删除结果 toast 的渲染与交互契约——固定定位不占版面、无受阻时自动 3 秒消失（无倒计时）、有受阻时手动关闭、文案仅一行（删除数与受阻简述）。

### Modified Capabilities
- `analysis-task-management`: "Delete feedback and refresh" 需求的删除反馈呈现方式变更——由内联提示块改为浮动 toast（自动消失 / 手动关闭），`loadError` 等持久错误仍内联展示。

## Impact

- **前端**：新增 `src/components/platform/DeleteToast.tsx`（轻量 toast 组件）；`AnalysisTasksPage.tsx` 中 `deleteNotice`、`batchDeleteResult`、`fieldSessionBatchResult` 三处内联渲染改造为统一 toast 调用，删除相关内联块。
- **保留**：`DiagnosticNoticeCard` 组件仍被 `loadError` 等持久错误使用，不删除。
- **后端**：无改动；`delete` API 与返回计数不变。
