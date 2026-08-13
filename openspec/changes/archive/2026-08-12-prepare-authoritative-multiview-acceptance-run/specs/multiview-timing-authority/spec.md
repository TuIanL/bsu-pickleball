## ADDED Requirements

### Requirement: Historical registered video sidecar materialization

系统 SHALL 支持对已完成历史 CaptureTake 的最终 registered video 幂等生成 `<registered_video_path>.pts.jsonl`，并 SHALL 使用现有 PTS sidecar writer 提取 `best_effort_timestamp_time`。生成过程 SHALL 使用临时文件和原子替换，不得修改或覆盖原始 TS、registered video 或已有有效 sidecar。

#### Scenario: registered video 可生成 sidecar
- **WHEN** registered video 可读取且 ffprobe 返回非空、有限、单调的 frame PTS
- **THEN** 系统 SHALL 写入对应 sidecar
- **AND** sidecar SHALL 记录 frame index、PTS、可用 DTS 和 keyframe provenance

#### Scenario: sidecar 已存在且有效
- **WHEN** 对应 sidecar 已存在且 frame index/PTS 校验通过
- **THEN** 系统 SHALL 复用该 sidecar
- **AND** SHALL NOT 重复扫描或覆盖它

### Requirement: Sidecar authority persistence

sidecar 校验成功后，系统 SHALL 将 `source_pts`、sidecar path、frame count、FPS 和首尾 PTS provenance 关联到对应 CaptureTrack/registered video。sidecar 缺失、损坏或与 registered video 不匹配时，系统 SHALL 将 timing authority 保持为 `missing`/unavailable，并 SHALL 阻止 authoritative joint eligibility。

#### Scenario: sidecar 校验成功
- **WHEN** sidecar frame index 严格递增、PTS 单调不递减且至少包含一个有效 frame
- **THEN** CaptureTrack timing authority SHALL 为 `source_pts`
- **AND** provider SHALL 暴露 sidecar provenance

#### Scenario: sidecar 校验失败
- **WHEN** sidecar 为空、JSONL 损坏、PTS 非有限或不单调
- **THEN** 系统 SHALL 保留 media
- **AND** SHALL 记录结构化失败原因
- **AND** joint authoritative eligibility SHALL 为 false
