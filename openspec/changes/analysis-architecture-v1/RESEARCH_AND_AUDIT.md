# 本地代码审查与方案修订记录

## 审查范围与证据级别

审查基线：2665bc3b974656cec45cd54e875d03cd3a8994c6。参考源为 /Users/tuian/Downloads/analysis-architecture-v1 的完整解压包及本轮对话中的架构建议。原包只读保留；本目录是根据实际代码重新编写的提案。

结论来自静态代码/规格检查和 OpenSpec 校验，没有执行真实模型、视频分析、算法准确率或性能基准。本地代码比报告中的抽象描述优先；不将附件内的操作指令自动提升为用户授权。当前未改应用代码、未 commit/push。

## 代码事实及架构影响

下列路径相对于仓库根；行号用于本次基线定位，实施时重新核对。

| 代码事实 | 位置 | 对提案的影响 |
| --- | --- | --- |
| Pipeline.run 同时编排多类能力，tracking 有共享帧循环 | backend/app/services/analysis_pipeline.py:438、1806、2154 | 通过新 engine 绕开完整编排，不能靠后半段 skip 达成独立验证 |
| 模型并非全都在构造器立刻加载 | Pipeline 及 detector/RTMPose 适配器 | 修正原包“构造即重加载”的过强判断；仍需证明未请求节点不构造/运行资源 |
| Executor Protocol 返回 AnalysisPipelineResult，单摄重建请求 | backend/app/services/analysis_executor_dispatch.py:66、131 | 返回类型需判别；持久化有效开关必须保真 |
| segmentation prerequisite 无可复用 run 时从 start_ms=0 采样 | backend/app/services/analysis_executor_dispatch.py:391、461 | 双摄局部 raw 验证避开正式切分 prerequisite，不宣称整条 legacy 前处理已局部化 |
| Worker signature/is_runnable/整体执行/完成回调带旧路径假设 | backend/app/services/job_orchestration.py:414、714、1335、1510 | 新计划签名、模块领取、节点重试、清单发布需显式修改合同 |
| 完成回调生成 canonical events/metrics/insights/report | backend/app/services/mock_analysis.py:113 | 模块不得调用该默认产品回调 |
| 删除任务清理 Job 根并可能清理私有上传源 | backend/app/services/mock_analysis.py:600 | 共享证据/来源 pin 需独立生命周期，检查私有目录内仍被引用文件 |
| SQLite 控制面已有任务权威记录 | backend/app/services/analysis_control_plane.py | 复用队列、租约、heartbeat，不引入第二套 Job 系统 |
| 现有窗口默认 pre/post=1500/500ms | backend/app/services/analysis_window.py:95 | 这是 legacy 默认；模块实现自己声明上下文，不给 raw detect 强加预热 |
| source PTS 与 canonical clock 已存在 | backend/app/services/frame_timing_provider.py、backend/app/vision/multiview/analysis_clock.py | 复用时间权威及 no_new_frame，固定采样相位 |
| joint 内部协同是有状态结构 | backend/app/vision/multiview/multiview_joint_run.py、backend/app/services/multiview_joint_executor.py | 保持内部边界；新 raw 双摄不宣称替代 joint 3D |
| ball finish 先事件与分段，再 reconstruct_segment | backend/app/vision/multiview/ball_stereo/canonical_runner.py:874 | 区分观测/清洗/重建轨迹，避免 DAG 环 |
| 姿态适配器以人框推理，但有按 track_id 的 visibility 历史 | backend/app/vision/pose/rtmpose26_adapter.py:42、84、200 | 无 tracking 的 raw 姿态需 observation scope 并隔离历史 |
| VideoMetadata 无内容摘要/不可变 revision | backend/app/schemas/video.py:16 | 必须显式准备强媒体/PTS 身份，不能把路径当内容 |
| AnalysisArtifacts 是大型固定字段模型，结果要求 metrics | backend/app/schemas/pipeline.py:41、203 | 保留兼容表面，新模块用通用 Manifest/Ref |
| Shot 的 shot_type 被设置为 stage | backend/app/services/canonical_shot_rally_events.py:732 | 动作属性/比赛阶段/丁克等语义分别定义，不能复用旧字段改含义 |
| Landing 严格引用 Shot/segment/event | backend/app/services/shot_landings.py | 不用最近时间补齐缺失关联 |
| 现有动态 artifact 路由使用 Literal 参数 | backend/app/api/routes_analysis.py:586 | 新 manifest 用独立路径，避免被解析为旧 artifact_name |
| 文件原子写入和 attempt marker 已存在 | backend/app/services/storage_service.py:327、416 | 仍需 DB 发布事务和 lease 核验；不能声称现有工具已实现跨资源原子性 |

