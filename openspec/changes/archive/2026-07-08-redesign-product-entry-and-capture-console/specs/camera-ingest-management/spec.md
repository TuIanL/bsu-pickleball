## MODIFIED Requirements

### Requirement: 摄像头注册与管理

系统 MUST 支持注册网络摄像头，存储其连接信息用于后续探头检测和录制。后端 API 不变，前端展示从主页面平铺改为设备抽屉面板。

#### Scenario: 注册新摄像头
- **WHEN** 用户提交 `POST /api/cameras`，包含 `camera_id`、`name`、`stream_url`、`protocol`、`username`、`password`
- **THEN** 系统将摄像头配置保存为 `data/cameras/{camera_id}.json`
- **AND** 返回 `CameraInfo` 对象，包含所有注册字段及 `created_at` 时间戳

#### Scenario: 查询所有摄像头
- **WHEN** 用户请求 `GET /api/cameras`
- **THEN** 返回所有已注册摄像头的 `CameraInfo` 列表
- **AND** 如果没有任何摄像头，返回空列表 `[]`

#### Scenario: 删除摄像头
- **WHEN** 用户请求 `DELETE /api/cameras/{camera_id}`
- **THEN** 删除对应的摄像头配置文件
- **AND** 返回 `{ deleted: true }`
- **AND** 如果摄像头正在录制中，返回 409 错误，不允许删除

#### Scenario: 重复注册
- **WHEN** 用户尝试注册已存在的 `camera_id`
- **THEN** 返回 409 错误，提示摄像头已存在，可先删除再重新注册

## ADDED Requirements

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
