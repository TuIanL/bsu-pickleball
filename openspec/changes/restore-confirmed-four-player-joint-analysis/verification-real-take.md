# 真实素材验收记录

## 2026-10-27 开场同步补核（未创建新分析 Job）

第一项已完成：新增 174 第 6 帧 / 175 第 4 帧（0.100000/0.066667s）开场锚点，保留原三锚点并经正常同步服务发布 revision 1。动作证据来自 0–5 秒与独立 43–48 秒核对；不稳定的 18–23 秒测量未采用。有效起点从 53.85 秒提前至 0.1 秒，RMS 6.9261ms，状态 confirmed、analysis_allowed=true。发布后正常输入预检通过；3615 tick 中第二机位正式可用由 1999 增至 3612，无重复源帧，区间外策略及尾部有效边界未放宽。相关回归 78 passed。

原文件已备份并核对哈希，视频、名册及旧 Job 输出未改。完整证据、实际源帧对与限制见 [开场同步核查](../../../docs/四人身份开场同步核查_2026-10-27.md)。8.11 完成；8.12 仍需创建新 120 秒任务，不能据同步预检改判下文 `job-603e082be8` 的 fail。

## 2026-10-26 四人确认与恢复逻辑实测

当前已完成任务 `job-603e082be8` / `mvr_98973dfb773e`，代码 `3118f65`，同一 `0–120000ms` 范围、原标定、原阈值和冻结名册。流水线 succeeded，四人全部确认，八项身份硬约束通过；正式覆盖率 77.68%/57.95%/96.87%/94.55%，最长缺口 10.13/11.07/3.00/3.63 秒，整体质量仍 **fail**。90–120 秒覆盖由中间任务全员 0% 恢复至 99.78%/93.89%/99.44%/89.11%。已抽查 65/110 秒双机位的服装与 P 标签，不能据此宣称完整视频验收通过。

后续定位到开场 cam_2 处于同步区间外、按策略仅回放，以及 90 秒的隔离记录污染正式统计两个断点。后者已由 `bf2ea6e` 修复，最终相关回归 **179 passed**，尚待新真实 Job 验证。完整签名、各任务状态及剩余工作见 [最新修复进展](../../../docs/四人身份修复进展_2026-10-26.md)。8.9/8.10 完成，8.11 及原全片验收任务继续开放。本次未重跑 OpenSpec CLI 校验；下文既有校验记录属于此前轮次。

## 2026-10-26 外接硬盘数据恢复与本机 120 秒复测

