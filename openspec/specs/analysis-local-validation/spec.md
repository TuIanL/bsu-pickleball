# analysis-local-validation Specification

## Purpose

定义 CLI 与 API 共用的局部计划、执行和检查入口，支持单摄及双摄短窗口验证，并分别记录合同测试、真实推理与算法质量证据。

## Requirements

### Requirement: CLI 与 API 使用同一规划和执行合同
系统 SHALL 提供共用的 plan、run、inspect 入口。CLI 与 API MUST 使用同一 Registry、Planner、规范化请求及 Executor；不得另写只供脚本使用的球/姿态完整分析链路。run SHALL 创建并通过既有 Worker 执行持久化 Job，inspect SHALL 支持 Job、计划、节点和 ArtifactRef。

#### Scenario: 两个入口得到相同计划
- **WHEN** CLI 与 API 使用相同来源、目标、实现、窗口、采样和配置
- **THEN** 它们 SHALL 产生相同 plan_hash
- **AND** SHALL 只在提交方式与展示方式上不同

### Requirement: 计划预览无推理副作用
plan/preview SHALL 只读取已登记的媒体、上下文、注册信息和产物索引；MUST NOT 打开 VideoCapture、初始化模型、写入计划/Job/产物或启动 Worker。缺少强身份或时间元数据 SHALL 返回待准备项，不得通过偷偷执行媒体准备来假装预览成功。元数据准备 SHALL 作为显式前置操作。

#### Scenario: 纯规划隔离
- **WHEN** 仅预览一个 ball.detect 的 30 秒窗口
- **THEN** 模型构造、视频打开和持久化写入次数 SHALL 均为零
- **AND** 预览 SHALL 返回依赖、有效窗口、资源需求、缓存提示及尚待准备项

### Requirement: 模块 API 不依赖固定报告响应
modular_v1 SHALL 提供计划预览、Job 提交、运行清单及产物读取的最小 API。模块结果 MUST 是可区分的 ModularRunManifest，包含计划、目标/节点、ArtifactRef、完整性和稳定诊断，不要求填充 legacy metrics、insights、report 或 143 个固定 artifact 字段。legacy 响应 SHALL 保持原 schema。

#### Scenario: 原始球检测结果
- **WHEN** 一个仅执行 ball.detect 的 Job 完成
- **THEN** 查询 SHALL 返回球检测 ArtifactRef 和节点状态
- **AND** SHALL 不调用默认产品完成回调生成指标或报告

#### Scenario: 清单路由不被动态路由吞掉
- **WHEN** 请求新增的固定清单读取路由
- **THEN** 路由 SHALL 在现有 artifacts/{artifact_name} 的 Literal 参数解析前正确匹配，或使用互不冲突的路径
- **AND** SHALL 不因 manifest 被当作旧 artifact_name 而返回 422

### Requirement: 首批三个能力有真实短窗口适配
v1 SHALL 在共用入口真实接入 player.detect、ball.detect、pose.sequence。pose.sequence 的选定实现 SHALL 消费可复用的人框及所需 RGB；不依赖球场标定、全局球员身份、球/回合/指标/报告。ball.detect SHALL 支持单摄和正式双摄时钟映射后的每机位原始二维观测，本期不承诺三维轨迹或 Shot 识别。

#### Scenario: 无标定的人框姿态
- **WHEN** 输入有效单摄短片与可用模型，但没有球场标定或名册
- **THEN** player.detect 和 pose.sequence SHALL 可以运行
- **AND** 姿态 SHALL 明确身份关联能力及坐标单位，不能制造稳定 Player_N

#### Scenario: 双摄局部球检测
- **WHEN** 提供两路源、有效 PTS/同步快照和局部窗口
- **THEN** ball.detect SHALL 按 CanonicalAnalysisClock 的映射生成两路观测和映射状态
- **AND** SHALL 不隐式调用 joint 人员跟踪、正式回合切分、三维重建或报告

### Requirement: 验收区分合同、真实推理和质量
交付 SHALL 分开记录纯合同 fixture、Worker 集成、真实单摄/双摄推理与算法质量证据。真实验收 MUST 记录媒体/模型身份、时间范围、命令、计划/产物、实际解码/推理计数及耗时；模型缺失、fixture 或空占位结果 MUST NOT 计为真实推理通过。

#### Scenario: 缓存和窄重算验收
- **WHEN** 对相同窗口重跑，再只改变姿态实现的有效参数
- **THEN** 第二次全命中 SHALL 不打开视频或执行模型
- **AND** 第三次 SHALL 复用未受影响的人框和球观测，只重算受影响的姿态及消费者

#### Scenario: 缺少真实模型
- **WHEN** 环境无法加载所需模型
- **THEN** 验收记录 SHALL 标明 model_environment 不可用及缺项
- **AND** SHALL 不以 mock 通过替代真实验收
