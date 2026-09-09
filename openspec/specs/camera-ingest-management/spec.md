# camera-ingest-management Specification

## Purpose
Define the camera ingest management capability — registering, listing, deleting network cameras and probing their online status for the recording pipeline.
## Requirements
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

### Requirement: 摄像头在线探测

系统 MUST 支持探测指定摄像头是否在线可访问。

#### Scenario: 探测在线摄像头
- **WHEN** 用户请求 `POST /api/cameras/{camera_id}/probe`
- **THEN** 系统使用 OpenCV `VideoCapture` 尝试打开摄像头流地址
- **AND** 如果在超时时间内（默认 10 秒）成功读取到一帧，返回 `online: true`
- **AND** 附带探测到的分辨率信息和延迟毫秒数
- **AND** 记录探测时间戳 `detected_at`

#### Scenario: 探测离线摄像头
- **WHEN** 摄像头流地址不可达或认证失败
- **THEN** 返回 `online: false`
- **AND** 附带错误原因描述 `error_message`
- **AND** `resolution` 和 `latency_ms` 字段为 `null`

#### Scenario: 探测超时
- **WHEN** 摄像头流地址响应过慢，超过 10 秒未返回帧
- **THEN** 返回 `online: false`
- **AND** `error_message` 提示超时

### Requirement: 摄像头模型定义

`CameraInfo` MUST 只存储连接信息，不包含球场语义。

#### Scenario: 摄像头模型不包含球场语义

- **WHEN** 后端序列化或读取一个 `CameraInfo`
- **THEN** 结果 SHALL 只包含摄像头连接、认证和创建时间字段
- **AND** 结果 MUST NOT 包含球场、球员或比赛位置字段

| 字段 | 类型 | 说明 |
|------|------|------|
| camera_id | string | 用户自定义唯一标识，如 `"baseline-cam"` |
| name | string | 摄像头展示名称 |
| stream_url | string | RTSP/RTMP/HTTP 流地址 |
| protocol | string | 协议类型：`rtsp` / `rtmp` / `http` |
| username | string | 认证用户名（可选） |
| password | string | 认证密码（可选，API 响应中脱敏为 `"***"`） |
| created_at | datetime | 注册时间 |

### Requirement: 摄像头前端展示改为设备抽屉

系统 SHALL 在采集控制台中将摄像头管理收入设备抽屉，主界面仅展示当前使用的摄像头状态。

#### Scenario: 控制台设备状态区
- **WHEN** 用户在采集控制台中查看设备状态
- **THEN** 系统仅展示当前采集方案使用的摄像头名称、在线状态和连接地址
- **AND** 提供「更换摄像头」按钮打开设备抽屉
- **AND** 不展示所有已注册摄像头的完整列表

#### Scenario: 设备抽屉管理全部摄像头
- **WHEN** 用户打开设备抽屉
- **THEN** 系统从右侧滑出面板，展示所有已注册摄像头列表
- **AND** 每项显示名称、ID、协议、探测状态和操作按钮（选择/探测/删除）
- **AND** 提供「注册新摄像头」入口
- **AND** 关闭抽屉不影响当前摄像头选择

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
