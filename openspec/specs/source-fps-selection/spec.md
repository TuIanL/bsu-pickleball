## Requirements

### Requirement: 用户可选择或确认源视频 FPS
系统 SHALL 在上传视频创建分析任务和实时录制启动流程中提供源视频 FPS 选择能力，并 SHALL 将用户确认的 FPS 作为分析输入保存。

#### Scenario: 上传视频时选择 FPS
- **WHEN** 用户在上传分析页面选择本地视频并填写分析信息
- **THEN** 系统 SHALL 提供 FPS 选择控件，包含常用值 24、25、30、50、60、90、120 和自定义正数
- **AND** 创建分析任务请求 MUST 包含用户确认的源视频 FPS

#### Scenario: 录制视频预填 FPS
- **WHEN** 用户从已完成录制进入创建分析任务页面
- **THEN** 系统 SHALL 使用录制 session 中保存的 FPS 预填源视频 FPS
- **AND** 用户 SHALL 能在提交前修改该 FPS

#### Scenario: 用户覆盖 metadata FPS
- **WHEN** 视频 metadata FPS 与用户选择 FPS 不一致
- **THEN** 系统 MUST 使用用户选择 FPS 作为分析任务的源 FPS
- **AND** 后端诊断信息 MUST 记录 metadata FPS、用户选择 FPS 和 FPS 来源

### Requirement: 后端统一计算 effective FPS
系统 SHALL 在后端分析流水线中计算单一 `effective_fps`，所有时间戳、速度、帧窗口和渲染时间计算 MUST 使用该值。

#### Scenario: 用户 FPS 优先于 metadata
- **WHEN** 分析任务包含有效的用户确认 FPS，且视频 metadata 也包含有效 FPS
- **THEN** 后端 MUST 将用户确认 FPS 作为 `effective_fps`
- **AND** 后端 MUST 不在任何分析阶段改用 metadata FPS 进行时间敏感计算

#### Scenario: metadata FPS 作为 fallback
- **WHEN** 分析任务未提供用户确认 FPS，且视频 metadata 包含有效 FPS
- **THEN** 后端 MUST 将 metadata FPS 作为 `effective_fps`

#### Scenario: 安全默认 FPS
- **WHEN** 分析任务未提供用户确认 FPS，且后端无法读取有效 metadata FPS
- **THEN** 后端 MUST 使用 30fps 作为 `effective_fps`
- **AND** 结果诊断 MUST 标记 FPS 来源为 fallback

### Requirement: 时间窗口按真实 FPS 换算
系统 SHALL 将跟踪、身份、球检测、事件去重和可视化中的时间窗口表达为秒语义，并在运行时依据 `effective_fps` 换算为帧数。

#### Scenario: 不同 FPS 下真实时长一致
- **WHEN** 同一逻辑窗口配置为 2 秒，且任务分别以 30fps、60fps、90fps、120fps 运行
- **THEN** 后端 MUST 分别使用约 60、120、180、240 帧作为该窗口
- **AND** 该窗口代表的真实时间 MUST 保持约 2 秒

#### Scenario: 旧帧数配置兼容
- **WHEN** 部署环境仍使用旧的 frame-based 环境变量配置
- **THEN** 系统 SHALL 继续读取旧配置并转换为秒语义或运行时帧数
- **AND** 新的 seconds 配置存在时 MUST 优先使用 seconds 配置

### Requirement: FPS 元数据可追踪
系统 SHALL 在任务摘要、分析结果和相关 artifact source metadata 中记录有效 FPS 及其来源。

#### Scenario: 分析结果记录 FPS
- **WHEN** 分析任务完成
- **THEN** tracking、ball overlay、analysis artifacts 和报告可用 source metadata MUST 包含 `fps`
- **AND** 诊断信息 SHOULD 包含 `fps_source`、`metadata_fps` 和 `user_source_fps` 中可用的字段

#### Scenario: FPS 参与任务签名
- **WHEN** 同一视频和同一标定以不同用户确认 FPS 创建分析任务
- **THEN** 系统 MUST 将它们视为不同分析输入
- **AND** 任务去重或复跑机制 MUST 不复用 FPS 不同的旧结果
