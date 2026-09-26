## Why

发球候选导航条是 2026-06-03 引入的展示层：它把发球时刻候选铺成播放器下方的横向卡片，替代拥挤的进度条 marker。但当前产品口径已明确——无骨架姿态参与的发球候选只是 tracking-only 的降级信号，不构成确认发球，把它放在播放器下方作为主视觉引导会强化"系统已识别发球"的错误印象。2026-09-23 双摄链路新增发球候选发布后，该导航条在双摄任务里重新出现（44 个候选 + `partial` 降级标签），与本项目的诚实展示原则冲突。

因此本变更把该导航条从"必须展示"收窄为"可选、默认不展示"，同时保留发球候选的计算与产物，供后续评分校准与检测能力评估继续使用。

## What Changes

- 前端新增开关 `VITE_SERVE_RALLY_STRIP_ENABLED`（默认 `false`），统一控制发球候选导航条与播放器内发球候选计数文案是否渲染；置 `true` 可临时恢复，无需重算产物。
- **BREAKING**（仅前端可见行为）：已完成任务的真实视频工作台**默认不再展示**发球候选导航条，也不再显示"发球候选：N 个候选"计数文案。
- 收窄 `visual-analysis-workspace` 的「真实视频发球开始 marker」：由"工作台 SHALL 显示导航条"改为"MAY 提供、默认不展示，受前端开关控制"。
- 移除 `visual-analysis-workspace` 的「发球候选导航条加载和降级状态」：该要求整体只描述导航条的加载/降级，默认不展示后没有承载对象。
- 明确保留（本次不改动）：`serve_events.json` 产物与 `serve_events_url` / `serve_events_status` / `serve_events_detail` 字段、发球候选检测逻辑（含 joint 链路 `_publish_joint_serve_candidates`）、`发球事件加载和降级状态`（产物仍作为独立数据层加载）、`发球 marker 来源清晰`（文案口径）。
- 本变更不删除 `ServeRallyStrip` 组件、`resolveServeMarkers` 解析函数与其单元测试，避免以后需要时重建。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `visual-analysis-workspace`: 「真实视频发球开始 marker」由强制展示改为可选且默认关闭；移除「发球候选导航条加载和降级状态」这条只服务于导航条的要求。

## Impact

- 前端：`src/config/featureFlags.ts`（新增开关）、`src/components/platform/VideoAnalysisCard.tsx`（import 与两处渲染门控）。
- 后端、产物 schema、artifact API、数据库：**无改动**；`serve_events.json` 继续照常生成与发布。
- 测试：`serveMarkers.test.ts`（直接渲染 `ServeRallyStrip`）与 `VideoAnalysisCard.test.tsx` 不受影响，组件与解析函数保持导出。
- 后续若要长期下线检测能力，应另开变更处理后端与产物层，本变更只锁定展示层口径。
