## MODIFIED Requirements

### Requirement: 摄像头注册与管理

系统 MUST 支持注册网络摄像头，存储连接信息用于探测和录制；前端仍使用设备抽屉。所有配置写入 SHALL 以 Settings.resolved_cameras_dir 为唯一根目录，响应 SHALL 脱敏凭据。

#### Scenario: 注册新摄像头
- **WHEN** 用户提交合法 camera_id、name、stream_url、protocol 及可选认证字段到 `POST /api/cameras`
- **THEN** 系统 SHALL 将配置写入配置根目录内的 `{camera_id}.json`
- **AND** SHALL 返回含 created_at 的 CameraInfo，password 为掩码且 stream_url 不含 userinfo

#### Scenario: 查询所有摄像头
- **WHEN** 用户请求 `GET /api/cameras`
- **THEN** 系统 SHALL 返回配置目录内已登记摄像头的脱敏列表
- **AND** 内置虚拟测试摄像头 SHALL 保持既有可用且不可修改的语义，不读取任意工作目录中的其他配置

#### Scenario: 删除摄像头
- **WHEN** 用户请求删除已登记且未在录制的普通摄像头
- **THEN** 系统 SHALL 仅删除配置根内对应文件并返回 `{ deleted: true }`
- **AND** 正在单摄或双摄录制的摄像头 SHALL 返回 409，内置虚拟摄像头 SHALL 不允许删除

#### Scenario: 重复注册
- **WHEN** 用户提交已存在的 camera_id
- **THEN** 系统 SHALL 返回 409 且不覆盖既有内容，包括并发创建同名 ID 的情况

## ADDED Requirements

### Requirement: 摄像头文件路径边界

系统 MUST 在 schema 和存储服务边界拒绝路径型 ID，并在解析最终路径后验证目录归属；不得依靠前端验证或截断名称实现隔离。

#### Scenario: 非法 ID 不写盘
- **WHEN** 新增或改名请求包含空 ID、控制字符、路径分隔符、绝对路径或 `.`/`..`
- **THEN** API SHALL 返回 422，服务直接调用 SHALL 拒绝，文件系统 SHALL 无新增或修改

#### Scenario: 符号链接越界
- **WHEN** 配置根内的候选文件通过符号链接指向根目录外
- **THEN** 系统 SHALL 拒绝读取、覆盖或删除该目标

#### Scenario: 更换工作目录
- **WHEN** 从不同 cwd 启动且使用相同 cameras_dir 配置
- **THEN** 系统 SHALL 访问同一摄像头目录

### Requirement: 历史摄像头配置迁移

系统 SHALL 提供默认 dry-run、显式 apply 的幂等迁移，保留源文件和结果清单，不静默改写旧 ID 或关联引用。

#### Scenario: 迁移冲突
- **WHEN** 目标已存在相同 ID 但不同内容，或旧 ID 不安全
- **THEN** 系统 SHALL 记录冲突并跳过，不覆盖目标或自动改名

#### Scenario: 重复导入
- **WHEN** 相同合法配置被重复导入
- **THEN** 系统 SHALL 跳过已有相同内容，保留原 ID 和录制引用

### Requirement: 摄像头连接凭据完整脱敏

公开响应、错误信息和日志 SHALL 不包含 URL 中的用户名密码或独立密码；内部探测与录制 SHALL 保留认证能力。

#### Scenario: URL 内嵌认证
- **WHEN** 摄像头使用带 userinfo 的 RTSP/RTMP/HTTP URL
- **THEN** 返回和展示 URL SHALL 移除 userinfo，内部连接 SHALL 使用原始认证信息