已从 `F:\TG的MacBook Air\backend\data\` 找回目标 take 的主库、Job 控制库、原标定、旧 Job 配置和视频注册记录。原件未改动；D 盘仓库忽略目录中保存独立核查副本。原 3 点同步锚点已在 D 盘两路视频上重新确认，120 秒双摄预检通过。详情见 [本机七月素材核查](../../../docs/四人身份七月素材核查_2026-10-26.md)。

新 Job `job-2771b1b418` / joint run `mvr_5b0ec65d6a4f` 完成 `0–120000ms` 实片，冻结名册 hash 与旧短片 Job `job-faf852782a` 相同，旧新产物并存。新任务的四人身份质量 verdict 仍为 `fail`：P1/P4 确认，P2/P3 未确认，覆盖率 8.19%/0%/0%/78.37%，四人最长缺口都超过 2 秒，跨侧门槛失败。旧新签名不同，不作为同签名控制实验。55.5–62.5 秒锚点附近的首断点和逐层证据见 [120 秒复测报告](../../../docs/四人身份七月120秒复测_2026-10-26.md)。7.6 的重跑与失败留证已完成；1.2/1.3/6.2/6.3/6.5 的完整验收仍未完成。

以下 Windows 恢复进度记录为本次找回数据库之前的阶段状态。

## 2026-10-26 Windows 本机恢复进度

目标 take `ct_9997fa5aedf7` 的两路原始 merged MP4 与录制清单已由用户放到 `D:\匹克球\2026-07-20\take_sync_20260720_121319_e7f03b`。两路各 35,230 帧，已在本机重建 source PTS sidecar；场线模型给出两机位全场标定草稿，抽样球员跨机位投影与 `identity`/`rotate_180` 方向一致。完整文件清点、哈希、预览和数值见 [本机七月素材核查](../../../docs/四人身份七月素材核查_2026-10-26.md)。

首次复制时 `analysis/` 为空；用户随后补齐旧 Job 产物、原 PTS sidecar 和 3 点手工同步锚点。旧 120 秒逐层 trace 与质量失败结果现可本机复核。原项目 `app.sqlite3`、Job 控制库和两机位标定文件尚未到位，Windows 本机数据库没有该 CaptureTake 或冻结名册；同步确认文件还保留 macOS 绝对路径。本机尚未创建同配置新 Job，1.2/1.3/6.2/6.3/6.5/7.6 的修复后真实验收不因此变为完成。

## 旧 Job 基线

- Job：`job-9a640b069a`，状态 `completed`，执行模式 `joint_tracking_v2`。
- Take：`ct_9997fa5aedf7`；参考视角 `cam_1`=`identity`，第二视角 `cam_2`=`rotate_180`；canonical frame `ccf_f09b721fc74c`。
- 输入签名：`fae3e10bad02e70abcd30bab5b86df58de57d95c53bcf9472b1b83da46396fe4`。
- 配置签名：`7202a48846e0003204521dd9f4c4f1ad5640eb50ced93d444d02341a46bb2a79`。
- 冻结名册 hash：`edfb8e4aa6af22678638e82e2aea290719af32bbdc085f98aeb88e20096e20e4`；来源 `manual`，Team A 初始端 `end_a`。P1/P2 属 A，锚点约 289.083s；P3/P4 属 B，锚点约 289.083s/292.083s。
- 产物目录：`$TAKE/analysis/job-9a640b069a`；联合跟踪目录 `$TAKE/analysis/multiview/mvr_c3a620a12ace`，其中 `$TAKE=/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_121319_e7f03b`。

### 身份与覆盖

| 槽位/内部轨迹 | metric-eligible 样本 | canonical 端 | 当前正式身份质量覆盖 | 最长缺口 |
|---|---:|---|---:|---:|
| P1 / global_player_1 | 0（1 个歧义样本） | 无 | 0% | 444.23s |
| P2 / global_player_2 | 4,327 | end_b：4,327 | 0% | 444.23s |
| P3 / global_player_3 | 12,332 | end_b：12,332 | 0% | 444.23s |
| P4 / global_player_4 | 60 | end_b：60 | 0% | 444.23s |

- Global Roster 占用 4 槽、确认 0 人、状态 `bootstrap`；P1/P2/P4 为 `slot_fallback`，P3 为 `direct_reference_binding`，但四者 `mapping_confirmed=false`。
- 四人质量产物记载 13,139 attempted ticks、444.23s；所有正式 `canonical_coverage` 都是 0%，最长缺口都是 444.23s，failure reasons 包括名册确认与四个个人 coverage/gap 门槛。
- fused trajectory 共 17,445 个样本：global_player_2/3 提供了主要轨迹，且所有 eligible 点均落在 end_b；global_player_1/4 几乎没有有效轨迹。
- overlay 有 17,615 帧：8,796 帧 1 个框、4,460 帧 0 个框、4,356 帧 2 个框、仅 3 帧 3 个框。首帧却出现 `Player_4`/`P4`，证据类型为 `bootstrap_backfill`，说明用户标签并未受当前冻结名册审计确认约束。
- recovery funnel：`unmatched_recovery_evidence_seen=77086`、`unmatched_recovery_rejected_geometry=70405`、`unmatched_recovery_accepted=133`、`unresolved_no_slot=58996`（见 `fused_diagnostics.json`）。

## 新 Job 验收运行

- 首次验收 Job：`job-dbb01b55d8`；joint run：`mvr_90595af15ead`；提交时间 `2026-09-27T13:06:25Z`。运行时守护会话到期后 worker 在 10,321 / 17,615 tick 处终止；重启记录为 `interrupted / worker_heartbeat_timeout`。这次没有完整产物，不作为验收结果；原 Job 与文件未覆盖。
- 输入签名：`70565d8a0617d37759d63e642fcd3b36fefb3c5b84d87346fb0cbf24830dfcb1`；配置签名：`002fc2b316c2b4c58a5db9a4f64ec91c4b2cadc8756f36b10a90e0c574408bbb`。
- 冻结名册 hash 与旧 Job 完全相同：`edfb8e4aa6af22678638e82e2aea290719af32bbdc085f98aeb88e20096e20e4`。P1/P2 Team A / end_a，P3/P4 Team B / end_b；A 机位 `identity`、B 机位 `rotate_180`。
- 处理完整 take（587.15s），双摄 `joint_tracking_v2`，`frameStride=2`、`sourceFps=60`、模型检测开启、姿态推理关闭、`useRallyContext=true`。为让身份和位置质量验收不被单独耗时的回合分割前置任务阻塞，本次 `segmentationRequired=false`；没有缩短视频时间窗或放宽四人门槛。`debugTraceEnabled=false`，常规固定窗口漏斗仍由 joint diagnostics 产出。
- 首次任务只写入 `$TAKE/analysis/job-dbb01b55d8` 和 `$TAKE/analysis/multiview/mvr_90595af15ead`；旧 Job 目录未刷新。
- 重跑 Job：`job-aecc1c6e10`，于 `2026-09-27T14:35:33Z` 创建；joint run `mvr_1cffc657f19e`。沿用相同输入签名 `70565d8a0617d37759d63e642fcd3b36fefb3c5b84d87346fb0cbf24830dfcb1`、配置签名 `002fc2b316c2b4c58a5db9a4f64ec91c4b2cadc8756f36b10e0c574408bbb`、冻结名册 hash、frame stride 和完整时间范围；未放宽门槛。
- 按用户指示于 `2026-09-27T14:47:27Z` 主动取消。取消请求返回前的进度为 1,992 / 17,615 tick；任务终态为 `canceled`，不构成通过或失败的全片质量结论，也未覆盖旧 Job。
- 用户明确表示暂不运行全量任务，后续未再创建替代的全片 Job。因此 1.2 / 1.3 的真实漏斗证据、3.2 的真实素材首断点修复、6.2 / 6.3 的全片视觉与质量验收仍待后续授权。代码回归结论独立有效。

### 用户执行的 120 秒诊断 Job

- Job：`job-faf852782a`；joint run：`mvr_b6e5d8762956`；素材时间范围为 `0–120.467s`，共 3,615 tick（reference frames `[0, 7230)`，metric frames `[0, 7200)`）。这是用户发起的短片分析，不是全片 Job。原始产物位于 `$TAKE/analysis/job-faf852782a` 与 `$TAKE/analysis/multiview/mvr_b6e5d8762956`；没有启动新的分析任务。
- 漏斗计数：`cam_1` 有 29,452 个原始检测框、29,452 个 ROI 后框、9,865 个局部正式检测和 17,364 个局部候选；`cam_2` 有 12,353、12,353、7,003、4,691。两机位总计 41,805 个原始框，ROI 未进一步过滤；这段素材的主要问题出现在局部身份/全局关联和锚点绑定阶段，现有证据不支持通过降低检测阈值来处理。
- 逐人质量：P1 与 P3 的正式检测计数为 0；P2 coverage `0.598`、最长缺口 `14.23s`；P4 coverage `0.825`、最长缺口 `15.83s`。整体 verdict 为 `fail`，四槽映射和覆盖门槛均未通过。
- Debug trace 中，`55.500s` 的候选 track `293` 与 P1 冻结框完全重合（IoU 为 1），但当时它没有球场位置，因而未成为 joint observation；`56.367s` 同一 track `293` 转为正式检测并被标成 `Player_3`。同一时间，另一条正式 track `260` 与 P4 冻结框完全重合，也被标成 `Player_3`。因此只用 `(view, Player_N, epoch)` 追踪锚点会把不同原始轨迹合并；同一个局部 P 标签在不同 raw track 间复用，能解释 P1/P3 缺失和 P4 端位冲突。
- 120 秒运行的旧 `perception_stage_trace` 仍使用固定的 2:30、4:49、7:22 和 9:40 窗口，这些窗口在 120 秒素材上均是 0 tick。实现已改为按本次素材时段生成开场、中段、末段窗口，并围绕冻结锚点生成窗口；旧 trace 的空窗口不代表检测为零。
- 产物之间也有身份结论冲突：`fused_diagnostics.json` 的冻结锚点审计为 P2 已确认、P4 端位冲突；`roster.json` 却把 P2/P4 都标成已确认；独立 `bootstrap_binding_audit.json` 又将四槽都标成无正式观测。Rally/Shot 组合会再次写入同一路径，覆盖 joint run 的来源轨迹证据。现已改为保留先发布的 joint-run 审计，Rally/Shot 只在审计文件缺失时补写。
- 基于这些证据实施的修复包括：将缺少本地 P 身份的正式场内检测交给全局关联；软接管身份保留为 tentative，不带入 P 标签；用原始跟踪 ID 贯穿候选/正式切换和锚点关联；给锚点增加只按同机位时间与 bbox 匹配的证据通道，该通道不会输入全局位置更新；未确认审计保留 raw track、局部失败原因和尝试过的 global ID。以上只由目标回归测试验证，尚无修复后的真实素材结果。
- 用户要求继续不跑全量视频。故 1.2 的后半段窗口、1.3 的全时段双机位/换端检查以及 6.2 / 6.3 全片验收仍未完成；本短片结果继续保留为失败诊断，不作为算法验收通过。

## 实施回归

- 上一轮完整后端套件：`python -m pytest backend/tests -q`，`1666 passed, 1 skipped`（142.27s；本次续作改动之前）。
- 本次相关后端回归：`tests/test_analysis_roster_runtime.py`、`tests/test_p1_online_recovery.py`、`tests/test_global_roster.py`、`tests/test_canonical_shot_rally_events.py`、`tests/test_joint_visual_artifacts.py`：`92 passed`；`tests/test_view_tracking_session.py`：`13 passed`。
- 本次再次尝试完整后端套件时，在 1510 个通过、1 个跳过后中断。最后的媒体夹具调用 ffmpeg 从两个约 1.2 GB 的视频文件抽封面，长时间没有推进；这不是分析任务。中断后 ffmpeg 子进程已退出，检查确认没有写出或覆盖 poster 文件。该次运行不作为完整后端回归通过。
- 目标前端回归 `npm test -- --run src/components/platform/VideoAnalysisCard.test.tsx src/pages/VisionPage.test.tsx`：`21 passed`。
- `npm run build`：通过。
- 修改文件 ESLint：0 error、3 条 `react-refresh/only-export-components` warning（均在 `VideoAnalysisCard.tsx` 的既有导出附近）。
- 完整前端套件此前有 1 项非本次触碰的 `VidatWorkbenchPanel` 异步比较测试失败；单独重跑该用例通过。目标页面回归通过。
- 本次 OpenSpec 修改后的 `openspec validate restore-confirmed-four-player-joint-analysis --strict`：有效。最终真实验收结论仍待修复后 Job 完成。

### 复现与限制

以下命令只读复核旧 Job 已落盘的质量与 Global 诊断摘要：

```bash
JOB='/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_121319_e7f03b/analysis/job-9a640b069a'
python - "$JOB" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
quality = json.loads((root / "four_player_identification_quality.json").read_text())
diagnostics = json.loads((root / "fused_diagnostics.json").read_text())
print(json.dumps({
    "job_id": quality.get("job_id"),
    "status": quality.get("status"),
    "verdict": quality.get("verdict"),
    "thresholds": quality.get("thresholds"),
    "players": quality.get("players"),
    "perception_funnel": diagnostics.get("perception_funnel"),
    "recovery_funnel": diagnostics.get("recovery_funnel"),
}, ensure_ascii=False, indent=2))
PY
```

此处不再使用不存在的 `backend/scripts/four_player_quality.py`。旧 Job 的 `debugTraceEnabled=false`，没有持久化 `joint_debug_trace.json`；`f0_refinement_snapshot.v1.json` 仅保留已分配到 global 的观测，不包含所有 YOLO 原始检测或被 ROI/local lock 丢弃的候选。因此旧产物能确认 global/metric/P 标签断点，但不能单独区分 detector、ROI/local track 与 global association 的首断点。

新 Job 的 `fused_diagnostics.json` 将在 `perception_stage_trace` 保存开场、长缺口、名册锚点和末段窗口内的逐视角 raw/ROI/local/candidate/association/metric 计数及当时的四槽锚点审计结论。该字段是固定窗口汇总，不是逐帧原始 YOLO dump；逐帧 Debug Replay 仍由 `debugTraceEnabled` 单独控制。
