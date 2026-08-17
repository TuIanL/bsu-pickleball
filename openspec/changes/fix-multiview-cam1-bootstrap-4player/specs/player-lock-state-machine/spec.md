# player-lock-state-machine Delta

## ADDED Requirements

### Requirement: bootstrap 候选接纳以纵向可判为门槛（x 出界不拒绝）

bootstrap 阶段候选接纳 SHALL 以"bbox 存在 + 置信度达标 + court 纵向（y）可判"为必要条件；court 横向（x）超出 tracking bounds SHALL NOT 单独导致候选被拒绝。`_is_identity_candidate` 对 bootstrap 阶段的判定 SHALL 由 `is_inside_tracking_area` 硬门改为"纵向可判"（y 在球场纵深或可估计范围内），与 `bootstrap-slot-completeness` 能力一致。

#### Scenario: x 出界候选进入 bootstrap 收集

- **WHEN** 候选 bbox 非空、conf 0.5、court (31.3, 12.4)（x 超界、y 可判 near）
- **THEN** `_collect_bootstrap_observations` SHALL 收集该候选到对应 tracklet
- **AND** SHALL NOT 因 x 超界跳过

#### Scenario: 纵向死区候选仍被过滤

- **WHEN** 候选 court y 落在 SIDE_DEAD_ZONE（|y-22| < 2ft）或 court_position 缺失
- **THEN** 该候选 SHALL 仍不被接纳
- **AND** 保持既有过滤语义

### Requirement: 象限分配的图像位置松弛映射

bootstrap 象限归属 SHALL 以 court 投影为主；当投影 x 出界无法推断 left/right、但 y 可判 near/far 时，SHALL 用图像 bbox 中心 x（相对画面宽度 50% 分界）推断 left/right，完成 `near_left/near_right/far_left/far_right` 归属。该松弛映射 SHALL 仅用于 x 出界场景，MUST NOT 覆盖正常投影结果。

#### Scenario: 图像位置推断横向象限

- **WHEN** 候选 court (31.3, 12.4)、y 可判 near、x 出界
- **AND** 图像 bbox 中心 x = 1286（画面宽度 1920，> 50%）
- **THEN** 该候选 SHALL 归入 near_right 象限
- **AND** 可锁定 Player_2 槽位

#### Scenario: 正常投影优先

- **WHEN** 候选 court 投影 (6.8, 45.3)（x 在界内、y 可判 far）
- **THEN** 象限归属 SHALL 用 court 投影（far_left）
- **AND** 不使用图像位置松弛映射

### Requirement: bootstrap 结束后槽位完整性检查

bootstrap 窗口结束（达到 `bootstrap_max_frames`）时，系统 SHALL 记录各槽位锁定状态；存在 searching 槽位 SHALL 输出诊断事件（如 `event: "slot_unfilled"` + `identity_id` + `home_quadrant`），供 bootstrap 四槽位完整性观测。MUST NOT 因槽位空缺伪造锁定或替换已锁定槽位。

#### Scenario: 空槽位可观测

- **WHEN** bootstrap 结束时 Player_2（near_right）仍 searching
- **THEN** 系统 SHALL 记录 `event: "slot_unfilled"` 且 `identity_id=Player_2`
- **AND** Player_2 SHALL 保持 searching（不伪造锁定）

#### Scenario: 已锁定槽位不受影响

- **WHEN** bootstrap 结束时 Player_1/3/4 已 locked
- **THEN** 这些槽位 SHALL 保持锁定状态
- **AND** 不因完整性检查产生替换