export_swing_skeleton.py 是导出验证，action_classification_preprocessing 是数据准备；二者不是完整动作模型。已有原语可适配，并不证明其模块接口、身份和缓存语义已经完成。

## 相对原包的修订

| 原包不足或需要澄清之处 | 本次修正 | 主要落点 |
| --- | --- | --- |
| 只 ADDED 旧 executor/job/trace 规格，仍与旧 MUST 冲突 | 以精确 requirement 名称提供完整 MODIFIED 块并保留原场景 | 7 份修改规格，任务 8 |
| 对跨域姿态、产物、任务删除合同考虑不足 | 明确 legacy 作用域，加入 raw pose、共享根、清单入口与引用保留 | pose-estimation-engine、analysis-artifacts、analysis-task-management、match-analysis-pipeline-capabilities |
| plan hash 与随机 ID/时间/缓存提示界限不够清晰 | semantic 白名单，依赖/窗口先于缓存，运行时实际绑定 | D4，任务 4 |
| 同键唯一 Artifact 无法在不覆写历史的条件下重建 | Artifact 非唯一计算键，独立 current 指针 | D7，任务 6 |
| 只计算 Job 直接引用容易误删上游/源 | 血缘、固定输入、活动运行和来源 pin，默认保守保留 | D7，任务 6.6–6.7 |
| 共享解码资源、独立节点与恢复之间缺少明确协议 | v1 使用产物边界和有界重新解码，streaming group 后置 | D8，任务 7、9 |
| 节点 unavailable/失败/质量及 Job 成功策略可能混用 | 正交状态，all_targets 默认；显式 best_effort/partial | D9，任务 7.2 |
| 窗口预热、动态事件边界容易隐含扩大范围 | 累计有限预算、输出选择版本、中间上下文、GOP 预读分开 | D5，任务 5 |
| 旧 trace 固定枚举不能直接塞新事件 | v2 增加 outcome/cache_decision/node_attempt，旧枚举保留 | D13，任务 11.4–11.5 |
| 文件 atomic finalize 被误认为 DB+文件整体原子 | DB 是发布可见性边界，orphan/迟到 lease/CAS 单独处理 | D10，任务 7.4–7.6 |
| 流程蓝图可能被理解为所有模型本期交付 | 全域 planned，三能力真实适配，未来 fixture 和真实验收分列 | D2，任务 9–10、12 |
| 活跃身份 change 被当成所有工作的前置阻塞 | 仅对重叠 executor/身份编辑协调，纯合同/raw 可先行 | 任务 1.2 |
| 原包某条 ADDED requirement 缺少 SHALL/MUST | 新规格每条均有规范词和 WHEN/THEN 场景，统一严格校验 | validation.md |

原包已有的静态注册、冻结上下文、类型化产物、资源/产物区分、能力优先于目录重排等方向保留。本次修订集中在使这些方向可执行、可恢复且与现有合同兼容。

## 规格与任务覆盖

| delta spec | 主要任务组 |
| --- | --- |
| analysis-capability-runtime | 2、4、7、9–10 |
| analysis-artifact-lineage | 3、6–7、12 |
| analysis-local-validation | 9、11–12 |
| analysis-evidence-association | 2、10 |
| analysis-window-planning | 4–5、9、12 |
| analysis-context-contract | 3、5、9–10 |
| analysis-result-publication | 6–8、12 |
| analysis-job-executor-dispatch | 8 |
| analysis-job-orchestration | 4、7–8 |
| analysis-run-trace | 11、12 |
| match-analysis-pipeline-capabilities | 4、8、12 |
| pose-estimation-engine | 9、12 |
| analysis-artifacts | 6、8、11–12 |
| analysis-task-management | 6、11–12 |

## 验收限制

OpenSpec 校验通过只证明提案结构有效，不证明实现正确、分析提速或模型质量。后续任务必须提交真实单摄/双摄短窗口证据，不能将 mock、缺模型、空占位产物计为真实通过。

本轮文件与规格一致性检查结果见 validation.md。所有实施任务保持未完成。
