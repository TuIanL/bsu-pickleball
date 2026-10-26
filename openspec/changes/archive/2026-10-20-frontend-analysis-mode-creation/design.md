## Context

`analysis-architecture-v1` 已归档。后端 `analysis_runtime` 提供 Registry、Planner、不可变产物、缓存与 Worker 执行，首批实现为 `player.detect`、`ball.detect`、`pose.sequence`；姿态实现依赖球员检测，均不消费球场或名册。其余目录能力为 planned。`AnalysisJobCreate` 已支持 `analysisEngine` 与 `modularRequest`，前端 `createAnalysisJob` 仍只序列化 legacy 字段。

三个创建页分别管理上传/已有视频、录制机位、双摄 take。提交与四角标定回调或完整双摄准备条件绑定；当前 `AnalysisFlowSelector` 的 new/legacy 只控制 `useRallyContext`，不代表分析 engine。模块详情已经有最小清单页，但缺少创建 API、用户化展示及正确的来源返回文案。

`libraryAdapter.selectLibraryAnalysisState` 当前会选中任何公开 completed 任务作为完整结果；历史版本解析也没有 engine 门控。直接增加模块创建会把仅球检测的结果送入完整报告消费者。`SyncAnchorStatus` 只有同步状态摘要；确认接口虽返回 calibration，刷新后的创建页不能依赖该瞬时响应。`SyncAnchorService.status` 可能执行旧确认的懒迁移，不能原样引入无副作用的计划预览。

## Goals / Non-Goals

**Goals:**

- 上传、单摄录制、双摄录制共用模式与专项创建流程，保留原路由和素材身份。
- 用户能选择单项或组合能力、片段和采样，在预览实际依赖后创建持久化任务。
- 明确准备失败、环境缺项、同步失效、预览过期和部分结果，避免假成功。
- 前端按领域拆分，共用 API、状态机和配置组件，后续能力可按目录接入。
- 补齐从创建、进度、结果到素材历史的完整链路。

**Non-Goals:**

- 不把完整比赛分析迁移到 modular，不实现 planned 能力，不修改算法阈值或四人身份逻辑。
- 不提供任意 DAG 编辑器、模型路径输入、跨 Job 手动绑定 Artifact 或跨节点解码优化。
- 不增加检测框/骨架视频叠加或完整报告；本期交付可读的模块摘要、质量、产物与技术详情。
- 不新增节点恢复 UI；沿用已有取消能力，失败后的再次创建仍遵守后端去重/新版本语义。

## Decisions

### D1. 用户模式与后端 engine 分层

默认是“完整比赛分析”，继续使用 legacy API。专项预设映射为球员检测 `[player.detect]`、球检测 `[ball.detect]`、姿态分析 `[pose.sequence]`，自定义组合支持首批已实现能力的非空集合。自定义不意味着用户必须手工选中姿态的上游依赖。名称和说明由前端集中维护，执行可用性由后端 catalog 与准备结果决定；新出现但尚无前端配置支持的能力不自动暴露复杂表单。

现有新/旧流程选择只在完整分析分支出现。完整分支的推理开关、名册和标定不传入模块请求，专项参数也不污染完整分析请求。模式切换保留已上传视频和可独立保存的各分支草稿，使计划失效；初版不持久化专项草稿到浏览器存储。需要跳往同步工作台时，在嵌套 return 中保留模式、目标、窗口和采样这些可验证的轻量查询参数，回来后重新准备与预览。

备选：给三个旧页面各加几个推理开关。放弃原因是开关不能表达独立目标、自动依赖和新 engine，也不能解除完整链路的前置条件。

### D2. 共用配置与状态机

建议新增 `types/analysisModules.ts`、`services/analysisModuleClient.ts`、`services/analysisModeConfig.ts`、`hooks/useModularAnalysisCreation.ts` 及 `components/analysis/` 内的模式、专项表单、计划预览组件。具体文件名可按实施时邻近命名调整，但 API/纯映射/状态管理/渲染边界须保留。只从通用 HTTP 层共享传输，不复制 `requestJson` 错误处理；保持页面懒加载边界。

三个页面只负责解析来源、提供视频预览/上传、拼装可追溯的比赛元数据与 return。状态机为：

```text
编辑 → 准备来源/环境 → 可预览 → 预览中 → 计划就绪 → 提交中 → 已创建
             ↓                    ↓           ↓
           准备失败             预览失败     提交失败
配置或同步版本变化 ───────────────→ 计划失效
```

