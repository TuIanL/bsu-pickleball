# 验收记录

日期：2026-10-20。变更：`frontend-analysis-mode-creation`。

## 交付行为

上传/已有视频、录制 A/B 单机位及双摄 take 共用五种模式：完整比赛分析（默认）、球员检测、球检测、姿态分析、自定义组合。专项使用显式准备 → 服务端计划预览 → 创建任务流程，姿态依赖由后端计划解析。专项不要求场地/球网标定或名册，实际目标、依赖、片段与缓存提示可在创建前确认。

专项任务保留视频、录制、take 和机位关联；刷新后可在原素材历史中打开。完整报告的主版本选择排除 modular_v1，专项深链经素材归属校验后进入模块结果页。结果分别展示目标完成情况、产物质量和存储可用性，重产物按用户操作读取。

## API 与兼容合同

- `GET /api/analysis/runtime-status` 返回 `modular_submission_enabled`；现有 capabilities 数组格式保持兼容。
- `POST /api/analysis/takes/{take_id}/sources/prepare` 从登记视频、真实 camera/view 映射及手动确认同步准备双路公共快照，返回 `source_ids`、`sources`、`reference_view_id`、`sync`、`source_binding`、`recording_session_id`。公共快照不含内部媒体/时间文件路径。
- `AnalysisRequest.source_binding` 可选，含 `take_id`、`sync_revision`、`provenance_fingerprint`。Web 双摄使用此绑定，旧 CLI 无绑定请求继续可用。预览和提交只读验证当前确认及来源，不进行旧同步文件的懒迁移。
- `POST /api/analysis/jobs` 支持可选 `expectedPlanHash`；与实际语义计划不一致时返回 HTTP 409 / `plan_preview_stale`，不创建 Job。旧调用不传此字段仍可用。
- 专项 Job 保留 `analysisEngine`、`analysisTargets` 及经过验证的录制归属。伪造 take、录制或机位关联会拒绝。
- `PICKLEBALL_MODULAR_ANALYSIS_ENABLED=false` 关闭新模块提交，已有清单仍可读取。完整分析仍使用现有 legacy_v1 引擎及 new/legacy 流程选项。

## 自动化验证

### 后端

命令：

```sh
backend/.venv/bin/python -m pytest backend/tests/test_modular_analysis_runtime.py backend/tests/test_sync_anchor_service.py -q
```

结果：**46 passed**；2 条现有依赖弃用警告。

覆盖预览无 Job 写入、依赖和计划 hash、预览 hash 冲突 HTTP 409、普通提交去重、CLI/legacy 兼容、模块禁用、无懒迁移的只读同步校验、真实 camera/view 绑定、双路准备的 PTS 要求与公共路径脱敏、同步/来源失效、伪造素材归属等。Fixture 测试不作为真实模型执行证据。

### 前端

第一组：9 文件 **95 passed**。

```sh
npm run test -- src/pages/AnalysisModeCreation.test.tsx src/pages/NewAnalysisPage.test.tsx src/pages/MultiViewAnalysisSetupPage.test.tsx src/pages/ModularAnalysisRunView.test.tsx src/services/analysisModeConfig.test.ts src/hooks/useModularAnalysisCreation.test.tsx src/services/libraryAdapter.test.ts src/services/libraryAnalysisVersion.test.ts src/components/library/LibraryItemWorkspace.test.tsx
```

第二组：6 文件 **89 passed**。

```sh
npm run test -- src/services/analysisClient.test.ts src/services/libraryAnalysisRouting.test.ts src/pages/AnalysisJobPage.test.tsx src/app/navigationContext.test.ts src/components/library/viewCapabilities.test.ts src/components/library/LibraryCard.test.tsx
```

合计 **184 passed**。新增覆盖三个入口的专项创建、上传复用、缺少另一路时的 B 机位分析、双摄服务端准备及嵌套 return、姿态自动依赖、无关模型缺失、必需模型缺失、窗口边界、过期异步响应丢弃、配置变更撤销预览、新版本提交结果未知后的历史核对、完整 A + 专项 B + 活跃 C、只有专项、模块深链和产物按需读取/重试。

### 构建、lint 与边界

- `npm run build`：通过，含 TypeScript、Vite 和 landing 体积预算检查。验收最终构建日志保存在 `.runtime/frontend-analysis-mode-creation/build.log`。
- landing 静态 JS gzip 预算检查通过；分析页仍以现有路由懒加载，未把专项表单引入 landing 页面。
- 对本轮所有修改及新增的前端文件单独执行 ESLint：**退出码 0**。
- `npm run lint`：全仓 **3 errors / 43 warnings**。3 个错误均在未修改文件：`AnalysisRosterConfirmation.tsx:201,234` 的 effect 内同步 setState，`Modal.tsx:17` 的 render 内 ref 访问。用 `git show HEAD:<file> | npx eslint --stdin --stdin-filename <file>` 对基线复核，分别得到相同 2 个与 1 个错误。
- 构建仍提示既有通用 client 的静态/动态混用和大 chunk；本轮未扩大该结构改造范围。
- `git diff --check`：通过。

## 浏览器验证

使用本机独立测试数据库、输出目录和片段，前端 `127.0.0.1:5177` 代理到后端 `127.0.0.1:8017`。开发鉴权旁路仅用于该本机验收实例。没有向正式任务队列提交测试 Job。

