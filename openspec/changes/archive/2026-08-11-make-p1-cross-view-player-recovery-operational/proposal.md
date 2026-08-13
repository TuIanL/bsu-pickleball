## Why

P1-0 已将双摄 canonical tick、每路 source frame 选择和 timing provenance 收敛为可验证的 authority contract，但现有 `joint_tracking_v2` 仍未形成真正的跨视角在线恢复闭环：guidance 单向、局部身份和 guided provenance 在 joint 边界丢失，且关联与几何约束存在可绕过路径。

现在需要把已经可信的时间对齐层接到一条可审计的 evidence chain 上，使一台摄像机的可靠真实观测能够帮助另一台摄像机重新从自己的像素中恢复同一位球员，同时保持 local/global identity 的连续性。

## What Changes

- 新增端到端的多视角在线球员恢复能力：`base donor -> guidance -> target-view real-pixel detection -> pre-gate -> tracker/lock/local identity -> global reassociation`。
- 将 cross-view guidance 改为双向、donor-aware、per-view geometry 的运行时契约；reference view 仅保留 canonical clock 与完整分析职责，不再拥有 donor 特权。
- 为 global binding 增加逐 tick aging、最后一份 view evidence 与严格 donor 选择；guided evidence 可参与测量和融合，但不得作为强 donor 或建立 cross-view anchor。
- 在 `joint_tracking_v2` 收紧 formal eligibility 为 lock-only，并让 joint observation 以 `view_id + player_id + identity_epoch` 保留稳定 local identity、精确 tracker assignment 与 guided provenance。
- 冻结 evidence-aware merge 的 base 优先级、overlapping guidance 的确定性决议，以及 episode-level guided recovery success 的判定语义。
- 修正 guided candidate 在 local/canonical 坐标间的 residual 边界，并使预门拒绝的候选绝不触碰 tracker。
- 将 global association 的 local identity/guidance prior 限制在 geometry hard gate 内，修复已有 mapping 复用和同 view bootstrap 的错误分组风险。
- 扩展 v2 artifact 与诊断漏斗，使每次恢复可追溯 donor、guidance、target source frame、local identity、track、残差和 global assignment；继续沿用 P1-0 timing eligibility/provenance。

## Capabilities

### New Capabilities

- `multiview-online-player-recovery`: 定义双向 online recovery evidence chain、恢复完成门和可审计诊断。

### Modified Capabilities

- `cross-view-player-guidance`: guidance 改为 donor-aware、双向且使用每路几何与 target-frame availability gate。
- `guided-player-redetection`: pre-gate 使用 target local court space，并将 accepted evidence/provenance 精确传递至 tracker assignment。
- `multiview-global-player-state`: binding 支持逐 tick aging、丰富 view evidence 与 base-only donor/anchor 规则。
- `multiview-player-association`: stable local identity 与 expected-global 只作为 geometry-feasible candidate 的 ranking prior，并禁止同 view bootstrap 合并。
- `view-tracking-session`: guidance 从占位契约改为 joint mode 的真实 guided detection；formal eligibility 按 mode 区分并输出 local identity evidence。
- `player-tracking-engine`: 在保持既有 `update()` 行为的前提下，增加 assignment-aware tracker 更新接口。
- `multiview-fusion-run`: `MultiViewJointRun` 使用 pre-tick snapshot、per-view geometry 和在线恢复 provenance；P0 `MultiViewFusionRun` 保持不变。

## Impact

- 主要影响 `backend/app/vision/multiview/`、`player_tracking_engine/`、`multiview_joint_executor.py` 及其 unit/integration fixtures。
- `fused_player_trajectory.v2` 仅新增 view-observation 字段与 diagnostics，不升级 artifact 主版本；历史 reader 保持兼容。
- `late_fusion_v1` 与单摄默认路径保持现有行为，offline refinement、视觉模型替换和最终 fusion weight 调整不在本 Change 范围内。
