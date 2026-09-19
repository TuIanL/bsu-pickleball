## Context

当前回合状态模型的训练、验证和候选产物链路已经具备模型包校验、双摄 RGB cache、时间线解码和人工 accept/correct/reject 审计。它服务于研究验证：`scripts/infer_match_state_rgb_candidate_timeline.py` 依赖 dataset manifest、RGB JPEG cache 和人工 labels，并把预测输出到 `data/match_state_candidates/`。

当前正式双摄分析有两条编排路径：`joint_tracking_v2` 的 public Parent 可直接被 Worker 领取；`late_fusion_v1` 会在创建 Parent 时立即创建两个 internal child，只有 child 完成后 Parent 才在 `fusion_ready` 被领取。现有候选接受路径调用 `create_manual_rally()`，因此会把已人工确认的候选写成 `manual/closed` 片段；这不能表示模型自身的正式输出。`SegmentManagerPage` 同时承载普通片段浏览和完整研发复核工作台，而 `AnalysisBatch` 目前只持久化批次并不派发 AnalysisJob。

本设计把模型提升为正式双摄分析的规划前置条件，而不删除既有 QA 资产。正式 `match_default` 双摄任务必须固定一份可复现的回合窗口计划，任何后续模型重跑、自动片段替换或人工时间线变化都不能改变已运行 Job 的依据。

## Goals / Non-Goals

**Goals:**

- 让用户只点击一次“开始双摄协同分析”，即可自动生成并使用正式模型回合，无须赛后人工逐条确认。
- 为每次正式推理保存可审计、可重试、可替代的 `MatchStateSegmentationRun`，并将自动 Segment 与人工 Segment 在数据和界面上清晰分离。
- 对 `joint_tracking_v2` 和 `late_fusion_v1` 都保证切分完成、窗口计划冻结后，才开始依赖回合语义的视觉执行。
- 复用 CaptureTake 的同步校准、PTSs 和 canonical 时间轴；生产推理不从训练脚本或训练期数据资产反向导入。
- 首版以回合窗口驱动有效时间、事件归属和报告，保留连续视频解码与身份状态。
- 将候选复核留作隐藏 QA 能力，收敛普通片段页。

**Non-Goals:**

- 不在本变更中训练、重新调参或变更已验证模型的分类效果。
- 不支持单摄 `match_default` 使用此双摄模型；单摄工程入口维持既有语义。
- 不把每个 Rally 派发为一个 AnalysisJob，也不在 V1 实现多离散窗口的 seek/跳跃式 tracking。
- 不删除 candidate artifact、review API、历史 review 审计或现有人工关键事件。
- 不让正式自动回合直接推导比分、犯规、胜负或未实现的战术结论。

## Decisions

### 1. 用内部 segmentation prerequisite job 表达 Parent-owned 前置阶段

每个新的双摄 `match_default` Parent 在创建后先处于 `waiting_segmentation`，并拥有一个不可在普通任务列表显示的 internal segmentation job。该 job 使用现有 durable JobStore、Worker lease、心跳、取消和重试能力，但其输入是 Parent 的 CaptureTake、两个 CaptureTrack、同步 revision 与模型包配置，而不是一个单摄 Pipeline 输入。

segmentation job 成功后，Coordinator 在单个编排转换中将 Parent 绑定到成功的 `segmentation_run_id` 和不可变 `AnalysisWindowPlan`：

- `joint_tracking_v2`：Parent 转为 `joint_ready`，随后由现有 joint executor 运行。
- `late_fusion_v1`：此时才创建并排队 `cam_1` / `cam_2` internal child，Parent 转为 `waiting_sources`；只有 child 终态后才转为 `fusion_ready` / `fallback_ready`。

这保留“切分属于 Parent”的产品和数据语义，同时避免让一个已被 Worker 领取的 Parent 在非终态中途返回，或让 late-fusion child 先按完整视频开始处理。

备选方案是让 Parent executor 内联执行切分。它在 joint 模式可行，却无法阻止 late-fusion child 的早期创建，且需要重做 Worker 对中间状态、取消和重试的终态假设，因此不采用。另一个备选是把每条 Rally 当作 child Job；它会放大调度和汇总开销，并破坏跨回合身份连续性，因此不采用。

### 2. SegmentationRun 是正式数据锚点，窗口计划是 Job 不可变快照