专项默认范围为参考视频前 30 秒（不足 30 秒取实际长度），提供明确的“整个视频”选择；输入以秒编辑，协议以整数毫秒传输，满足 `0 ≤ start < end ≤ duration`。默认每 2 帧采样一次，与现有创建页一致，允许正整数步长，phase/anchor 使用协议默认值。本期默认 `all_targets`；高级设置可选“尽可能保留成功目标”映射 `best_effort`，并说明成功仍可能只有部分结果。算法阈值/实现选择先采用后端默认值，技术预览展示实际有效值。

准备、预览、提交均有在途守卫。来源/配置修订号用于忽略旧异步响应；换视频、卸载或切换模式后，旧响应不能重新激活提交。准备请求写入的是可复用快照，不应声称浏览器 abort 能回滚后端准备。重试复用已上传 videoId，避免重复上传。

### D3. 补齐薄 API 接口并保持预览纯读取

复用 `GET /api/analysis/capabilities`，保持现有数组响应。增加只读 `GET /api/analysis/runtime-status` 返回 `modular_submission_enabled`；目录实现状态与部署是否允许提交分别判断。复用单摄 `POST /sources/prepare`、`POST /models/prepare`、`POST /plans/preview`、`POST /jobs`、清单和产物 API。环境关闭、接口不兼容或目录加载失败时只禁用专项分支，并保留重试与完整分析。

模型准备返回每个实现的状态，前端只阻断选中目标及实际依赖所需模型；缺姿态模型不能阻断单独球检测。首批依赖可用性在准备后的真实 Planner 预览中最终裁决，不在前端重建依赖图。计划预览仍只读取已准备快照，不加载模型、解码媒体、迁移同步文件或创建 Job。

增加 `POST /api/analysis/takes/{take_id}/sources/prepare`：从服务端已登记 take/track/video/camera 关联及同步服务准备双路 SourceSnapshot，返回公共 source 元数据、`source_ids`、权威 `reference_view_id`、完整同步快照和其 revision/provenance fingerprint；不得返回宿主媒体路径。该接口可以做显式媒体准备和既有同步确认迁移，但不能自动确认锚点。机位参考采用已确认同步的 reference camera，本期不在专项表单另设冲突的参考时钟。

为 `AnalysisRequest` 增加可选 `source_binding`（take_id、同步 revision、provenance fingerprint），Web 双摄必须携带。Planner 通过注入的只读校验器验证该绑定仍匹配已登记来源和权威同步；当前 CLI 未携带绑定时继续使用已有 source/sync 合同。同步绑定不成为未消费算法上下文，影响计算的媒体/PTS/sync 仍由既有 plan hash 冻结。读取校验不得调用有懒迁移副作用的 status 路径；需要迁移时返回待准备项。

准备与提交都校验视频归属及同步有效性，失败返回稳定错误码和同步工作台入口。A/B 单机分析仅准备选定视频，不要求另一路或双摄同步。

备选：让浏览器通过 SyncAnchorStatus 估算 sync。放弃原因是摘要缺失正式映射，刷新还会丢失确认响应，容易错误降级为名义 FPS。

### D4. 预览到提交保证语义一致

模块提交使用独立类型化 client，仍发往 `/api/analysis/jobs`，携带 `analysisEngine=modular_v1`、`modularRequest`、metadata，以及新增可选 `expectedPlanHash`。Web 必须携带最新预览 hash；后端在原有提交路径构建实际 plan，在写入 Job 前比较语义 hash，不另行生成第二份可能漂移的计划。不同则返回 `409 plan_preview_stale`，不创建任务，页面保留表单并要求重新预览。已有未带 hash 的 CLI/API 请求保持行为。

缓存提示是预估，不承诺命中；缓存状态变化本身不使语义预览失效。模型身份、实现参数、来源或同步内容变化才触发重新准备/预览。预览响应不持久化计划，实际提交才冻结。

默认不请求新版本，重复点击/网络重试相同请求由后端返回已有 Job。用户显式勾选“创建新分析版本”映射 `new_version=true`，仍可能复用有效节点缓存，不应命名为“强制重新推理”。新版本请求响应丢失时，不自动重发；先查询素材历史核对，无法确认时展示结果不确定提示，由用户明确决定后续动作，避免自动产生多份任务。

