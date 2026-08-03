## ADDED Requirements

### Requirement: 软接管产生的临时身份显示 canonical 标签

视频检测叠加层（`VideoAnalysisCard`）对经位置连续性软接管获得身份的检测框 SHALL 显示对应的 canonical player ID（如 `P1`），不得因置信度低而降级为 `person`。仅当检测框的 `player_id` 完全为空（软接管也不适用）时，标签 SHALL 显示中性文本（如 `person`）。

#### Scenario: 软接管身份的检测显示 canonical ID

- **WHEN** 一个检测框的 `player_id` 由身份层软接管（`tracking_status="tentative"`）指派为 `Player_2`
- **THEN** 框标签 SHALL 显示 `P2`（或等价 canonical 形式）
- **AND** SHALL NOT 因低置信度而显示 `person` 或原始 `track_id`

#### Scenario: 完全未关联的检测仍显示中性文本

- **WHEN** 一个检测框 `player_id` 为空，且位置连续性软接管不适用
- **THEN** 框标签 SHALL 显示中性文本（如 `person`）
- **AND** SHALL NOT 显示 `ID {track_id}` 形式的原始数字
