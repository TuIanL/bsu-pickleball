## ADDED Requirements

### Requirement: assignment-aware tracker update

`MultiObjectTracker` SHALL 提供兼容的 assignment-aware update，返回 tracks 以及本次输入 detection index 到 assigned track id 的精确映射。既有 `update(detections)` SHALL 保持原返回类型与行为，并可委托该新接口。

#### Scenario: 兼容 legacy update
- **WHEN** 既有单摄调用 `update(detections)`
- **THEN** 调用方 SHALL 获得与此前相同语义的 track list

#### Scenario: 获取 detection assignment
- **WHEN** joint session 使用 assignment-aware update
- **THEN** 系统 SHALL 能将 accepted guided detection 精确关联到其 assigned track id
