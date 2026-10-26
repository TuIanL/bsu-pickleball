## ADDED Requirements

### Requirement: 模块任务展示用户目标与自动依赖

模块任务清单 SHALL 使用中文能力名称和状态，按 manifest.targets 区分用户目标与自动依赖，并显示分析片段与真实进度。实现标识、配置指纹、运行计数及 trace SHALL 放入技术详情；MUST NOT 通过 legacy 推理开关或全部 nodeRuns 推断用户选择。

#### Scenario: 姿态任务显示自动依赖
- **WHEN** targets 仅为 pose.sequence，nodes 包含 player.detect 和 pose.sequence
- **THEN** 页面 SHALL 标明姿态为请求目标、球员检测为自动加入步骤
- **AND** cached 节点 SHALL 显示已复用，不显示为重新推理

### Requirement: 模块结果完整性与质量分别展示

模块详情 SHALL 分别展示 Job 状态、complete/partial/none、节点状态、产物 quality 与 availability。执行完成 MUST NOT 等同于检测到对象或证据充分；partial 的可用产物 SHALL 保留查看入口。

#### Scenario: 没有候选观测
- **WHEN** 节点完成且产物 quality 为 no_candidates
- **THEN** 页面 SHALL 显示执行已完成但未检测到候选，不能伪造轨迹、稳定球员身份或报告

#### Scenario: 部分成功与上游阻断
- **WHEN** 独立球检测成功、人检测失败且姿态 blocked
- **THEN** 页面 SHALL 分别显示成功、失败和上游阻断，保留球观测查看入口
- **AND** SHALL 按 manifest 展示完整性，不把整个任务简化为全部有结果

#### Scenario: 证据不足或存储不可用
- **WHEN** 产物为 insufficient_evidence、truncated 或 availability 非 available
- **THEN** 页面 SHALL 显示对应质量/可读性原因，不以 completed 隐藏限制

### Requirement: 模块详情保留来源与按需读取

模块进度与结果页 SHALL 按 origin 提供正确返回文案和路径；active 时可请求取消，清单读取失败 SHALL 保留已知内容并提供重试。观测 payload 和 trace SHALL 在用户展开时读取，不作为进入页面的前置请求。

#### Scenario: 从比赛库进入后返回
- **WHEN** 模块路由携带 Library return
- **THEN** 返回控件 SHALL 显示“返回比赛详情”并回到该素材，完成不触发 legacy 报告加载

#### Scenario: 取消和读取失败
- **WHEN** 用户取消运行中的模块任务或某次清单/产物读取失败
- **THEN** 取消 SHALL 经后端确认状态更新，读取失败 SHALL 可重试且不清除已有节点结果

#### Scenario: 初次打开不读取大产物
- **WHEN** 用户打开模块详情且未展开观测/trace
- **THEN** 页面 SHALL 只加载所需任务和清单元数据，不下载观测 payload 或 trace
