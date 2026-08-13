# multiview-online-player-recovery Specification

## Purpose
TBD - created by archiving change make-p1-cross-view-player-recovery-operational. Update Purpose after archive.
## Requirements
### Requirement: 在线恢复证据链

`joint_tracking_v2` SHALL 仅在 target view 从自身当前 source frame 的真实像素中重新获得 formal local player observation 后，声明一次 online recovery。该 observation SHALL 可追溯 donor view、guidance、target source frame、local player identity 与 identity epoch、source track、pre-gate residual 与 assigned global player。

#### Scenario: 双向 controlled dropout 恢复
- **WHEN** 已 anchored 的 global player 在 Cam1 变 weak、Cam2 保持可信 base observation，且 Cam1 当前 frame available
- **THEN** 系统 SHALL 使用 Cam2 donor guidance 在 Cam1 的真实像素中恢复 formal local player observation
- **AND** 恢复前、中、后的 global player identity SHALL 保持一致

#### Scenario: 预测不构成恢复
- **WHEN** target ROI 未检测到或未接受真实 candidate
- **THEN** 系统 SHALL NOT 生成 target-view recovered observation
- **AND** SHALL NOT 将 prediction 或 guidance 计为 recovery

### Requirement: Recovery diagnostics 完整性

运行 diagnostics SHALL 记录 target weak、eligible opportunity、guidance generated、ROI invoked、candidate、pre-gate accepted、tracker admitted、local identity admitted 与 expected-global preserved 的漏斗，并按原因区分 donor、availability、pre-gate、lock 与 global assignment 失败。

#### Scenario: 可定位恢复失败
- **WHEN** 某 target view 没有产生恢复 observation
- **THEN** diagnostics SHALL 记录最早阻断阶段及结构化 reason
- **AND** target frame unavailable SHALL 与 source frame available 但无视觉 observation 区分

### Requirement: Recovery episode 与成功语义

系统 SHALL 在 target binding 首次进入 weak/lost 时建立 `recovery_episode_id`，直至 target 重新形成 formal observation。`recovery_opportunity` SHALL 要求 target frame available、weak/lost、global confirmed+anchored 与可接受 uncertainty；`guided_recovery_success` SHALL 要求真实 guided pixel evidence 经 pre-gate、surviving tracker、formal lock/local identity 后被分配到 expected global。same-tick base recovery SHALL 记录为 `base_recovered`，不得计入 guided success。

#### Scenario: same-tick base 优先
- **WHEN** pre-tick target binding weak，且该 tick 的 base 与 guided detection 都命中同一 target player
- **THEN** 系统 SHALL 保留 base evidence 并记录 `base_recovered`
- **AND** SHALL NOT 将该 episode 标记为 guided recovery success

