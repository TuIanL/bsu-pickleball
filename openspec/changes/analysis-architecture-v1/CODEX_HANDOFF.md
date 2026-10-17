# analysis-architecture-v1 实施交接

本目录是已整理的 OpenSpec 提案，不表示实现完成。当前用户授权范围是修订并产出 proposal；后续只有用户要求实施时才进入 apply。Downloads 中原始包作为参考保留，不直接复制其“立即 apply”指令。

## 阅读顺序

1. proposal.md：需求、范围、7 个新增能力规格和 7 个修改能力规格。
2. design.md：D1–D13 的已确定技术决策、迁移和风险。
3. specs/：对外可验证合同；MODIFIED 块使用现有 requirement 的精确名称并保留原场景。
4. tasks.md：全部待实施；按依赖顺序执行。
5. RESEARCH_AND_AUDIT.md：本地事实、原方案修正和验收边界。

## 本期交付边界

完整蓝图包含球员、球、球拍、姿态、运动证据、挥拍、接触、动作属性、Shot/Rally、落点、语义和战术。生产可执行试点仅 player.detect、ball.detect、pose.sequence；未来域以 planned 类型/声明及测试 fixture 验证，不能把 fixture 当真实模型。

局部单摄/双摄共用同一 Planner/Executor/Worker。完整产品默认 legacy_v1，模块显式 modular_v1。本期不迁移指标/报告，不拆 joint 内部协同，不修改身份算法或检测阈值。

## 必须保留的决策

- 能力、实现、产物 schema、taxonomy 独立版本。
- 最小依赖闭包；preview 零视频打开、零模型构造、零持久化写入。
- 先依赖/窗口/采样，再缓存提示；运行时基于实际输入重新核验。
- plan_hash 不含随机 ID、时间、动态缓存状态和物理输出位置。
- 局部窗口默认前后累计扩展各不超过 2000ms；raw detect 无额外默认预热，非法/seek 失败不跑全片。
- 采样相位、来源 PTS、同步映射、初始化方式必须冻结；双摄不以 nominal FPS 替代权威 clock。
- 缓存键与内容摘要分开；cache_key 不在 Artifact 表上设唯一约束，独立指针允许同键新 artifact_id。
- 存活血缘和来源 pin 保留上游；删除 Job 不递归删共享产物，历史被 pin 私有文件不能误删。
- v1 节点间使用持久化产物，允许有界重新解码；不承诺单遍共享流。
- 节点状态、availability、quality、Job 终态分别表达；默认 all_targets，显式 best_effort 才允许 succeeded+partial。
- 文件 finalize 后还需 lease 保护的 DB 发布事务；DB 提交前 orphan 不是缓存。
- 节点重试复用已发布上游；job attempt/node_attempt 分开，不支持节点内部 checkpoint。
- 姿态 observation scope 不假装稳定 tracking；隔离 RTMPose 的 track_id 历史。
- module manifest 不经过 legacy on_completed/stage_from_pipeline/报告回调。
- v1 trace 兼容，v2 用 outcome/cache_decision 扩展语义，沿用旧 event 枚举。

## 实施顺序与协作

任务组 1–5 完成边界与纯合同/规划，6–8 接入存储、执行与既有控制面，9 完成真实试点，10 验证未来扩展，11 接入入口/trace/最小 UI，12–13 验收与发布。

restore-confirmed-four-player-joint-analysis 的未完成真实身份验收不阻止独立合同、Planner 和 raw adapter。进入共享 executor/身份文件前重新核对该 change，固定基线和文件归属；不要把本轮架构改动变成身份算法修复。

默认请求行为应始终保持 legacy；各阶段保留可运行检查点，不等所有未来模型完成才验证架构。

## 验收证据

分别记录合同 fixture、Worker/存储集成、真实推理、算法质量。真实证据必须有媒体/模型摘要、命令、窗口、计划/产物、实际 capture/解码/模型计数与耗时。

关键验收：单摄三能力无标定执行；双摄 raw ball 不启动整场 segmentation/joint tracking；同窗口第二次全缓存零 capture/模型；只改 pose 参数只影响姿态分支；失败重试和中断恢复保留上游；损坏/离线/并发发布/删除引用都能解释。

本轮只做文档结构和一致性校验，没有运行上述模型或性能验收，不得勾选 tasks.md 的实现任务。
