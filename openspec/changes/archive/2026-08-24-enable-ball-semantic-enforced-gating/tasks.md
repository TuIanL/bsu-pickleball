## 1. 语义门控与生命周期契约

- [x] 1.1 扩展 `BallSemanticPolicyConfig`，增加 take/job 级 Enforced rollout、权威来源限制和回滚快照字段，保持全局默认 Shadow/fail-open
- [x] 1.2 定义 boundary action、action id、formal segment lifecycle 和 warm/reacquire 层级的类型契约，并补充序列化/反序列化测试
- [x] 1.3 扩展 `BallSearchDecision` 与 `MatchSemanticSnapshot`，记录 rollout 生效条件、boundary action、formal publish before/after 和 fallback 原因
- [x] 1.4 为 `SemanticStateMachine` 和 timeline provider 增加 phase 边沿检测、权威 `rally_start`/`rally_end`/`non_play` 映射及 action 幂等规则
- [x] 1.5 补充状态机测试，覆盖 active→non-play、post-rally→pre-serve、pre-serve→serve-armed、rally-start→active、重复 boundary tick 和 provider 失败

## 2. 单摄正式球链门控

- [x] 2.1 在 `BallTracker` 增加语义边界生命周期入口，支持封存当前 formal segment、清理预测/暂态连续性状态并保留 raw/diagnostic history，同时不破坏 `update(frame)` 兼容入口
- [x] 2.2 在单摄 `_process_ball_frame` 的正式候选发布前接入 Enforced gate：权威 `non_play`/`rally_end` 禁止新候选进入 formal tracker，Shadow/UNKNOWN/algorithm 继续走旧路径
- [x] 2.3 确保 semantic suppression 不增加 stationary false-positive blacklist，并为 raw、warm、tracker-consumable、formal、suppressed 层级补充逐帧诊断
- [x] 2.4 实现 `PRE_SERVE`/`SERVE_ARMED` 的 warm/reacquire 路径，过滤手持静止球，并在运动/连续性/发球区域或权威 `rally_start` 条件满足后打开新的 formal segment
- [x] 2.5 增加单摄边界测试，验证边界后候选不会追加到旧轨迹、重复 reset 不改变结果、下一回合不会复用上一回合的 segment/prediction 状态

## 3. 双摄 canonical 一致性

- [x] 3.1 调整 `CanonicalBallStereoProcessor` 的 commit 阶段，使 joint 层提供的单一 snapshot/decision/action 在两路 tracker 更新前统一生效
- [x] 3.2 为双摄 boundary action 增加 action id 幂等保护，保证同一 canonical tick 只封存/重置一次，且两视角共享相同 phase、timestamp 和 segment boundary
- [x] 3.3 调整 `MultiViewJointRun` 的 tick 编排，保持 detector 每视角每 tick 一次、tracker 最多更新一次，并覆盖 boundary tick 的 player barrier、缺帧和 `available_extrapolated` 情况
- [x] 3.4 增加双摄对照测试，验证一路缺失不会产生第二个 phase/segment，stereo association 不会反向恢复已封存的正式 tracker 状态

## 4. 诊断产物与灰度配置

- [x] 4.1 扩展 `ball_semantic_timeline.v1` 诊断字段，记录 rollout、boundary action、action id、formal candidate before/after、tracker state before/after 和 segment ids
- [x] 4.2 将 Enforced simulation 与实际 Enforced 结果区分记录，补充 suppression、boundary seal、reset、warm capture、formal publish 和 fallback 计数
- [x] 4.3 将 take/job 级 rollout 配置写入 artifact/config snapshot，并保证诊断生成失败不影响旧球路、球员分析和回滚路径
- [x] 4.4 增加 artifact/API 契约测试，确保新增字段向后兼容、旧任务无语义上下文时仍返回 available/skipped/unavailable 的既有状态语义

## 5. 真实素材验证与回归

- [x] 5.1 增加固定回放 fixture，覆盖回合外手持球/捡球、权威 `rally_end`、发球准备、`SERVE_ARMED`、正式回合、单视角丢失、未知状态和 provider failure
- [x] 5.2 在相同 detector candidates、model path、frame stride 和 timeline 下生成 Shadow-vs-Enforced 对照，验证不重复运行 detector 且输出可重放
- [x] 5.3 使用 2026-07-20 双摄真实素材 `take_sync_20260720_112124_00d84c` 的同一时间点核对：非比赛 formal suppression、回合封存、发球重新捕获、回合内不误抑制和跨视角一致性
- [x] 5.4 记录真实素材核对结果、误抑制/误放行样本、首球捕获延迟、边界泄漏和未知比例，并确认 `models/ball/tennis-ball.pt` 未被修改
- [x] 5.5 运行 ball tracker、ball event、trajectory reconstruction、dual-view、player pipeline、artifact API 和配置回归测试；验证关闭 Enforced rollout 可恢复第一阶段 Shadow/兼容结果
