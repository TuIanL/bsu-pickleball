# multiview-analysis-input-contract Specification

## Purpose

定义多视角分析输入契约：sync authority、Canonical Timeline、pairing tolerance、`court_orientation` 声明与 Canonical Court Frame。本 Change 为该能力新增创建前置的 MultiView Preflight 校验：把"输入契约是否满足"从融合执行期提前到任务创建期，不满足时显式失败并告知用户原因，不静默退化。

## ADDED Requirements

### Requirement: MultiView 输入契约

MultiView 输入契约（sync authority / Canonical Timeline / pairing tolerance / `court_orientation` 声明 / Canonical Court Frame）MUST 保持 P0 冻结版本，本 Change 的任何新增校验（preflight）MUST NOT 修改其算法语义，MUST 仅在任务创建前追加前置校验。

#### Scenario: 契约语义不被改变

- **WHEN** preflight 或 Composer 引用输入契约
- **THEN** sync 门控 / orientation 声明 / Canonical Timeline 语义 SHALL 与 P0 一致
- **AND** 本 Change SHALL NOT 重定义任何已冻结契约

### Requirement: MultiView Preflight

系统 MUST 在创建双摄任务前校验输入契约是否满足：`CaptureTake completed` → `cam_1/cam_2 video available` → `cam_1/cam_2 calibration available` → `cam_1/cam_2 orientation declared` → `sync_calibration.json available` → 两机位属 P0 axis-preserving 范围。不满足时 MUST 返回结构化失败原因（含已解析 take_dir、期望 sync 路径、timeline 内容、生成命令）。

#### Scenario: 前置条件齐全

- **WHEN** 双摄任务的视频、标定、orientation、sync authority 全部可用且属 P0 支持范围
- **THEN** preflight SHALL 通过
- **AND** 允许创建 multiview Parent

#### Scenario: sync 不可用

- **WHEN** `sync_calibration.json` 不存在或其 sync 门控不可用
- **THEN** preflight SHALL 返回「双摄同步信息不可用」并附诊断细节（take_dir / 期望路径 / timeline 内容 / 生成命令）
- **AND** 前端 SHALL 提供「重新检查同步」「改用 A 机位单摄分析」等操作
- **AND** SHALL NOT 静默创建一个随后降级的假融合任务

#### Scenario: orientation 未声明

- **WHEN** 任一机位 `court_orientation` 未声明
- **THEN** preflight SHALL 判定不通过
- **AND** MUST NOT 按 `cam_2` 自动推断 `rotate_180`（沿用 P0 硬断言）

#### Scenario: 机位超出 P0 范围

- **WHEN** 任一机位不属于 P0 axis-preserving 支持范围（如 sideline / 轴交换标定）
- **THEN** preflight SHALL 判定不通过
- **AND** 按不支持处理，不得假装可融合