新增 `MatchStateSegmentationRun`，核心字段包括：`id`、`capture_take_id`、`planning_job_id`、状态（`running/succeeded/valid_no_rallies/low_evidence/failed/superseded`）、模型 package/version/weight SHA-256、decoder hash、输入 video identities/fingerprint、sync calibration revision、timing authority、artifact 位置与 hash、窗口计划 hash、unknown rate、片段数、开始/结束时间和 `supersedes_run_id`。

`CaptureSegment` 增加可空 `segmentation_run_id`。正式发布的回合具有：

```text
segment_type = rally
source       = algorithm
status       = inferred
edit_status  = active
segmentation_run_id = <successful run>
```

人工采集事件和人工片段保留 `segmentation_run_id = null`，永不被切分发布事务改写。

成功 run 的 artifact 中写入 `AnalysisWindowPlan`：按 ordinal 排序的 `{segment_id, start_ms, end_ms}`、run id、artifact hash 和模型 provenance。Parent 保存 `segmentation_run_id` 与 `window_plan_hash`；下游仅消费这份 plan，而不查询“当前最新”自动 Segment。因而 Job A 在运行期间生成 Run 2 时，仍使用 Run 1 的范围。`valid_no_rallies` 写入空 plan（不是 `None`），下游应标记回合派生指标为 `no_active_rallies`，不得回退成整场有效时间。

备选方案是下游每次从 `capture_segments` 查最新 active algorithm rows。它无法保证运行可复现，且会把并行重跑污染到已运行 Job，因此不采用。

### 3. 发布采用“写 artifact，再事务切换”的非破坏式策略

Runtime 先生成和校验临时 artifact；artifact 成功落盘且 schema、输入和窗口均有效后，在一个数据库事务中：创建成功 run、创建新 algorithm/inferred Segments、记录 plan hash，并将同一 CaptureTake 上被新 run 替代的旧 algorithm Segments 置为 `superseded`。人工 Segment 不在查询或更新范围内。

若推理、artifact 校验或事务任一步失败，run 写为失败诊断（若能持久化），旧 run 和旧 active algorithm Segments 保持不变；临时 artifact 由可恢复清理任务处理。失败绝不先清空旧版自动 Segment。

候选 review 的 `create_manual_rally()` 继续专用于“人工接受了候选”的 QA 语义，正式发布不得调用它。现有 `candidate/review` artifact 保持在独立命名空间，不能被正式 Segment 查询 API 当作自动回合来源。

### 4. 生产 Runtime 直接消费同步后的 CaptureTake 媒体

新增 `backend/app/vision/match_state/`，包含模型定义与加载、package 验证、预处理、`MatchStateSynchronizedSampler`、时间线 decoder、artifact schema 和运行服务。训练脚本可复用该稳定模型/预处理定义，生产服务不得导入 `scripts/train_*` 或依赖 dataset manifest、RGB cache、人工 labels、ground truth/evaluation。

Sampler 以 CaptureTake 公共时间为输入：reference view 使用其 `FrameTimingProvider`，secondary view 经已确认的 sync calibration 映射到媒体时间；采样记录 PTS、coverage、view mask、同步 revision 和不足证据原因。V1 的 RGB 模型要求两路完整输入：缺视角、不可读媒体、缺模型包或同步不可用分别生成稳定状态，而非伪造另一视角或按两个视频的相同秒数粗略 seek。

`Settings` 增加 model package 目录、device、batch size、required profile 和 Runtime 启用项；模型 package/权重/训练配置/阈值/预处理文件进入部署 manifest 并验证 SHA-256。Worker 缓存键为 `(package SHA-256, device)`，避免逐场重载权重。

### 5. 用明确结果策略驱动 Parent 转换

正式 Runtime 对外区分：

| 结果 | `match_default` 双摄 Parent 行为 |
| --- | --- |
| `succeeded` | 发布 run/segments/plan，继续分析 |
| `valid_no_rallies` | 发布空 plan，继续但回合派生指标明确 unavailable |
| `low_evidence` | 以稳定质量错误结束 Parent，不继续分析 |
| `model_unavailable`、`input_unavailable`、`sync_unavailable`、`inference_failed` | fail-fast，不释放后续视觉执行 |

工程 profile 可将切分配置为 optional，并必须在 Job/result 中显示其没有正式窗口计划；它不得伪装成 `match_default` 的成功结果。单摄流程标记为 `not_applicable`。

