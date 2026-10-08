# 可靠性 change 验收记录（2026-10-08）

## 验收范围

本轮针对仅本机演示：浏览器通过 loopback 同源代理访问 API；服务端凭据不进入前端包。四人身份算法的独立审核已移交 `restore-confirmed-four-player-joint-analysis/tasks.md` 的 6.5，本记录不宣称算法正确性通过。

## 页面与真实素材

- 比赛库主背景跟随主题；主题更新器保持纯函数，提交后同步 DOM、存储和事件。StrictMode 一次点击一次切换，直接设置、重新挂载、存储事件与同页事件均有回归。
- 缺失 poster 回退到视频首帧，视频 error 则显示占位图；新的 poster URL 仍可重新加载，卡片导航保留。
- 真实双摄 `ct_9997fa5aedf7` 对应的历史 session 缺少播放版，分片 MP4 的原生预览长期卡住。已为两路补生成独立 faststart 播放版，未重编码；编码、尺寸、时长和包数与原始媒体一致。原始合并文件与分析素材注册路径保留。
- 两路都是 H.264 / 1920×1080 / 587.166667 秒 / 35,230 个视频包；浏览器实际 videoWidth=1920、readyState=4，并显示标定帧与两组四角。
- 浏览器已核验比赛库与双摄标定页的暗色结果；2026-10-08 用户已确认最终视觉验收通过（task 11.7）。没有代替用户确认或提交球场标定。
- 媒体验收数据：`.runtime/reliability-media-reconnect-20261008.json`、`.runtime/reliability-playback-repair-20261008.json`。截图保存在 `.runtime/reliability-evidence-20261008/`。

## Worker 与存储

- 实际 JobStore、Worker、dispatcher 和 AnalysisPipeline 的租约丢失集成回归通过：终态 interrupted、failureClass=worker_lease；无错误 retry，同一 Worker 继续执行下一任务。
- 真实外接盘验收 job `job-587ff8edc3`：两轮都读取两路真实首帧，随后注入解码失败；最终 failed/input_media，完整 retry 事件落在实际 session 的 `analysis/<job_id>/run_trace.jsonl`，两路句柄均释放。此项是实际媒体读取和故障注入验收，不是完整 joint 算法运行。
- 挂载/卸载验收使用实际可丢弃磁盘镜像：挂载时正常写入，卸载后写入 `_degraded/<job_id>`，重挂并清空进程索引后仍读到原降级产物。持久 `.storage.json` 提供降级理由。SQLite DELETE / integrity_check=ok。
- 按 design 的 2026-10-06 决策，未主动卸载用户原始素材卷；本轮观察到 Elements 不可用及用户重新连接后的真实视频恢复，两路 Range 请求均 206。验收覆盖真实外接存储写入、实际卷卸载分支与恢复，不声称测试了运行中物理拔掉 Elements 的断电损坏。
- 证据：`.runtime/reliability-acceptance-20261006/evidence.json` 与 `real-media-run_trace.jsonl`；验收工具 `backend/scripts/verify_runtime_storage.py` 使用独立控制数据库，不修改生产任务索引。
- 临时目录清理保留 `.gitkeep`，回归覆盖正常结束、旧孤儿、最近写入和正在运行的任务。

## 本机鉴权与文档

- Vite dev/preview 均注入服务端 Bearer token，保持 Range/206；连接地址、Host、Origin 与 Fetch Metadata 守卫拒绝跨来源访问。
- 已配置 token 时，残留 AUTH_DISABLED 不覆盖凭据。代理没有 token 且没有显式 bypass 时返回 503。
- 文档默认关闭；本机启动脚本显式打开 PICKLEBALL_LOCAL_DOCS，仅允许 loopback peer 与本机 Host；伪造 forwarded header 无效。启动后 /health、/docs、/openapi.json 实测 200。
- 当前本机服务已独立于验证命令进程组启动，监听 loopback；重启前活动分析任务为 0。

## CI 的真实负例

