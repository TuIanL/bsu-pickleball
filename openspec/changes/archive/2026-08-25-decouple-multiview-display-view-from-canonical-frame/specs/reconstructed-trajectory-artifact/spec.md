# reconstructed-trajectory-artifact Delta

## ADDED Requirements

### Requirement: 多视角展示路径按 view 可审计

多视角重建产物用于视频展示的 image-space path SHALL 以 `view_id` 作为显式维度，并为每个 sample 保留 canonical timestamp、source frame index、source timestamp 和 provenance。缺少某 view 的 path SHALL 表示该 view 不具备该 sample 的视频展示资格，而不是允许前端猜测投影。

#### Scenario: 读取目标 view path

- **WHEN** 前端请求 `displayViewId=cam_2` 的球路展示
- **THEN** artifact 读取 SHALL 返回 `cam_2` 对应的 image-space samples
- **AND** samples SHALL 能与同一 canonical timestamp 的事件和 segment 对齐

#### Scenario: 目标 view 缺少 sample

- **WHEN**某 segment 只有 `cam_1` 的 image-space path
- **THEN** `cam_2` 的展示资格 SHALL 为 unavailable 或 degraded
- **AND** 前端 SHALL 不得使用 `cam_1` path 绘制在 `cam_2` 视频上
