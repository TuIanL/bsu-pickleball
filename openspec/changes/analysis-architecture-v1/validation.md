# 实施验收记录

日期：2026-10-17。实施分支 `codex/analysis-architecture-v1`，起点为备份提交 `0793a71`（应用代码基线 `2665bc3`）。本文件替代提案阶段的“全部待实施”记录；提案产物 done 与实现完成仍是两个不同概念。

## 自动验证

| 检查 | 实际结果 | 本地原始日志 |
| --- | --- | --- |
| 修改前 legacy 窗口/Worker/trace/双摄基线 | 69 passed，218.60s，无用例失败 | implementation-log.md 中记录命令 |
| 全量后端 | 1805 passed、1 skipped、22 warnings，523.33s | `.runtime/analysis-architecture-backend-tests.log` |
| 后补模块合同测试 | 30 passed，2.08s | `backend/tests/test_modular_analysis_runtime.py` |
| 最终模块/API/删除/热路径/双摄/trace 回归 | 120 passed、2 warnings，3.96s | `.runtime/analysis-architecture-final-backend-tests.log` |
| 前端相关四文件 | 51 passed，10.72s | `.runtime/analysis-architecture-frontend-tests.log` |
| 全量前端 | 98 files、755 passed，55.98s | `.runtime/analysis-architecture-frontend-full.log` |
| 生产构建（tsc、Vite、landing budget） | 退出 0 | `.runtime/analysis-architecture-build.log` |
| 本期六个 TS 文件 ESLint | 0 errors、2 warnings | `.runtime/analysis-architecture-eslint.log` |
| 全仓 ESLint | 3 errors、43 warnings，未通过；3 个错误均在备份 HEAD 可复现 | `.runtime/analysis-architecture-lint-final.log`、`analysis-architecture-lint-baseline-{roster,modal}.log` |

全量后端完成后追加了纯合同/参数/queued cancel 校验和 API new-version 保真，最终 120 项覆盖这些修改；没有把不同批次相加伪称一次全量结果。全量前端前后只移动原有 lint 注释和排除生成目录，运行逻辑不变。

全仓 lint 最初误扫 `.runtime` 内 MPEG-TS 测试片段，已增加 `**/.runtime/**` 忽略，不修改规则。余下错误为未修改的 `AnalysisRosterConfirmation.tsx` 两个 set-state-in-effect，以及 `Modal.tsx` 一个 refs-during-render；以 `git show HEAD:<file> | eslint --stdin --stdin-filename <file>` 复现。任务页原有 suppression 放错行已移至对应 setState，未新增规则关闭。

测试警告包括已有 Starlette/Pydantic/Alembic 弃用或 diagnostics 序列化提示，前端 jsdom 缺少 canvas 实现和 Fast Refresh/Hook 提示。本期没有通过降级规则或替换真实结果使验证通过。