Parent 的阶段图将“回合自动切分”置于 `multiview-input-check` 之前，Parent 进度从 prerequisite job 的遥测投影而来。切分阶段失败、取消或被 Worker 中断时，Parent 展示对应稳定状态，且 late-fusion 不得留下可执行 child。

### 6. V1 持续解码，窗口消费按语义分层接入

V1 不把 `AnalysisWindowPlan` 改造成底层 tracker 的多段输入。双摄视觉执行仍连续解码，必要时通过低频逻辑维护 identity；plan 先供以下消费者读取：有效时间分母、ball/shot 事件的 rally association、回合级统计、可视化和报告范围。

现有 `effective_time_windows` 优先级变为：显式 job clip（若存在）→ job-bound plan（包括空 plan）→ legacy 手工 rally timeline → 仅允许 engineering profile 使用的全视频 fallback。该顺序确保正式 Job 不会混入之后生成的 run 或旧人工事件。

### 7. 片段页仅呈现正式来源，QA 与编辑 API 留在隔离面

普通 `SegmentManagerPage` 只加载并呈现：现场人工关键事件/人工片段，以及当前已发布 SegmentationRun 的 active algorithm Rally。自动区顶部展示一次模型版本、生成时间和回合数；每条只展示 ordinal、边界、时长、来源、播放/定位和关联分析结果。

普通 UI 不调用 candidate/review、边界编辑、创建 Rally、调整 ordinal、split/merge/archive/restore 或 AnalysisBatch API。保留视频、双机位同步播放、时间线、空态和错误兜底。研发候选/人工复核能力保持后端兼容，只能经显式开发入口或 feature flag 使用。

## Risks / Trade-offs

- [模型包或 GPU Runtime 未部署导致正式双摄任务无法运行] → 启动和 prerequisite preflight 同时校验 package、hash、设备和依赖；失败给出 `model_unavailable`，不静默降级。
- [双摄同步未确认或媒体 PTS 不一致导致错误回合] → sampler 只使用 CaptureTake 现有权威 sync/timing assets，记录 revision 和 coverage；`sync_unavailable` / `low_evidence` 阻止 `match_default` 后续执行。
- [Run 重跑与运行中 Job 并发] → Job 固定 run id 和 plan hash；发布只有成功事务才 supersede 旧 segments，计划不从“最新 Segment”动态解析。
- [internal prerequisite job 增加编排复杂度] → 复用既有 JobStore、Worker liveness 和 Coordinator terminal hook，新增明确的 Parent 状态转换测试。
- [连续解码仍花费 non-play 计算] → 首版用稳定性换取身份连续性；后续单独 Change 才评估 non-play 低频或跳跃式优化。
- [历史 QA API 被误当作正式入口] → 前端移除普通导航与调用；API 文档和响应标注 QA，正式 Segment API 以 run summary 为唯一自动来源。
- [自动 Segment 与同一时间段人工 Segment 并存] → UI 按来源分组而不做“谁覆盖谁”的猜测；正式 plan 只引用其所属 run 的 algorithm segments。

## Migration Plan

1. 先部署模型 package、权重、manifest 和 Settings，但不改变现有任务创建；以开发 profile 在真实 CaptureTake 做 Runtime smoke test。
2. 增加表、可空外键、artifact schema 与读取 API，保持历史 `CaptureSegment`、candidate artifact 和 review 审计不变。
3. 启用 prerequisite 编排和新阶段图；仅对新建双摄 `match_default` Parent 生效。历史 Job 与单摄 Job 使用原有阶段和时间线回退。
4. 发布正式 Runtime 和 algorithm Segment 事务，再开启 Parent 的 required policy；在此之前不可将模型状态标记为生产可用。
5. 收敛 SegmentManager 前台；候选复核界面迁移到显式开发入口/feature flag 后，保留 API 与回归测试。
6. 回滚时关闭 required policy 并停止创建 segmentation prerequisite；已有成功 run、segments 和 artifact 保留可读，历史 Job 继续按其已绑定 plan 展示，不回写为人工片段。

## Open Questions

- 生产模型 package 在首个部署环境中的受控目录、CUDA/CPU target 和 manifest 发布流程需要在实施前由部署配置确定；代码接口按可配置目录实现。
- `valid_no_rallies` 的产品文案与结果页呈现需在前端实现时定稿，但其数据语义固定为“模型正常运行、空窗口计划、非整场 fallback”。