### D5. 完整结果与模块历史分开投影

Library 历史 view model 保留 engine、目标摘要与来源字段；来源关联复用已核实的 videoId、recording_session_id、capture_take_id/camera slot 元数据，模块服务补齐必要持久化关联。return 只承担导航，不作为后台归属凭据；不得靠标题或任意 URL 反推所有权。

`primaryResultAnalysisJobId` 与兼容别名只选择 legacy（含缺省 engine）的完整结果，并保留双摄 Parent 优先规则。active 投影与历史计数覆盖模块任务，完成时仍定向重投影；只有专项结果的素材在历史中显示“专项分析已完成”，完整结果为空，数据分析/报告/球路不被启用。不得因完整结果为空而将成功的专项历史显示成失败。

模块历史按钮为“查看专项结果”，进入 `/analysis/:jobId?return=...`。模块详情自身承接进度与结果，完成不自动跳入 legacy Workspace。若用户手写 `analysisJob=模块任务` 深链，先验证素材归属，再 replace 到带原素材 return 的模块详情；跨素材或未知任务仍走既有拒绝/回退。旧的完整历史选择和已选完整版本保持不变。

备选：把模块结果直接嵌入 Workspace 的所有分析 Tab。放弃原因是目前各 Tab 消费 legacy 固定产物，扩大改动而不能增加首批原始观测的报告含义。

### D6. 结果展示遵守模块证据

复用 `ModularAnalysisRunView`，中文模式与能力名称、片段、所选目标、自动依赖、执行进度优先展示。按 manifest.targets 区分目标/依赖，不能从 nodeRuns 所有节点推断用户勾选。显示 pending/running/cached/completed/failed/blocked/canceled/skipped；完整性 complete/partial/none 与每个产物 quality/availability 独立表达，`no_candidates` 不伪装成检测成功有对象，`insufficient_evidence` 不伪装成可信结论。

取消只在允许的 active 状态显示；清单/产物读取失败提供局部重试，不清空已有内容。产物与 trace 只按用户展开按需加载，技术内容保留截断和可读错误。返回文案由 origin 决定，Library 显示“返回比赛详情”，不硬编码返回任务管理。

## Risks / Trade-offs

- [同步服务读取可能写入旧确认迁移] → 准备阶段承担迁移，preview/submit 校验抽出纯读取路径并用副作用测试证明。
- [部署声明 implemented 但模型缺失] → 分开显示实现、服务启用和模型准备状态；仅阻断所选依赖。
- [两路 camera_id 与 view_id 混用] → 由服务端 take 关联返回真实映射，以 Planner 原有权威检查兜底。
- [模块任务覆盖旧报告或进入固定结果 schema] → 在 primary、历史选择、深链和 CTA 各边界统一 engine 分流，并补集成回归。
- [准备计算耗时与旧请求竞态] → 显示准备阶段、复用已上传视频、忽略旧修订响应；本期不把准备改成后台工作流。
- [新版本创建响应丢失] → 禁止自动重发非幂等版本创建，先用历史核对并保留不确定状态。
- [清单缺少完整计划配置摘要] → 首批按已存在的节点实现/配置指纹和 manifest.targets 展示，不伪造无法读取的模型参数；必要的轻量公共摘要随现有清单兼容扩展。

## Migration Plan

1. 先落地兼容 API 字段、runtime 状态、take 准备和只读校验；保持旧 catalog 和未带 hash 的请求不变。
2. 接通共用前端创建流程与三个页面，默认完整模式；后端不支持新增接口时专项明确不可用。
3. 同步上线 Library engine 投影、模块结果导航和中文详情，不能只发布创建入口。
4. 通过针对性前后端测试、构建和真实短片冒烟；真实模型缺失时记录未验证项，不以 fixture 冒充真实推理。
5. 回滚可用现有 `PICKLEBALL_MODULAR_ANALYSIS_ENABLED=false` 禁止新增模块提交；已创建模块任务的清单读取保留，legacy 创建不受影响。无破坏性数据迁移，不删除任何旧任务或产物。

## Open Questions

无阻断产品决策。本期已确定默认完整分析、专项默认前 30 秒、首批三个能力及组合、结果以清单摘要呈现。实施时需核对同步服务的只读提取点与素材关联字段，记录实际部署的模型可用性；这些属于接入验证，不改变本提案范围。
