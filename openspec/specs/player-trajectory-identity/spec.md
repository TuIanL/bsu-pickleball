# player-trajectory-identity Specification

## Purpose
Provide stable match-level player identities, metric-unit player trajectories, trajectory repair, and diagnostics for doubles pickleball analysis.
## Requirements
### Requirement: Stable doubles player identities
The backend SHALL assign target-court-eligible projected player observations to stable match-level `player_id` values for doubles analysis, distinct from detector observations and temporary tracker `track_id` values.

#### Scenario: Tracker emits fragmented IDs for four real players
- **WHEN** a doubles video produces more than four distinct source `track_id` values across the match
- **THEN** the final player trajectory artifact exposes no more than four stable `player_id` trajectories for target-court match metrics

#### Scenario: Source track history is preserved
- **WHEN** multiple source `track_id` values are assigned to the same real target-court player
- **THEN** the player state records current and historical source track IDs for diagnostics

#### Scenario: Existing track mapping is observed again
- **WHEN** an observation contains a `track_id` already bound to a `player_id` and remains target-court eligible or is within a configured reconnect grace period
- **THEN** the identity manager updates the existing player rather than creating a new player

#### Scenario: Neighbor court track is observed
- **WHEN** an observation belongs to a tracklet classified as non-target-court by the player selection layer
- **THEN** the identity manager does not create or update a final target-court `player_id` from that observation and records filtered diagnostics

### Requirement: Metric court coordinate identity matching
The backend SHALL use metric court coordinates as the canonical unit for player identity matching, speed filtering, interpolation, and final trajectory export.

#### Scenario: Final trajectory sample is exported
- **WHEN** a detected or interpolated player sample is written to the final trajectory artifact
- **THEN** the sample includes metric `court_x` and `court_y` values and artifact metadata declares `court_unit` as `m`

#### Scenario: Imperial dimensions are documented
- **WHEN** the final trajectory artifact includes court metadata
- **THEN** it includes standard pickleball dimensions as 13.41 m by 6.10 m and reference dimensions as 44 ft by 20 ft

#### Scenario: Existing projection uses feet during migration
- **WHEN** upstream projection output is expressed in feet
- **THEN** the identity layer converts coordinates to meters before applying distance, speed, interpolation, or boundary thresholds

### Requirement: Player state lifecycle
The backend SHALL maintain player states with `active`, `lost`, and `inactive` lifecycle statuses based on the last observed frame and configured frame buffers.

#### Scenario: Player is observed in current frame
- **WHEN** a player receives a detector-backed observation for the current frame
- **THEN** the player status is `active` and its last seen frame, position, velocity, and confidence are updated

#### Scenario: Player is temporarily missing
- **WHEN** a player has not been observed in the current frame but the gap is within the configured lost buffer
- **THEN** the player status is `lost` and the player remains eligible for reconnect assignment

#### Scenario: Player is missing beyond lost buffer
- **WHEN** a player has not been observed beyond the configured lost buffer
- **THEN** the player status becomes `inactive` while its trajectory history remains available

### Requirement: Track-to-player reconnect scoring
The backend SHALL score new or unbound track observations against existing players using target-court eligibility, metric court position, motion continuity, and optional appearance similarity when available.

#### Scenario: New track appears near predicted lost player
- **WHEN** an unbound source `track_id` appears near a lost player's predicted metric court position and is target-court eligible
- **THEN** the identity manager assigns the track to that player when the score meets the configured threshold

#### Scenario: Candidate assignment implies implausible speed
- **WHEN** assigning an observation to a player would exceed the configured maximum plausible player speed in meters per second
- **THEN** the identity manager rejects or downranks that assignment

#### Scenario: Four player identities already exist
- **WHEN** four player identities already exist and a new unbound target-court-eligible track appears
- **THEN** the system does not create a fifth player identity and instead assigns, drops, or records the track as unmatched diagnostics