1. 窄屏（IAB 470px）从已有上传素材进入，完整分析为默认；切换“球员检测”后不再要求完整表单和标定。
2. 准备真实 4 秒片段，窗口显示 0–4 秒；设置 stride=30 后预览，只有球员检测目标。创建按钮在准备/预览期间禁用。
3. 创建进入 `job-b29ef8ca80f7`，URL 保留 `/library/upload/video-mode-smoke?view=overview` return；实际推理完成后显示全部目标完成、证据充分、产物可读取。
4. 点击“返回比赛详情”回到原素材，刷新后的专项历史可见；点击“查看专项结果”再次进入该 Job。完整报告/球路入口继续按对应证据门控。
5. 桌面 Chrome（约 1196px）进入姿态模式，用 Enter 键执行准备和预览；计划同时列出“球员检测 · 自动加入的依赖”和“姿态分析 · 所选目标”。模式卡片、配置和按钮正常排列。
6. 双摄进入球检测模式，填写 60–62 秒 / stride 30，打开同步工作台后返回：模式、目标、窗口、采样和原素材 return 均恢复；创建按钮要求重新准备/预览。测试副本因 take 身份变化而正确显示旧确认失效。
7. 在隔离测试副本中使用同一真实视频既有的人工锚点重新确认同步，继续执行双路来源准备、计划预览和模块提交；不修改外接盘原始锚点或媒体。

截图保存在本地验收目录：`create-desktop.png`、`result-narrow.png`；最终双摄截图及 Job 见下方补充记录。

## 真实模型执行

真实来源：外接盘 `take_sync_20260720_121319_e7f03b` 的 `174_merged.mp4`、`175_merged.mp4` 与已有 source PTS；窗口 **60000–62000ms**，stride **30**。另有上传素材 `video-48f67f0047.mp4` 的 4 秒本地裁剪用于浏览器单摄流程。

运行现有真实验收脚本，输出到隔离目录。显式设置模型根目录、人体模型绝对路径及 CPU 线程数：

```sh
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PICKLEBALL_MODEL_DIR="$PWD/models" \
PICKLEBALL_DEFAULT_DETECTOR_MODEL="$PWD/backend/yolo11n.pt" \
backend/.venv/bin/python backend/scripts/validate_modular_analysis.py \
  --source '<真实录制目录>/174_merged.mp4' \
  --secondary-source '<真实录制目录>/175_merged.mp4' \
  --sync '<真实录制目录>/timeline/sync_calibration.json' \
  --start-ms 60000 --duration-ms 2000 --stride 30 \
  --output-root .runtime/frontend-analysis-mode-creation/real-dual-prepared
```

结果：**passed**，不是 Fixture。冻结模型资源 hash、来源 hash、完整 plan_hash、节点计数及质量/可用性摘要保存在本变更的 [smoke-evidence.json](smoke-evidence.json)。原始清单在本地 `.runtime/frontend-analysis-mode-creation/real-dual-prepared/evidence.json`。

| 场景 | Job | 观察 |
| --- | --- | --- |
| 单摄球 + 姿态（自动依赖球员） | `job-b8c5d5f3f17c` | 三个节点完成，每节点实际模型执行 4 次 |
| 相同单摄计划新版本 | `job-83c73a5c854f` | 三个节点全部 cached，模型执行和 capture opens 均为 0 |
| 只改姿态参数 | `job-66023ce859d7` | 球、球员复用；姿态执行 4 次 |
| 双摄二维球观测 | `job-ad0f16aed176` | 只有球检测节点，模型执行 8 次，包含两路 available 观测 |
| 相同双摄计划新版本 | `job-9e26dd88cfd7` | 球检测 cached，模型执行和 capture opens 均为 0 |

上述 5 个任务均 succeeded / complete；产物均 sufficient / available。缓存场景与首次执行的 plan_hash 相同，姿态参数变化时 plan_hash 改变。首次尝试因在仓库根运行时模型相对路径不匹配而未开始推理，已在 `real-dual/evidence.json` 记录失败；使用明确模型路径重新运行后通过。

本次验收验证创建、合同和短片执行可用性；不据此评价整场准确率、球员持续身份或三维轨迹精度。

### 浏览器双摄最终结果

- Web 创建 Job：`job-3ab864d7a694`，succeeded / complete。
- `recordingSessionId=sync-mode-dual`、`analysisKind=multiview`、`videoId=rec-db6e9e990a`、`analysisTargets=[ball.detect]`；源相机为真实 `174 / 175`，参考视图由服务端同步配置确定。
- 最终清单与浏览器单摄清单摘要已附入 `smoke-evidence.json` 的 `browser_cases`，包含完整 plan_hash 和真实执行计数。
- 返回 `/library/sync_recording/sync-mode-dual` 后专项历史显示“球检测 · 双摄 · 已完成”，窗口 60–62 秒；完整报告入口按完整结果证据门控。
- 结果截图：`.runtime/frontend-analysis-mode-creation/result-dual-desktop.png`。

## 最终状态

OpenSpec 严格校验通过；任务 32/32 完成。6 份主规格已同步（新增 15 条、修改 6 条）；变更于 2026-10-20 归档至 `openspec/changes/archive/2026-10-20-frontend-analysis-mode-creation/`。
