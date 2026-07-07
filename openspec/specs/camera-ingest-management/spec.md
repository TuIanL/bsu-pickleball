# camera-ingest-management Specification

## Purpose
Define the camera ingest management capability — registering, listing, deleting network cameras and probing their online status for the recording pipeline.

## Requirements
### Requirement: 摄像头注册与管理

系统 MUST 支持注册网络摄像头，存储其连接信息用于后续探头检测和录制。

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

| 字段 | 类型 | 说明 |
|------|------|------|
| camera_id | string | 用户自定义唯一标识，如 `"baseline-cam"` |
| name | string | 摄像头展示名称 |
| stream_url | string | RTSP/RTMP/HTTP 流地址 |
| protocol | string | 协议类型：`rtsp` / `rtmp` / `http` |
| username | string | 认证用户名（可选） |
| password | string | 认证密码（可选，API 响应中脱敏为 `"***"`） |
| created_at | datetime | 注册时间 |
