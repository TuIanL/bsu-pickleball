# multiview-court-frame-normalization Specification

## Purpose

定义两级球场坐标系（Local Camera Court Frame 与 Canonical Physical Court Frame）、`court_orientation` 声明契约、`CanonicalCourtFrameDefinition` 持久化与 Canonical Court Normalizer，保证多视角分析的所有坐标比较都发生在同一物理球场坐标系内。P0 仅支持 axis-preserving（保轴）标定视角。

## ADDED Requirements

### Requirement: 两级球场坐标系

系统 MUST 区分两种球场坐标系：**Legacy / Local Camera Court Frame**（现有单视角体系沿用，语义为 `local y=0 = image-top / camera-far end`、`local y=44 = image-bottom / camera-near end`）与 **Canonical Physical Court Frame**（Fusion 层专用，端点使用物理命名 `end_a`（canonical y=0）/ `end_b`（canonical y=44），边线使用 `sideline_a`（canonical x=0）/ `sideline_b`（canonical x=20））。Canonical 帧 MUST NOT 使用 `near/far` 作为端点名称。

#### Scenario: Local 帧语义限定

- **WHEN** 系统描述或记录现有单视角坐标
- **THEN** 系统 SHALL 将 `local y=0` 明确解释为 image-top / camera-far end，`local y=44` 解释为 image-bottom / camera-near end
- **AND** 系统 SHALL NOT 修改或重解释历史单视角 artifact 的坐标含义

#### Scenario: Canonical 帧物理命名

- **WHEN** 系统在 Fusion 层命名球场端点
- **THEN** 系统 SHALL 使用 `end_a / end_b` 与 `sideline_a / sideline_b` 等物理命名
- **AND** 系统 SHALL NOT 使用 `near/far` 作为 canonical 端点名称

### Requirement: CanonicalCourtFrameDefinition 持久化

系统 MUST 将每个 take 的 canonical 帧定义持久化为独立记录 `CanonicalCourtFrameDefinition`（含 `frame_id / capture_take_id / end_a_definition / end_b_definition / created_at / schema_version`）。同一 take 的多次分析 MUST 引用同一 `frame_id`，MUST NOT 每次重新选定端点。

#### Scenario: 持久化定义

- **WHEN** 操作者首次为某 take 配置 canonical 帧
- **THEN** 系统 SHALL 持久化 `CanonicalCourtFrameDefinition`
- **AND** 后续分析 SHALL 复用该定义，不产生新的端点选择

#### Scenario: 禁止每次重选

- **WHEN** 同一 take 被多次分析
- **THEN** 各次分析 MUST 引用同一 `frame_id`
- **AND** 系统 SHALL NOT 因重跑而整体翻转 canonical 坐标

### Requirement: CourtOrientation 声明

每个参与多视角分析的 `MultiViewViewInput` MUST 携带可选 `court_orientation`，允许值 SHALL 为 `identity / rotate_180 / mirror_x / mirror_y`，分别对应 `(x,y)→(x,y)`、`(x,y)→(20-x, 44-y)`、`(x,y)→(20-x, y)`、`(x,y)→(x, 44-y)`。`court_orientation` MUST 表示该 view（CaptureTrack + Calibration）的 Local Camera Court Frame 到 Canonical Physical Court Frame 的仿射变换。未声明 MUST 使用 `None`，MUST NOT 引入第五种朝向值。

#### Scenario: 有效枚举值

- **WHEN** 系统校验 `court_orientation`
- **THEN** 仅 `identity / rotate_180 / mirror_x / mirror_y` 被接受
- **AND** 其他取值 SHALL 被拒绝

#### Scenario: 未声明语义

- **WHEN** 某 view 未提供 `court_orientation`
- **THEN** 其值 SHALL 为 `None`，语义为"尚未声明"
- **AND** 系统 SHALL NOT 将其解释为第五种朝向

#### Scenario: 变换语义

- **WHEN** 系统应用 `court_orientation = rotate_180`
- **THEN** canonical 坐标 SHALL 为 `(20 - x, 44 - y)`
- **AND** `mirror_x` / `mirror_y` SHALL 分别应用 `(20 - x, y)` / `(x, 44 - y)`
- **AND** `identity` SHALL 保持 `(x, y)` 不变

### Requirement: 支持范围限定为 axis-preserving

`court_orientation` 四元素契约 MUST 仅在 axis-preserving（保轴，local x/y 不交换）标定视角下成立。P0 支持范围 SHALL 限定为对向底线机位与底线类高位机位；任意 sideline 朝向或 local x/y 轴交换的标定 SHALL 视为不支持。

#### Scenario: 对向底线机位

- **WHEN** 两路为球场对向底线机位
- **THEN** 系统 SHALL 支持用 `court_orientation` 归一化
- **AND** 两路变换 SHALL 可用四元素之一表达

#### Scenario: 轴交换标定不支持

- **WHEN** 某 view 标定的 local x/y 轴发生交换
- **THEN** 系统 SHALL 视为不支持
- **AND** 该 view SHALL NOT 被纳入融合

### Requirement: Canonical Court Normalizer

Multi-view Fusion MUST 只消费经过 Canonical Court Normalizer 转换后的坐标。任一参与融合的 view `court_orientation` 为 `None` 时，系统 MUST 不将该 view 纳入融合，并按 job-level 单视角 fallback 处理。系统 MUST NOT 根据 `cam_2` 槽位自动推断 `rotate_180`。

#### Scenario: 未知朝向禁止融合

- **WHEN** 任一路 `court_orientation = None`
- **THEN** 系统 SHALL 禁止对该 view 执行多视角融合
- **AND** 系统 SHALL 使用该 view 的单视角轨迹作为 job-level fallback

#### Scenario: 禁止自动推断

- **WHEN** 多视角 run 缺少 `cam_2` 的 `court_orientation`
- **THEN** 系统 SHALL NOT 自动填入 `rotate_180`
- **AND** 该行为 SHALL 由自动化测试断言

#### Scenario: 归一化后比较

- **WHEN** 两路观测需在 Fusion 层比较
- **THEN** 系统 SHALL 先将各自 local 坐标经 `court_orientation` 变换为 canonical 坐标
- **AND** 比较与融合 SHALL 只基于 canonical 坐标
