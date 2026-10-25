## ADDED Requirements

### Requirement: 三个创建入口使用统一分析模式

上传/已有视频、录制单机位和双摄 take 创建页 SHALL 提供完整比赛分析、球员检测、球检测、姿态分析和自定义组合。默认 SHALL 为完整比赛分析；专项可选项 MUST 同时满足后端 implemented 状态及前端已支持配置。planned 能力 MUST NOT 可提交。现有 new/legacy 流程选择 SHALL 仅属于完整分析分支。

#### Scenario: 模式与实际目标映射
- **WHEN** 用户选择球员检测、球检测或姿态分析预设
- **THEN** 请求 targets SHALL 分别为 `[player.detect]`、`[ball.detect]` 或 `[pose.sequence]`
- **AND** 自定义组合 SHALL 提交非空、去重的所选目标集合

#### Scenario: 后端能力未实现或目录不可用
- **WHEN** 能力为 planned、未知配置类型或目录读取失败
- **THEN** 页面 SHALL 禁止对应专项提交并解释原因，目录错误 SHALL 可重试
- **AND** 完整比赛分析 SHALL 保持可用，不以 mock 目录替代失败响应

#### Scenario: 切换模式不污染请求
- **WHEN** 用户从填写过标定/名册的完整分析切换到专项分析
- **THEN** 已上传视频 SHALL 复用，旧预览 SHALL 失效
- **AND** 模块请求 MUST NOT 携带无消费关系的 legacy 推理开关、名册、场景标定或回合配置

### Requirement: 专项表单按目标需要收集输入

首批专项分析 SHALL 只要求可用来源、时间范围、目标和采样；不要求球场/球网标定、名册或整场切分。双摄 SHALL 额外要求权威 PTS 和有效同步。缺省窗口 SHALL 为参考视频前 30 秒与其时长的较小值，并提供显式整段选择。采样步长缺省 SHALL 为 2，必须为正整数；窗口 SHALL 以整数毫秒提交并满足 `0 ≤ start < end ≤ duration`。

#### Scenario: 无标定创建姿态分析
- **WHEN** 用户提供有效单摄视频和姿态目标，未提供球场标定或名册
- **THEN** 页面 SHALL 允许完成准备和预览，显示后端自动加入的球员检测依赖
- **AND** 提交 MUST NOT 触发完整比赛分析或正式回合切分

#### Scenario: 非法窗口阻断提交
- **WHEN** 开始时间为负、结束时间不大于开始时间、超出参考视频时长，或采样不是正整数
- **THEN** 页面 SHALL 在字段附近显示原因并禁止预览和提交

#### Scenario: 默认与整段范围
- **WHEN** 读取到 12 秒或 90 秒视频并首次进入专项表单
- **THEN** 默认范围 SHALL 分别为 0–12 秒或 0–30 秒
- **AND** 选择“整个视频”后 SHALL 采用实际参考视频完整时长，不得自动扩大用户选定片段

#### Scenario: 双摄与选定单机位条件分离
- **WHEN** 用户选择双摄专项分析而权威同步不可用
- **THEN** 页面 SHALL 阻止创建并提供带完整返回上下文的同步工作台入口
- **AND** 用户在 A/B 单机位入口分析可用视频时 MUST NOT 被另一路或双摄同步阻断

### Requirement: 显式准备和计划预览

前端 SHALL 分别显示来源/环境准备、计划预览和创建任务状态。计划 SHALL 以后端响应为真源，展示请求目标、自动依赖、请求及有效窗口、采样、失败策略和缓存提示；技术详情展示后端可提供的实现及有效参数。缓存提示 MUST NOT 表示保证命中。默认 failure_policy SHALL 为 all_targets，高级选项可映射 best_effort 并解释部分结果。

#### Scenario: 无关模型缺失
- **WHEN** 模型准备返回姿态模型缺失，但用户仅选择 ball.detect 且所需球模型就绪
- **THEN** 页面 SHALL 继续球检测的预览流程，不因无关模型失败阻断

#### Scenario: 姿态依赖缺失
- **WHEN** 用户选择姿态分析，但人检测模型无法准备
- **THEN** 页面 SHALL 显示缺失的人检测依赖和可操作的错误提示，禁止创建
- **AND** MUST NOT 把已实现能力等同于当前环境可运行

#### Scenario: 预览不等于提交
- **WHEN** 用户完成计划预览但没有点击创建
- **THEN** 系统 MUST NOT 创建 Job、运行模型或生成观测产物

### Requirement: 预览失效和异步响应隔离

源视频、目标、时间范围、采样、失败策略、有效配置或同步版本变化 SHALL 使旧预览不可提交；旧请求响应 MUST NOT 覆盖更新后的状态。页面 SHALL 在准备、预览和提交期间禁止重复操作，失败后保留表单及已上传视频以便重试。

#### Scenario: 慢预览晚于表单修改返回
- **WHEN** 用户对视频 A 预览后切换到视频 B，A 的响应最后返回
- **THEN** 页面 SHALL 丢弃 A 的响应，不得使用 A 的计划激活 B 的提交按钮

#### Scenario: 跳转同步工作台后返回
- **WHEN** 用户通过嵌套 return 完成或取消同步校准
- **THEN** 页面 SHALL 恢复来源、模式及有效的目标/窗口/采样草稿
- **AND** SHALL 重新检查同步并预览，不使用离开前的计划直接提交

### Requirement: 模块提交与版本语义

Web 专项创建 SHALL 发送 `analysisEngine=modular_v1`、`modularRequest`、来源关联 metadata 和最新 `expectedPlanHash`。默认 SHALL 不创建强制新版本；返回已有 Job 时 SHALL 打开该 Job。显式新版本 SHALL 标注仍可能复用计算结果。失败时 MUST NOT 回退为 demo 或完整分析。

#### Scenario: 相同请求重复提交
- **WHEN** 用户普通创建同一语义计划或在网络错误后重试普通创建
- **THEN** 系统 SHALL 复用后端去重返回的 Job，并进入该任务，不重复上传来源

#### Scenario: 提交时预览已过期
- **WHEN** 后端返回 plan_preview_stale
- **THEN** 页面 SHALL 保留输入、撤销提交资格并要求重新预览，不自动接受变更后的执行计划

#### Scenario: 新版本提交响应丢失
- **WHEN** new_version=true 的请求发出后无法确定服务端是否创建成功
- **THEN** 前端 MUST NOT 自动重发，SHALL 提示结果待确认并查询素材任务历史供核对
- **AND** 未能确认时 SHALL 保留不确定状态，不宣称任务未创建

#### Scenario: 三个入口完成创建
- **WHEN** 上传、单摄录制或双摄 take 入口成功创建专项任务
- **THEN** 系统 SHALL 进入该 Job 的进度/模块结果路由，保留原素材 return
- **AND** 新上传无 return 时 SHALL 用上传后的稳定 videoId 建立 Library return
