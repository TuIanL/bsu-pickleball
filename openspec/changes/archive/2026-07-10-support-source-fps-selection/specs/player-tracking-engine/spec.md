## ADDED Requirements

### Requirement: 球员跟踪依据 effective FPS 计算时间
球员跟踪引擎 SHALL 使用后端统一的 `effective_fps` 计算帧时间戳、跟踪缓冲、身份重连窗口、插值窗口和主球员选择窗口。

#### Scenario: 时间戳使用 effective FPS
- **WHEN** 分析任务的 `effective_fps` 为 60fps 且处理第 120 帧
- **THEN** tracking overlay 中该帧时间戳 MUST 为约 2.0 秒
- **AND** 后端 MUST NOT 使用 30fps 或 90fps 默认值计算该时间戳

#### Scenario: 身份缓冲按秒换算
- **WHEN** 身份跟踪丢失缓冲配置为 1 秒，且 `effective_fps` 为 90fps
- **THEN** PlayerIdentityManager 接收的丢失缓冲 MUST 为约 90 帧
- **AND** 相同配置在 30fps 下 MUST 为约 30 帧

#### Scenario: 主球员选择窗口按真实时长一致
- **WHEN** 主球员选择窗口配置为 1 秒，且任务分别以 30fps 和 120fps 运行
- **THEN** PrimaryPlayerSelector 的窗口帧数 MUST 分别约为 30 和 120
- **AND** 两者代表的真实时间窗口 MUST 一致