执行命令（Python 在 backend 目录，前端在仓库根）：

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_modular_analysis_runtime.py -q
.venv/bin/python -m pytest tests/test_modular_analysis_runtime.py tests/test_analysis_delete_disk_cleanup.py tests/test_job_hot_path.py tests/test_multiview_orchestration.py tests/test_analysis_run_trace.py tests/test_analysis_run_trace_api.py -q
npm test -- --pool=threads --maxWorkers=1
npm run build
npm run lint
npx eslint src/pages/AnalysisJobPage.tsx src/pages/AnalysisTasksPage.tsx src/pages/ModularAnalysisRunView.tsx src/pages/ModularAnalysisRunView.test.tsx src/services/analysisClient.ts src/types/report.ts
```

## 分层证据与 14 份规格覆盖

| 证据类别 | 已验证内容 | 边界 |
| --- | --- | --- |
| 合同 fixture | 最小/替代/可选 DAG、环/类型拒绝、窗口预算/跨界选择、采样相位、消费上下文、未来类型、ObjectRef/Association、语义版本 | 注入 runner 和 fixture 仅在测试注册，不是生产动作/战术模型 |
| 存储/Worker/API/UI 集成 | 冻结 hash、CLI/API 一致、只读 preview、cache repair/CAS、orphan/迟到 lease、失败/取消/恢复、单调进度、间接血缘/source pin、离线盘、路由脱敏、legacy 兼容 | 原有队列与资源限制复用，没有第二套调度器；不改变四人身份算法 |
| 真实推理 | 已有录制来源、YOLO 人/球及 RTMPose26、单/双摄 60–90s、窄重算、全缓存计数 | 使用实际安装模型，不以 fixture/缺模型/占位成功替代 |
| 质量 | payload 可读、schema/单位/主体作用域、时间/机位映射、quality 与 status 分离；像素值/visibility 行为回归 | **未进行人工标签的 precision/recall、挥拍/击球/战术准确率评估**；sufficient 不是精度结论 |

`RESEARCH_AND_AUDIT.md` 保留 14 份 delta spec 与任务组映射。新增 runtime、lineage、local validation、association、window、context、publication 由模块合同及故障测试覆盖；修改 executor/orchestration/trace/pipeline/pose/artifacts/task-management 同时由模块集成和全量 legacy 回归覆盖。未把结构校验当模型验收。

## 真实短窗口结果

完整机器证据：[evidence/real-window-validation.json](evidence/real-window-validation.json)，包括媒体/PTS/权重/配置摘要、plan_hash、artifact_id、内容摘要、输入血缘、同步合同、计数和耗时。来源为既有录制 take `take_sync_20260720_121319_e7f03b` 的 174/175 两路，1920×1080、60fps；请求 `[60000,90000)`，stride 30、phase 0。准备 28.943s，输出隔离在 `.runtime/analysis-architecture-v1-validation/acceptance/`，未改原媒体/生产 Job。

| 场景 | wall 秒 | 节点结果 | capture / 模型构造 / 推理 |
| --- | --- | --- | --- |
| 单摄人+球+姿态 | 204.916 | 三节点 completed，complete | 每节点 1 / 1 / 60 |
| 同窗口新 Job | 10.313 | 三节点 cached，complete | 全部 0 / 0 / 0 |
| 仅 pose confidence 改为 0.45 | 27.601 | 人/球 cached，pose completed | pose 1 / 1 / 60；其余全 0 |
| 双摄仅 raw ball | 27.001 | 仅一个 ball 节点 completed，complete | 2 / 1 / 120 |
| 双摄同窗口新 Job | 20.077 | ball cached，complete | 0 / 0 / 0 |

单摄每节点应用层 read/grab 1771 帧，采样 60 帧，范围 3600–5370；双摄合计 3542 帧、采样 120 帧，范围 cam_1 3600–5370、cam_2 3598–5368。双摄时间权威 source_pts，现有同步快照为三个人工锚点、good，有效域覆盖本次窗口。参考机位/PTS/no_new_frame 与显式 secondary 降级另有控制测试。

所有真实场景都将 legacy pipeline_factory/on_completed 设为禁止调用，未进入整场切分、joint tracking、标定、指标或报告。全缓存仍重新核验约 1GB/路源文件强摘要，因此不等于零媒体 I/O 或毫秒返回。三能力首次冷启动包含 ML 依赖初始化；该样本无旧全链路对照，不报告端到端加速倍数。

OpenCV 内部 GOP 预读不可见，记录为 `internal_not_exposed`；以上 decoded/read 范围仅是应用层证据。节点之间允许有界重新解码，不宣称单遍解码。验收准备发生在 runtime_versions 元数据增强前，证据中的运行环境版本明确标为运行后记录，未篡改原冻结计划。

复现命令（在 backend）：

```sh
.venv/bin/python scripts/validate_modular_analysis.py \
  --source '/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_121319_e7f03b/174_merged.mp4' \
  --secondary-source '/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_121319_e7f03b/175_merged.mp4' \
  --sync '/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_121319_e7f03b/timeline/sync_calibration.json' \
  --reference-camera 174 --secondary-camera 175 \
  --start-ms 60000 --duration-ms 30000 --stride 30 \
  --output-root ../.runtime/analysis-architecture-v1-validation/acceptance
```

## OpenSpec 与交付边界

严格校验本 change 1/1、全仓 207/207 通过（205 specs、2 changes），0 failed。80/80 实施任务完成；proposal/design/specs/tasks 产物齐备。`git diff --check` 与新增文件显式换行/尾随空白扫描通过，文档链接与复现输入存在，备份/main 提交不变。

```sh
OPENSPEC_TELEMETRY=0 openspec validate analysis-architecture-v1 --strict --json --no-interactive
OPENSPEC_TELEMETRY=0 openspec validate --all --strict --json --no-interactive
OPENSPEC_TELEMETRY=0 openspec instructions apply --change analysis-architecture-v1 --json
OPENSPEC_TELEMETRY=0 openspec status --change analysis-architecture-v1 --json
git diff --check
```

规格保持 7 ADDED + 7 MODIFIED，主规格待 archive 再合并。实现范围是三能力和全域扩展骨架；21 个未来能力仍 planned，不能以本期完成宣称球拍/挥拍/动作/丁克/战术算法可用。

默认产品 engine 保持 legacy，模块提交可通过 `PICKLEBALL_MODULAR_ANALYSIS_ENABLED=false` 关闭而保留 reader/历史证据。备份/main 不动；本期没有自动 commit、push 或 archive。开发入口和后续能力实现步骤见 [开发指南](../../../docs/analysis-architecture-v1.md)。
