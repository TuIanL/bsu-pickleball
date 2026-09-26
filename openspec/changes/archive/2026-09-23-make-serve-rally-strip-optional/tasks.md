## 1. 前端展示层门控

- [x] 1.1 `src/config/featureFlags.ts` 新增 `serveRallyStripEnabled = envFlag(import.meta.env.VITE_SERVE_RALLY_STRIP_ENABLED, false)`，默认隐藏并与既有 `kitchenArrivalCardEnabled` 保持同构
- [x] 1.2 `src/components/platform/VideoAnalysisCard.tsx` 引入该开关，并在 `RealVideoOverlay` 内门控两处渲染：「发球候选：N 个候选」文案行与 `<ServeRallyStrip />` 导航条（「弹跳候选」文案行保持不变）
- [x] 1.3 确认未触碰发球候选检测与产物层：`resolveServeMarkers`、`getServeEvents`、`serve_events.json`、`_publish_joint_serve_candidates`（`backend/app/services/multiview_joint_executor.py:74` / 调用点 `:1161`）全部保持原样
- [x] 1.4 确认 `overlayRows` 中「发球候选」产物状态行保留，使产物存在性对操作者仍可解释

## 2. 验证

- [x] 2.1 `npx vitest run src/components/platform/VideoAnalysisCard.test.tsx src/components/platform/serveMarkers.test.ts src/pages/VisionPage.test.tsx` → 22 passed / 0 failed
- [x] 2.2 `npx tsc --noEmit -p tsconfig.app.json` → 0 error
- [x] 2.3 `npx eslint src/components/platform/VideoAnalysisCard.tsx src/config/featureFlags.ts` → 0 error（4 条既有 warning，与本次无关）
- [x] 2.4 手动确认：默认构建下播放器内不再出现「发球候选：N 个候选」文案，播放器下方不再出现发球候选导航条；弹跳候选文案正常

## 3. 规格同步与归档

- [x] 3.1 逐字比对 delta 中 `MODIFIED Requirements` 与 `REMOVED Requirements` 的 requirement 标题与 `openspec/specs/visual-analysis-workspace/spec.md` 一致（标题不匹配会导致归档原子中止）
- [x] 3.2 `openspec validate --all` 通过
- [x] 3.3 `openspec archive "make-serve-rally-strip-optional" -y` 完成归档与主规格合并（实测 `visual-analysis-workspace`: `~ 1 modified` / `- 1 removed`）
- [x] 3.4 归档后复查主规格：「真实视频发球开始 marker」为收窄版本（默认不展示、受 `VITE_SERVE_RALLY_STRIP_ENABLED` 控制），「发球候选导航条加载和降级状态」已移除（grep 计数 0）
- [x] 3.5 确认归档未产生新的 `TBD - created by` 占位符（仍为原有 5 处，本变更不新建 capability）
