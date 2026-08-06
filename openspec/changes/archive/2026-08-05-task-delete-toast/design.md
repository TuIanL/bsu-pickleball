## Context

`AnalysisTasksPage.tsx`（任务管理页）现有 3 处删除结果提示都以"内联大块"呈现，挤占列表版面：

1. **分析任务删除**（line ~700）：`deleteNotice` → 全宽 `DiagnosticNoticeCard`（标题 + 正文 + "已删除/受保护/未找到/失败" 2 列 4 格明细），且要等下一次选择操作才清空。
2. **录制批量删除**（line ~898）：内联色块 div，绿/红提示 + 计数。
3. **采集任务批量删除**（line ~958）：同上模式。

代码库无任何 toast 组件；`DiagnosticNoticeCard` 还被 `loadError`（加载失败红块）等持久错误使用，需保留。删除相关数据（`deleted/blocked/failed`，分析任务另有 `not_found`）全部来自前端已调用的 delete API，无后端改动。

## Goals / Non-Goals

**Goals:**

- 新增一个轻量浮动 toast 组件（右下角固定定位），3 处删除结果统一使用。
- 全成功：绿色单行"已删除 N 个任务"，3 秒自动消失，**无倒计时/进度条**。
- 有受阻（受保护/未找到/失败）：琥珀色单行（删除数 + 受阻简述），带 × 需手动关闭。
- `loadError` 等持久错误保留内联展示，不改为 toast。

**Non-Goals:**

- 不引入 toast 第三方依赖（sonner/radix 等）。
- 不做 toast 队列/堆叠（单 toast 状态，新删除替换旧的即可）。
- 不改后端 delete API 与返回结构。
- 不处理其它页面/其它类型的持久错误转 toast。

## Decisions

### D1：组件形态——单个 `DeleteToast` 组件，页面持有单一 toast 状态

新增 `src/components/platform/DeleteToast.tsx`：

```tsx
type DeleteToastKind = "success" | "attention";

interface DeleteToastProps {
  kind: DeleteToastKind;
  message: string;
  onClose: () => void;
}
```

- `kind === "success"`：绿色（`#22C55E` 系），**不显示关闭按钮**，组件内部 `useEffect` 里 `setTimeout(onClose, 3000)` 自动消失，**只定时器、不画倒计时**。
- `kind === "attention"`：琥珀色（`#F59E0B` 系），显示 × 关闭按钮，**不启动定时器**，等用户手动 `onClose`。
- 渲染容器：`fixed bottom-4 right-4 z-50`，单行文字 + 可选 ×。

选择"组件自管理自动消失定时器"而非页面统一 `setTimeout`：把"成功 3 秒消失 / 受阻手动关"的差异封装在组件里，3 处调用方只传 `kind` + `message`，逻辑不重复。定时器放 `useEffect` 并在清理函数 `clearTimeout`，避免快速连续删除时旧定时器误关新 toast。

**备选被否**：引入 sonner/radix toast 库——功能超需求且与项目"手写轻量组件"的既有风格不符；`DiagnosticNoticeCard` 加 fixed 壳复用——卡片内容仍是 4 格明细大块，不满足"只需一行"的诉求。

### D2：状态统一——3 个独立状态收敛为 1 个 toast 状态

- 删除 `deleteNotice`、`batchDeleteResult`、`fieldSessionBatchResult` 三个内联状态与渲染块。
- 新增单一 `deleteToast: { kind: DeleteToastKind; message: string } | null`。
- 三处删除完成的回调各自把计数折叠成一行文案后 `setDeleteToast(...)`；新 toast 直接替换旧 toast（无堆叠）。
- 页面卸载即消失（组件随页面卸载，无全局持久化）。

### D3：文案——单行，删除数 + 受阻简述（只含非零项）

| 场景 | 文案 |
|---|---|
| 分析任务全成功 | `已删除 N 个任务` |
| 分析任务受阻 | `已删除 N 个，M 个未删除`（后接非零原因简写，如 `受保护 1 · 未找到 1 · 失败 1`） |
| 录制批量全成功 | `已删除 N 个录制` |
| 录制批量受阻 | `已删除 N 个录制，M 个未删除（受保护/失败）` |
| 采集批量全成功 | `已删除 N 个采集任务` |
| 采集批量受阻 | `已删除 N 个采集任务，M 个未删除（受保护/失败）` |

受阻文案只拼接非零的计数项，避免一行出现 `0`。明细 4 格网格（已删除/受保护/未找到/失败）整体移除。

### D4：`loadError` 保留内联

`loadError` 分支（line ~694）保持现状——持久错误状态需持续可见，不应被 3 秒 toast 顶掉。`DiagnosticNoticeCard` 组件与 `analysisDiagnostics` 类型不改动。

### D5：动效——最小淡入淡出

给容器加 `transition-opacity` + 一个极小的挂载淡入（如 `@keyframes` 在 `index.css`，或用 Tailwind `animate-*`）；MVP 阶段仅保证"出现 → 3 秒后移除"，不做滑入/堆叠动画。若不想新增全局 keyframe，可退化为无动画直接出现/消失。

### D6：可访问性

容器加 `role="status"` / `aria-live="polite"`；关闭按钮加 `aria-label="关闭提示"`。

## Risks / Trade-offs

- **[连续删除时旧定时器误关新 toast]** → 定时器放 `useEffect`，依赖 `kind/onClose`，清理函数 `clearTimeout`；新 toast 出现时旧定时器被清。
- **[受阻 toast 常驻占用右下角，用户未察觉]** → 琥珀色 + × 足够显眼；用户点击 × 或触发下一次删除即消失。
- **[一行文案容纳受阻原因可能过长]** → 只拼非零项 + `·` 分隔，最多 3 段，超长由容器 `max-w` 与 `truncate`/换行兜底。
- **[loadError 误改成 toast]** → 明确 Non-Goal；改造仅触及 3 处删除结果渲染，`loadError` 分支不动。

## Migration Plan

纯前端增量改造：
1. 新增 `DeleteToast.tsx` 组件。
2. `AnalysisTasksPage.tsx`：收敛状态、替换 3 处内联渲染、删除 `deleteNotice` 相关 JSX 与 `batchDeleteResult`/`fieldSessionBatchResult` 内联块。
3. `tsc -b` + `vite build` 验证；后端零改动。

回滚：仅前端，撤销组件与页面改动即可，无数据/契约影响。

## Open Questions

- 受阻文案是否需要点击后展开详细 4 格明细？（MVP 建议不需要，一行简述足够。）
