## MODIFIED Requirements

### Requirement: 软接管产生的临时身份显示 canonical 标签

视频检测叠加层对经 lock hint 或位置连续性软接管获得身份的检测框 SHALL 显示对应的 canonical player ID（如 `P1`），不得因 `tentative` 或低置信度而降级为 `person`。仅当检测框在当前帧确实没有可证明的 `player_id` 时，标签 SHALL 显示中性文本。

#### Scenario: 软接管身份的检测显示 canonical ID

- **WHEN** 一个检测框的 `player_id` 由身份层软接管指派为 `Player_2`
- **THEN** 框标签 SHALL 显示 `P2`
- **AND** SHALL NOT 因 `tracking_status="tentative"` 显示 `person`

#### Scenario: lock hint 恢复身份的检测显示 canonical ID

- **WHEN** 一个新 track 由 lock hint 指派到 `Player_3`
- **THEN** 框标签 SHALL 显示 `P3`
- **AND** 标签 SHALL NOT 显示原始 `track_id`

#### Scenario: 完全未关联的检测仍显示中性文本

- **WHEN** 一个检测框 `player_id` 为空且 soft takeover 不适用
- **THEN** 框标签 SHALL 显示 `person`
- **AND** SHALL NOT 显示 `ID {track_id}` 形式的原始数字

## ADDED Requirements

### Requirement: 相邻 overlay 帧保持可证明的 canonical 身份

前端 overlay 帧解析在相邻帧之间插值时 SHALL 保留或继承可证明的 canonical player identity，但 SHALL NOT 根据不同 track 的空间距离自行猜测身份。

#### Scenario: 同一 track 的下一帧恢复身份

- **WHEN** 当前 overlay 帧的 detection 与下一 overlay 帧使用相同 `track_id`
- **AND** 当前帧 `player_id` 为空而下一帧为 `Player_1`
- **THEN** 插值后的当前渲染 detection SHALL 使用 `Player_1`
- **AND** 标签 SHALL 显示 `P1` 而不是 `person`

#### Scenario: 不同 track 不由前端猜测身份

- **WHEN** 当前帧和下一帧的 track_id 不同
- **AND** 后端没有为下一 track 提供 `player_id`
- **THEN** 前端 SHALL NOT 仅凭空间距离将其标为某个 P ID
- **AND** SHALL 保留中性标签或等待后端身份数据

#### Scenario: canonical ID 不泄漏 raw track_id

- **WHEN** overlay detection 同时包含 `player_id` 和 `track_id`
- **THEN** 用户可见标签 SHALL 只显示 `P1`..`P4`
- **AND** SHALL NOT 显示 raw `track_id`
