## ADDED Requirements

### Requirement: 当前视角与 sync mapping 身份绑定

多视角 Parent 的每个 view input SHALL 持久化稳定的 camera identity。同步校验和 frame pairing SHALL 使用该 identity 匹配 mapping；系统 SHALL NOT 仅依据 `cam_1`/`cam_2` 槽位或唯一 non-reference mapping 猜测真实 camera。

#### Scenario: camera identity 精确匹配

- **WHEN** Parent 解析 secondary view 的 sync mapping
- **THEN** 系统 SHALL 以该 view input 的 camera identity 查找 mapping
- **AND** mapping 的 `camera_id` 与目标 identity 不一致时 SHALL 判定为不可用

### Requirement: canonical frame 进入多视角输入

多视角 Parent SHALL 持久化 `canonicalFrameId` 或等价的完整 canonical frame reference，并将其传递给对应的 `MultiViewFusionRun` 或 `MultiViewJointRun`。

#### Scenario: 输入可追溯 canonical frame

- **WHEN** 多视角任务被创建或重启恢复
- **THEN** Parent 和运行实体 SHALL 引用同一个 canonical frame id
- **AND** 该 id SHALL 出现在运行产物或 diagnostics 中
