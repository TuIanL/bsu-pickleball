# project-delivery-quality-gates Specification

## Purpose
TBD - created by archiving change harden-project-reliability-and-delivery. Update Purpose after archive.
## Requirements
### Requirement: 依赖单一声明与可复现安装

后端 SHALL 以 backend/pyproject.toml 为依赖源，生成 requirements 和锁定结果，基础验证基线 SHALL 为 Python 3.11；可选视觉/姿态/训练环境 SHALL 独立说明，根元数据不得声明冲突要求。

#### Scenario: 干净基础安装
- **WHEN** 在没有个人缓存、媒体和权重的 CI 环境按文档安装
- **THEN** 包安装与生成的 requirements 安装 SHALL 均包含正式入口依赖并能导入 API、运行基础测试
- **AND** 重建 SHALL 使用提交的锁定结果，文档 SHALL 记录解释器和平台

### Requirement: 隔离且可执行的质量门禁

CI SHALL 执行 npm ci/build/test/lint、完整基础 pytest 和 OpenSpec 校验；所有测试写入 SHALL 在隔离目录内，模型/硬件验证 SHALL 与基础测试明确分离。

#### Scenario: 两种后端测试入口
- **WHEN** 从根目录运行规范后端命令或在 backend 运行 `python -m pytest -q`
- **THEN** 两者 SHALL 收集同一基础测试集，不出现 scripts 导入冲突或通过忽略失败测试获得通过

#### Scenario: 单例与硬编码目录隔离
- **WHEN** 完整测试套件结束
- **THEN** 上传、摄像头、候选、业务数据库、控制面与静态测试帧 SHALL 均只访问临时目录，真实运行目录 SHALL 无测试新增或修改

#### Scenario: 跟踪回归门禁
- **WHEN** 运行 lock_only 的正式检测与候选检测互斥测试
- **THEN** 测试替身 SHALL 满足 slots 等真实契约，测试 SHALL 执行业务互斥断言而不因替身 AttributeError 中止

### Requirement: 首屏资源预算

生产构建 SHALL 统计 landing 入口及其全部静态依赖 JS 的 gzip 字节数，合计 MUST 不超过 350 KiB，CSS 单独报告，source map 不计；动态 chunk 大小也 SHALL 记录。

#### Scenario: 首屏超出预算
- **WHEN** 初始静态 JS 合计超过预算
- **THEN** 构建质量检查 SHALL 失败，单纯重命名或拆分静态 chunk SHALL 不规避检查

### Requirement: 能力与验收证据一致

README、后端说明与技术成果说明 SHALL 区分已运行能力、实验能力、模拟演示和规划；真实失败不得变成 demo 成功，测试通过不得作为算法准确率证明。

#### Scenario: 硬件和实验能力说明
- **WHEN** 用户读取产品入口文案、README 或硬件页
- **THEN** 硬件 SHALL 明确为模拟或规划且不计入实际交付，球路/状态模型 SHALL 按可用证据说明实验边界

#### Scenario: 未具备真实验收环境
- **WHEN** 本次无法执行真实摄像头或模型推理验收
- **THEN** 验收记录 SHALL 明确写未验证及所缺条件，不写为通过
