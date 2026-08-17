# bootstrap-slot-completeness Specification

## Purpose
确保 PlayerLockManager bootstrap 阶段在 4 人双打场景下完整锁定 4 个槽位（near_left/near_right/far_left/far_right）。根因修复：cam_1 第 4 名球员（远端右，conf 0.5）因脚点投影 x=31.3ft 超出 tracking bounds（x∈[-4,24]）被 `_is_identity_candidate` 直接拒绝，导致 Player_2 槽位全程 searching、cam_1 只有 3 个 binding。本能力定义"候选接纳放宽"与"四槽位完整性"约束。

## ADDED Requirements

### Requirement: 纵向可判即接纳（x 出界不拒绝）

bootstrap/reconnect 候选接纳 SHALL 以"图像证据 + 纵向可判"为必要条件：候选具备 bbox（bbox 非空）、清晰度达标（conf ≥ 状态门控）、且 court 纵向（y）可判 near/far（y 在球场纵深范围内或轻微出界可估计）时 SHALL 接纳为候选；court 横向（x）超出 tracking bounds SHALL NOT 单独导致拒绝。`_is_identity_candidate` SHALL 移除对 `is_inside_tracking_area` 的硬依赖（x 出界即 false），改为"纵向可判"判定。

#### Scenario: x 超界但纵向可判的第 4 人被接纳

- **WHEN** 候选 bbox 非空、conf 0.5、court 投影 (31.3, 12.4)（x 超 tracking 上界 24，y=12.4 可判 near）
- **THEN** 该候选 SHALL 被接纳为 bootstrap 候选
- **AND** SHALL NOT 因 x 超界被 `_is_identity_candidate` 拒绝

#### Scenario: 纵向不可判的场外人仍被拒绝

- **WHEN** 候选 court 投影 y 在球场纵向死区（|y - 22| < dead zone）或 bbox 缺失
- **THEN** 该候选 SHALL 仍被拒绝（不误纳场外裁判/观众）
- **AND** 拒绝原因 SHALL 可观测

### Requirement: bootstrap 四槽位完整锁定

bootstrap 阶段 SHALL 尝试锁定全部 4 个槽位。象限分配 SHALL 以 court 投影为主、图像位置（bbox 中心 x 相对画面）为松弛映射兜底：court 投影可判象限时用投影；投影 x 出界但 y 可判时，SHALL 用图像横向位置推断 left/right 完成象限归属。bootstrap 窗口结束时，4 个槽位中仍 searching 的 SHALL 继续尝试直到锁定或窗口结束，MUST NOT 因象限缺失而永久空槽。

#### Scenario: x 出界候选仍完成象限归属

- **WHEN** 候选 court (31.3, 12.4)（y=near 可判，x 出界无法判 left/right）
- **THEN** 系统 SHALL 用图像 bbox 中心 x（相对画面宽度）推断 left/right
- **AND** 该候选 SHALL 被分配到 near_left 或 near_right 槽位完成锁定

#### Scenario: 四槽位全锁定

- **WHEN** 4 名球员画面均清晰可见且纵向可判
- **THEN** bootstrap 结束后 Player_1..Player_4 槽位 SHALL 全部锁定（state=locked）
- **AND** 每个槽位 SHALL 绑定一个不同 track

### Requirement: 宁可空槽不误锁

bootstrap 四槽位完整性 SHALL 以"不误锁非球员"为硬约束：图像松弛映射 SHALL 只用于"纵向可判 + bbox 清晰"的候选；场外人员（court 投影 y 不可判、或 bbox 过小/置信度过低）SHALL NOT 被填入任何槽位。锁定槽位不可替换语义（既有 spec）SHALL 保持不变。

#### Scenario: 场外人不填充空槽

- **WHEN** 仅 3 名球员在场，另有一个裁判（court 投影 y 不可判或 bbox 极小）
- **THEN** 第 4 槽位 SHALL 保持 searching
- **AND** 裁判 SHALL NOT 被锁定到任何槽位

#### Scenario: 低置信度候选不填充空槽

- **WHEN** 空槽候选 conf < searching_conf
- **THEN** 该候选 SHALL NOT 被锁定
- **AND** 槽位 SHALL 保持 searching
