## 1. 语义契约与配置

- [x] 1.1 定义 `MatchSemanticSnapshot`、phase、authority、evidence、policy decision 和 fallback 的类型契约，并补充序列化/反序列化单元测试
- [x] 1.2 定义 `BallSearchPolicy` 的决策结构，明确 raw candidate、tracker-consumable candidate、formal published candidate 和 policy-suppressed candidate 四种结果层级
- [x] 1.3 增加 Shadow/Enforced、语义时间线、发球准备和策略门控所需配置，默认保持 Shadow Mode 且 fail-open
- [x] 1.4 为语义配置生成 diagnostics snapshot，确保任务可以记录实际生效的 phase、阈值、时间单位和版本

## 2. 时间线与语义状态策略

- [x] 2.1 实现统一的 semantic timeline provider，在 canonical take time 上解析 manual、corrected、algorithm 和无 authority 的时间线状态
- [x] 2.2 接入现有有效比赛时间窗口和 `non_play`、`rally_start`、`rally_end` 事件，并为 capture take 缺失、时间线读取失败和历史事件缺字段提供兼容回退
- [x] 2.3 实现 `UNKNOWN`、`NON_PLAY_CONFIRMED`、`PRE_SERVE`、`SERVE_ARMED`、`RALLY_ACTIVE`、`RALLY_END_CANDIDATE`、`POST_RALLY` 的保守状态转换和滞回逻辑
- [x] 2.4 将球员静止/移动、站位、ServeStartDetector 输出和最近球证据接入 evidence，不允许单一弱证据直接硬结束回合
- [x] 2.5 为状态转换和边界条件补充单元测试，覆盖手持球、捡球、比分结束、发球准备、正常回合、长时间丢失和未知状态

## 3. 单摄球链兼容接入

- [x] 3.1 在单摄球检测/跟踪流程中接入 `BallSearchPolicy`，确保策略评估发生在正式候选发布前且不破坏现有 `BallTracker.update(frame)` 兼容入口
- [x] 3.2 实现权威 `non_play` 窗口的 enforced 抑制：禁止新候选进入正式 tracker 输出，但保留原始候选、authority、phase 和抑制原因
- [x] 3.3 确保被语义策略抑制的候选不增加静止误检黑名单计数，且 `UNKNOWN` 或 provider 失败时完整回退现有连续性、物理门和黑名单逻辑
- [x] 3.4 将 ServeStartDetector 的结果作为 `PRE_SERVE`/`SERVE_ARMED` evidence 接入，不在本任务中把它直接升级为正式击球或回合结束事件
- [x] 3.5 增加单摄 Shadow Mode 对照测试，验证现有 ball trajectory、bounce、event 和 v3/v4 输出在 Shadow Mode 下保持一致

## 4. 双摄 canonical prepare/commit

- [x] 4.1 将 `CanonicalBallStereoProcessor` 的每 tick 处理拆分为候选 prepare、策略消费 commit 和后续 stereo evidence 阶段，prepare 阶段不得更新 tracker
- [x] 4.2 调整 `MultiViewJointRun` 的 tick 顺序，使球候选 prepare 之后完成当 tick 球员感知和 global association，再执行语义评估与球 tracker commit
- [x] 4.3 保证双摄每视角每 canonical tick detector 只调用一次、tracker 最多更新一次，并为重复调用、缺帧和异常降级补充测试
- [x] 4.4 让双摄两路共享同一个 canonical `MatchSemanticSnapshot`，不允许每个视角独立产生冲突 phase
- [x] 4.5 保留旧双摄结果作为 Shadow baseline，记录策略前后候选数量、tracker 接受数量、抑制数量和 stereo measurement 差异

## 5. 语义诊断产物与回放

- [x] 5.1 定义并生成 `ball_semantic_timeline.v1` 或等价结构化 artifact，按 tick 保存 phase、authority、evidence 摘要、policy decision、candidate counts 和 fallback
- [x] 5.2 将语义诊断接入 job artifact 状态、路径、detail 和失败降级逻辑，确保诊断生成失败不影响球员分析和旧球路产物
- [x] 5.3 为诊断增加按时间重放和新旧策略对照所需的稳定字段、版本号、source take、frame stride 和 timestamp provenance
- [x] 5.4 编写固定回放 fixture，至少覆盖非比赛时刻、手持球、场外物体、发球准备、正式回合、遮挡/丢失和回合结束候选

## 6. 验证与灰度启用

- [x] 6.1 建立 Shadow Mode 指标：非比赛误检候选/分钟、发球后首次可靠球观察延迟、回合内候选召回率、抑制比例、UNKNOWN 比例和新旧轨迹差异
- [x] 6.2 运行现有球跟踪、ball event、ball flight、双摄 canonical、v3/v4 artifact 和 player pipeline 回归测试，并确认球员分析不因语义 provider 失败而失败
- [x] 6.3 在固定真实片段上人工核对策略状态、候选抑制和发球重新捕获结果，记录误抑制与误放行样本
- [x] 6.4 默认保持 Shadow Mode；仅在验证通过后允许配置启用 manual/corrected `non_play` 的 enforced 硬抑制
- [x] 6.5 验证关闭语义策略配置后可以恢复现有单摄和双摄球处理路径，形成可执行的回滚检查项