#### Scenario: Unbound track lacks target-court eligibility
- **WHEN** an unbound source `track_id` has low target-court membership or is classified as a neighbor-court candidate
- **THEN** the identity manager rejects the assignment regardless of generic person confidence or movement level

### Requirement: Trajectory repair and sample status
The backend SHALL repair short missing intervals with interpolation and SHALL distinguish detector-backed samples from synthetic samples.

#### Scenario: Player reconnects after short gap
- **WHEN** the same player has detector-backed positions before and after a missing interval within the interpolation buffer
- **THEN** the backend fills the missing frames with interpolated metric court positions

#### Scenario: Interpolated point is exported
- **WHEN** a trajectory point is generated by interpolation
- **THEN** the exported sample sets `is_interpolated` to true and uses a `tracking_status` that is not `detected`

#### Scenario: Missing interval exceeds interpolation buffer
- **WHEN** a player is missing for longer than the configured interpolation buffer
- **THEN** the backend does not synthesize continuous trajectory points for that interval

### Requirement: Player trajectory artifacts
The backend SHALL export player-level trajectory artifacts that include JSON and CSV forms suitable for metrics, debug visualization, and manual review.

#### Scenario: JSON artifact is generated
- **WHEN** a real calibrated video analysis completes with player observations
- **THEN** the backend writes a JSON artifact containing video metadata, court unit metadata, player states, source track history, and per-player trajectory samples

#### Scenario: CSV artifact is generated
- **WHEN** a real calibrated video analysis completes with player observations
- **THEN** the backend writes a CSV artifact with frame, timestamp, player ID, source track ID, bbox, image footpoint, metric court coordinates, confidence, tracking status, and interpolation marker

#### Scenario: Metrics consume player identities
- **WHEN** player-level trajectory artifacts are available
- **THEN** movement metrics use stable `player_id` trajectories instead of raw temporary `track_id` fragments

### Requirement: Identity diagnostics
The backend SHALL expose diagnostics for identity assignment, reconnect, lost, inactive, and unmatched-track events.

#### Scenario: Track is assigned to player
- **WHEN** an unbound source track is assigned to a player
- **THEN** diagnostics record the frame, source `track_id`, target `player_id`, assignment score, and primary reason

#### Scenario: Player transitions to lost
- **WHEN** a player becomes lost
- **THEN** diagnostics record the transition frame and the player's last known metric court position

#### Scenario: Track cannot be assigned
- **WHEN** a source track fails assignment or is filtered as incidental
- **THEN** diagnostics preserve the decision without adding it to final player trajectories

### Requirement: Player trajectory 覆盖诊断

后端 SHALL 在 player trajectory identity 输出或分析阶段 counters 中提供轨迹覆盖诊断，使下游发球检测能够识别目标球员轨迹提前中断、身份失联或目标球场过滤过严。

#### Scenario: Player trajectory 覆盖完整视频
- **WHEN** 真实视频分析完成且稳定 player trajectory 覆盖接近完整源视频时长
- **THEN** trajectory artifact 或 diagnostics SHALL 暴露每个 `player_id` 的样本数量、最早时间、最晚时间、detected/interpolated 分布和源 track 历史摘要

#### Scenario: Player trajectory 提前中断
- **WHEN** tracking overlay 仍覆盖后续视频但所有或主要 player trajectory 的最后样本时间明显早于源视频结束时间
- **THEN** trajectory diagnostics SHALL 记录覆盖缺口、最后活跃时间、可能原因和被过滤或未匹配 track 的摘要

#### Scenario: 目标球场过滤导致无样本
- **WHEN** 后半段存在人体检测框但 primary-player selection 或 target-court eligibility 没有为 identity layer 提供合格 track
- **THEN** diagnostics SHALL 记录该时间段的过滤原因，以便发球检测和 UI 能报告输入链路不足

#### Scenario: 下游能力读取覆盖诊断
- **WHEN** 发球检测消费 player trajectory artifact
- **THEN** 它 SHALL 能读取或推导 trajectory 覆盖信息，并在覆盖不足时输出降级或诊断结果
