# local-database-foundation Specification

## Purpose
Define the local SQLite database foundation for lightweight business metadata, state, and relationships while keeping videos and algorithm artifacts on the filesystem.
## Requirements
### Requirement: 本地 SQLite 数据库初始化

系统 MUST 提供本地 SQLite 数据库，用于保存业务元数据、状态和对象关系。

#### Scenario: 应用启动时初始化数据库
- **WHEN** 后端应用启动
- **THEN** 系统 SHALL 初始化 SQLite 连接
- **AND** 系统 SHALL 确保本 change 需要的数据表可用
- **AND** 初始化过程 SHALL 不删除已有视频、分析产物或摄像头配置文件

#### Scenario: 数据库文件不存在
- **WHEN** 配置的 SQLite 数据库文件不存在
- **THEN** 系统 SHALL 创建数据库文件及其父目录
- **AND** 系统 SHALL 创建 Field Session 所需数据结构

### Requirement: 数据库与文件系统存储边界

系统 MUST 使用数据库保存业务索引和关系，并继续使用文件系统保存大文件和算法产物。

#### Scenario: 保存业务元数据
- **WHEN** 系统创建或更新 Field Session
- **THEN** 系统 SHALL 将 Field Session 的业务字段、状态和时间戳保存到 SQLite

#### Scenario: 保留文件系统产物存储
- **WHEN** 系统保存录制视频、标定文件、分析 JSON、JSONL、图片或叠加视频
- **THEN** 系统 SHALL 继续将这些产物保存到文件系统
- **AND** 系统 SHALL 不把二进制视频或大型算法产物写入 SQLite

### Requirement: 测试数据库隔离

系统 MUST 支持在测试中使用隔离的临时 SQLite 数据库。

#### Scenario: 使用临时数据库运行测试
- **WHEN** 测试配置提供临时 SQLite 数据库路径
- **THEN** 系统 SHALL 使用该数据库执行 Field Session 相关测试
- **AND** 测试 SHALL 不读取或修改开发环境的正式数据库文件