- 草稿 PR：[TuIanL/bsu-pickleball #2](https://github.com/TuIanL/bsu-pickleball/pull/2)，已关闭、未合并；故障样例仅留在隔离分支，没有写入本地工作区。
- 最终 commit：`06eb0f0d8ba7cb54e812788af4bfb0e4e3860bb4`。
- 实际 PR 运行：[37788800305](https://github.com/TuIanL/bsu-pickleball/actions/runs/37788800305)。
- Ruff job 113350378148：F401 指向 `backend/app/_ci_gate_probe.py:2:8`，exit 1。
- 同一 job 的异常策略检查也实际执行：指向样例第 8 行的静默 broad exception，1 violation，exit 1。
- OpenSpec job 113350378249：明确拒绝缺少 SHALL/MUST 与 Scenario 的规格，exit 1。
- Ruff/异常策略与 OpenSpec 独立于完整质量任务。完整远端 quality 在原有依赖安装步骤失败；负例验收不代表完整远端 CI 已全绿，也不代表已配置 GitHub 合并保护规则。

## 自动回归结果

- 前端全量：97 文件、753 用例通过；日志 `.runtime/reliability-frontend-full-20261008.log`。
- 后端全量：1,728 通过、22 warnings；沿用 task 12.1 的两个既定 ignore，日志 `.runtime/reliability-backend-full-20261008-path.log`。首次运行缺 Homebrew PATH，3 个 ffprobe 用例失败；补齐 PATH 后全部通过，没有绕过失败用例。
- 生产构建与落地页 gzip 预算通过；日志 `.runtime/reliability-build-20261008.log`。
- Ruff、增量异常策略、本 change 的 OpenSpec strict 及 git diff --check 通过。
- 定向 ESLint 无 error，保留组件导出产生的 5 条既有 Fast Refresh warning。

## 提交拆分与归档

使用临时 Git index 在本地审阅分支 `codex/harden-analysis-runtime-reliability-20261008` 保存独立提交；主分支 HEAD 与原暂存区校验值保持不变。

1. `6b3deca5f189bf0f0da6b0de66dfd3c7a8123d05`：fix(library): recover theme switching and failed preview fallbacks（6 个文件）。
2. `724a4fe8ee8c71525329cd67b84ba0859c74cf04`：ci: enforce independent runtime reliability gates（4 个文件）。
3. `4959ee808fe1c01ca0e35d7d5a709656a17501b2`：fix(runtime): preserve control signals and reliable analysis artifacts（62 个文件）。
4. `ad201ba646b7310228ab170ef68ba0c62ed4f887`：fix(frontend): harden capture lifecycle and authenticated local access（88 个文件）。

拆分边界：

- Worker、StorageService、analysis_pipeline、routes_analysis、分析 schemas 与错误轨迹模块进入可靠性提交，并携带前置 trace change 的依赖。
- 共享 executor、visual artifacts、result composer、association 和 overlay builder 仅取产物根接线或 F401/F841 清理；global_state 仅去掉三个既有死变量，保留原身份算法。
- 共享后端测试仅取临时 take 目录初始化 hunk；身份审核、切分复用/clip 的新用例留在另一 change。
- 前端 AnalysisJobPage、analysisClient 保留错误轨迹、同源鉴权、轮询和类型校验；VideoAnalysisCard 与 VisionPage 只取主题色修改。
- types/report 只取 trace 类型和旧报告类型适配；冻结名册 hash、匿名观测、身份槽位，及 StructuredHeatmap 的身份渲染均留在四人身份 change。
- 身份裁决、回合切分复用/clip 行为与相关算法测试未进入本次分支。完整 hunk/排除文件记录见 `commit-boundaries-20261008.json`（运行时镜像 `.runtime/reliability-split-commits-20261008.json`）。

隔离分支回归：后端 1,685 passed、22 warnings；前端 97 文件 / 751 passed；生产构建通过，落地页静态 JS gzip 140,685 字节。Ruff 通过；针对分支实际 diff 的 45 个 Python 文件，增量异常策略零违规；测试快照源码与分支 blob 逐一一致。日志 `.runtime/reliability-split-backend-full-20261008.log`、`reliability-split-frontend-full-20261008.log`、`reliability-split-build-20261008.log`。首次隔离后端运行遗漏测试目录初始化和本地真实输入，已补齐后原样重跑全量，没有增加 ignore。

人工视觉验收已于 2026-10-08 通过；最终本机健康检查 200，两路 faststart 原生媒体 Range 请求 206，证据 `.runtime/reliability-final-live-check-20261008.json`。

归档日期 2026-10-08；规格同步 32 条新增、13 条修改，无删除/重命名。三个新主规格 `api-access-control`、`resource-lifecycle-integrity`、`runtime-silent-failure-guardrails` 补写真实 Purpose。全部 94 项任务完成；四人身份链独立审核保留在另一个 change 的 6.5。

归档后全仓检查发现 11 份既有主规格 Purpose 少于 strict 要求的 50 字符；已在原说明后补充各自范围和产物用途，未更改 requirement 或 scenario。前置 trace change 的遗留 6.1 按实际完成的外接盘故障注入证据补记完成。规格与归档记录随独立文档提交保留。

最终全仓 OpenSpec strict：206 项通过、0 失败；主规格 TBD 扫描零命中，`git diff --check` 通过。
