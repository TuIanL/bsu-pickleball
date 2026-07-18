# capture-runtime-status

## Purpose
管理实时录制工作台用于展示 CaptureTake 运行时状态（存储、录制、轨道、同步、指标可用性、安全边界）的快照接口，使前后端以一致、可校验的真实运行指标驱动录制工作台。

## Requirements

### Requirement: CaptureTake 运行状态快照

系统 MUST 提供 `GET /api/capture-takes/{capture_take_id}/runtime-status`，返回指定 CaptureTake 当前可用于录制工作台展示的存储、录制、轨道、同步和更新时间信息。

#### Scenario: 查询活跃单摄录制状态

- **WHEN** CaptureTake 状态为 `starting` 或 `recording`
- **THEN** API SHALL 返回当前录制状态、已录制时长、目标分辨率、目标帧率、当前文件大小、存储容量和单摄轨道状态

#### Scenario: 查询活跃双摄录制状态

- **WHEN** CaptureTake 为双摄模式且状态为 `starting` 或 `recording`
- **THEN** API SHALL 返回 cam_1 与 cam_2 的独立状态、文件大小、可用帧率测量、错误信息和同步摘要

#### Scenario: 查询终态录制

- **WHEN** CaptureTake 状态为 `completed`、`partial`、`failed` 或 `canceled`
- **THEN** API SHALL 返回最后可用的运行指标、终态和更新时间

### Requirement: 指标来源和可用性

运行状态 API MUST 为文件大小、码率、有效帧率、存储容量和轨道状态表达 `ready`、`collecting`、`unavailable` 或 `error` 等可用性状态，并不得把目标配置伪装成实测值。

#### Scenario: 有效帧率尚未测得

- **WHEN** 当前分片尚无有效帧率测量结果
- **THEN** API SHALL 返回 `collecting` 或 `unavailable`
- **AND** 不得将目标 fps 标记为 effective fps

#### Scenario: 无法读取会话文件

- **WHEN** 会话目录或活动分片暂时不可读
- **THEN** API SHALL 将相关文件指标标记为 `error`
- **AND** SHALL 返回可用于诊断的错误信息

### Requirement: 存储容量和文件大小

系统 MUST 基于当前录制实际使用的存储根目录返回总容量、已用容量、可用容量和当前 CaptureTake 文件大小，并 MUST 使用字节整数作为 API 原始单位。

#### Scenario: 正常读取存储容量

- **WHEN** 会话目录所在存储介质可访问
- **THEN** API SHALL 返回 `total_bytes`、`used_bytes`、`free_bytes`
- **AND** 文件大小 SHALL 汇总当前 Take 可见的已完成和活动分片

#### Scenario: 存储介质不可访问

- **WHEN** `shutil.disk_usage` 或会话目录读取失败
- **THEN** API SHALL 返回存储 `error` 状态和错误原因
- **AND** 不得切换到默认目录推断容量

### Requirement: 运行状态安全边界

运行状态 API MUST 只读取已由 CaptureTake 记录并校验过的会话目录和数据库关联分片，不得接受任意客户端路径作为查询目标。

#### Scenario: 使用合法 CaptureTake 查询

- **WHEN** 客户端提供存在的 CaptureTake ID
- **THEN** 系统 SHALL 根据数据库记录解析会话目录并返回状态

#### Scenario: 查询不存在的 CaptureTake

- **WHEN** 客户端提供不存在或无权访问的 CaptureTake ID
- **THEN** API SHALL 返回 404
- **AND** 不得读取客户端提供的任意文件路径
