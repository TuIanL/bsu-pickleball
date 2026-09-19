## MODIFIED Requirements

### Requirement: Stage telemetry

阶段遥测 MUST 保持既有 `AnalysisStage` 结构，并由当前分析模式的规范化阶段图生成。`single_view` MUST 继续使用既有单摄稳定阶段。需要正式双摄回合切分的 `late_fusion_v1` 与 `joint_tracking_v2` Parent MUST 将“回合自动切分”作为第一个聚合阶段；它先于素材与同步检查以及任一 A/B 或 joint 视觉执行。后续阶段仍分别按“素材与同步检查 / A 机位视觉分析 / B 机位视觉分析 / 多视角融合 / 指标重算 / 可视化输出 / 报告生成”和“素材与同步检查 / 双摄协同跟踪 / 双摄球路分析 / 指标重算 / 可视化输出 / 报告生成”顺序表达。双摄子阶段进度 MUST 经 `viewRuns` 暴露，运行中应反映最近可用的 child 或内部 `ViewRun` 状态；双摄专用阶段 MUST NOT 被追加到单摄阶段列表末尾。

总体进度 MUST 使用当前阶段图的稳定权重和阶段进度聚合，保持单调递增；MUST NOT 通过包含未来 `pending` 阶段的数量平均值覆盖真实的当前阶段进度。回合自动切分遥测 SHALL 从其 internal prerequisite job 投影到 public Parent。报告阶段 MUST 只能在前置分析和后处理阶段完成后开始。

#### Scenario: Parent 显示回合自动切分
- **WHEN** 用户轮询一个刚创建的正式双摄 Parent
- **THEN** Parent `stages` SHALL 将“回合自动切分”显示为 active 或 pending 的第一个阶段
- **AND** A/B 视觉分析、joint tracking、融合、指标、可视化和报告 SHALL 在切分成功前保持 pending

#### Scenario: 切分失败不显示后续进度
- **WHEN** formal segmentation prerequisite 以 model/input/sync/low-evidence 失败
- **THEN** Parent SHALL 将“回合自动切分”标记为 failed 并提供稳定用户原因
- **AND** 后续双摄阶段 SHALL 不得显示 active 或 done

#### Scenario: Parent 聚合阶段
- **WHEN** 前端轮询切分成功后的 multiview Parent 摘要
- **THEN** Parent `stages` SHALL 展示与 `executionMode` 对应的完整聚合阶段和真实顺序
- **AND** `viewRuns`（`cam_1` / `cam_2` 各自的 `status / stage / progress`）在有子运行时 SHALL 提供两路子进度，运行中也反映 child 或内部 `ViewRun` 的最近状态

#### Scenario: joint tracking 不显示报告先于协同跟踪
- **WHEN** `joint_tracking_v2` 的协同跟踪阶段上报进度 95
- **THEN** `multiview-joint` SHALL 为 active，指标、可视化和报告 SHALL 仍按图保持 pending
- **AND** 总体进度 SHALL 按 joint 阶段权重聚合，而不是按单摄阶段数量平均

#### Scenario: 报告生成是终末阶段
- **WHEN** 双摄任务进入报告生成
- **THEN** 只有在切分、融合或协同跟踪、指标重算和可视化输出完成后，报告阶段才 SHALL 变为 active
- **AND** 报告完成后总体进度 SHALL 为 100

## ADDED Requirements

### Requirement: 任务签名和执行记录绑定正式切分配置

需要正式回合切分的 Parent 输入签名 MUST 包含模型 package hash、decoder hash、required policy、CaptureTake 输入 fingerprint 和 sync calibration revision。Parent 与其 prerequisite job MUST 持久化 `segmentation_run_id`、`window_plan_hash`（成功后）及 prerequisite job reference，并在完成结果中暴露可复现但不泄露本地绝对路径的摘要。

#### Scenario: 模型版本变化创建新 Parent
- **WHEN** 同一 CaptureTake 以不同模型 package hash、decoder hash 或同步 revision 创建正式双摄任务
- **THEN** 系统 SHALL 视为不同分析输入
- **AND** SHALL 不复用旧 Parent 的成功结果或窗口计划

#### Scenario: 同配置重复提交
- **WHEN** 同一 CaptureTake 与相同切分配置重复提交，且未请求新版本
- **THEN** 系统 SHALL 复用或引用已有 queued、running 或 succeeded Parent
- **AND** SHALL 不额外创建重复 prerequisite job

### Requirement: prerequisite job 的恢复与取消

正式切分 prerequisite job SHALL 使用 durable Worker lifecycle。其 interrupted、failed、canceled 或成功状态 MUST 经 Coordinator 投影为 Parent 的稳定状态；重启 reconciliation MUST 不释放未成功切分的 late-fusion child，也不得重新发布已成功 run 的重复自动 Segment。

#### Scenario: prerequisite 在重启后中断
- **WHEN** 服务重启后 prerequisite job 的 heartbeat 已过期
- **THEN** Worker recovery SHALL 将该 prerequisite 标记为 interrupted
- **AND** Parent SHALL 进入明确 interrupted 或 failed 状态而不是无限等待

#### Scenario: 成功 prerequisite 重放
- **WHEN** 重启前 prerequisite 已成功发布 run 和 plan，但 Coordinator 尚未释放 Parent
- **THEN** reconciliation SHALL 使用已绑定的 run id 和 plan hash 推进 Parent
- **AND** SHALL 不重复创建 algorithm Segments 或 supersede 同一 run
