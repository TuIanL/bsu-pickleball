## ADDED Requirements

### Requirement: local-space guided candidate evidence

guided candidate pre-gate SHALL 在 target local court space 比较 candidate projection 与 guidance `predicted_local_position`，并输出包含 guidance、expected global、donor、local position、residual、accepted/reject reason 的 evidence。reject candidate SHALL 永不进入 tracker。

#### Scenario: 非 identity orientation residual
- **WHEN** target view orientation 为 rotate_180、mirror_x 或 mirror_y
- **THEN** 正确 local candidate SHALL 按 local residual 通过 pre-gate
- **AND** 系统 SHALL 不将 local candidate 直接与 canonical prediction 比较

### Requirement: guided provenance 贯穿 tracker assignment

accepted guided detection 在 merge 后 SHALL 通过精确 detection-to-track assignment 关联到 track；由该 track 形成的 joint observation SHALL 保留 `guided_roi` origin、guidance id、expected global、donor 和 pre-gate residual。

#### Scenario: tracker 接住 guided candidate
- **WHEN** accepted guided detection 被 tracker 关联至 track
- **THEN** 该 track 的后续 joint evidence SHALL 使用该 candidate 的 provenance
- **AND** 系统 SHALL NOT 通过 bbox 相似度猜测来源

### Requirement: evidence-aware merge 与 surviving-track filtering

base/guided merge SHALL 消费 `DetectionEvidence` 而非裸 detection。base/guided 高 IoU 重合时 SHALL 保留 base，并将 guided 记为 `duplicate_of_base`；多个 guided evidence 重合时 SHALL 按 residual 升序、donor quality 降序、`guidance_id` 稳定顺序保留唯一项。assignment 后，只有 `DuplicateTrackSuppressor` 最终保留的 track evidence 才可形成 joint observation。

#### Scenario: base 与 guided 同 tick 重合
- **WHEN** base detection 与 guided detection 命中同一人且超过 dedup overlap 阈值
- **THEN** 系统 SHALL 保留 base evidence
- **AND** guided evidence SHALL 不计为 recovery success

#### Scenario: 两条 guidance 命中同一 candidate
- **WHEN** 两个重叠 ROI 产生同一人的 guided candidates
- **THEN** 系统 SHALL 确定性地仅保留一份 guided evidence
- **AND** 被丢弃 evidence 的 reason SHALL 可在 diagnostics 中追溯
