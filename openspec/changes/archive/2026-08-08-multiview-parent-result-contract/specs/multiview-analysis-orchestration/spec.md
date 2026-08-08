# multiview-analysis-orchestration Delta Specification

## ADDED Requirements

### Requirement: Parent 视频源自含

multiview Parent 的 `videoId`/`calibrationId` MUST 在创建时从 reference child 继承；对历史 Parent（`videoId` 缺失），读取时 MUST 从 reference child 虚拟解析（只读、不落盘），确保前端无论 result 是否落盘都能确定视频源。

#### Scenario: 创建时继承

- **WHEN** `create_multiview_job` 创建 Parent
- **THEN** Parent 的 `videoId`/`calibrationId` SHALL 等于 reference child 的对应字段

#### Scenario: 历史 Parent 虚拟解析

- **WHEN** 读取一个 `videoId` 缺失的 multiview Parent
- **THEN** 返回的 job summary SHALL 携带从 reference child 解析出的 `videoId`
- **AND** 该解析 SHALL 只读、不落盘（不改动持久化记录）
