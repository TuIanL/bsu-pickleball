## ADDED Requirements

### Requirement: GuidanceDecision 只读可观测

`GuidanceGenerator` SHALL 提供 side-effect-free 的 `GuidanceDecision` 只读记录（如 `last_decisions`），对每次未生成 guidance 的评估 SHALL 记录 `status`（`generated | not_eligible`）与结构化 `reason`（如 `target_not_missing / donor_unavailable / donor_low_quality / prediction_uncertain / cooldown / geometry_unavailable / not_confirmed_anchored`）。该 observability SHALL NOT 改变 `generate()` 的返回、触发语义或任何门限。

#### Scenario: 未生成 guidance 时原因可追溯

- **WHEN** 某 `(global_player, target_view)` 在 tick 未生成 guidance（binding 未 weak、或 donor 不可用、或 uncertainty 超限、或 cooldown 未过、或 geometry 缺失）
- **THEN** 系统 SHALL 记录 `GuidanceDecision(status=not_eligible, reason=<具体原因>)`
- **AND** guidance 生成逻辑与触发语义 SHALL 保持不变

#### Scenario: 生成 guidance 时状态确认

- **WHEN** 某 `(global_player, target_view)` 在 tick 成功生成 guidance
- **THEN** 系统 SHALL 记录 `GuidanceDecision(status=generated)` 及该 guidance 标识
- **AND** 该记录 SHALL 不影响 guidance 返回与消费

### Requirement: build_expected_player_region 共享纯函数

系统 SHALL 提供纯函数 `build_expected_player_region(predicted_position, uncertainty, target_geometry, policy)`，按 guidance 现有 ROI 计算规则（`base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，cap `max_roi_margin_px`）构建 expected player region。guidance 与 player display diagnostics SHALL 共用该函数，MUST NOT 各写一套固定半径的 expected region。

#### Scenario: guidance 与 diagnostics 共用同一 region

- **WHEN** 同一 `(predicted_position, uncertainty, target_geometry)` 输入
- **THEN** guidance ROI 与 diagnostics expected region SHALL 由同一纯函数产生一致的几何
- **AND** 不得出现 diagnostics 计数使用的 region 与 guidance 实际搜索 region 不一致
