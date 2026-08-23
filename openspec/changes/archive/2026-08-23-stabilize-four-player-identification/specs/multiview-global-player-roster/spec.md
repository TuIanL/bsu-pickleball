## ADDED Requirements

### Requirement: Roster 确认需要绑定完整性
双打 roster 进入 `ROSTER_ACTIVE` 前 SHALL 除占满四个 occupant 外，验证每个 occupant 的独立 source evidence、track/local/global 双射、side consistency 与稳定窗口。由同一 source track 或同一 reference local slot 派生的两个 occupant MUST NOT 同时确认。

#### Scenario: 四个 occupant 中两个共享 P1 local slot
- **WHEN** roster 表面占满 4 个 occupant，但两个 global 共享 reference `Player_1`
- **THEN** roster SHALL 保持 BOOTSTRAPPING/CONFLICTED
- **AND** SHALL NOT 发布 confirmed 四人映射

### Requirement: Canonical 映射受控冻结
roster confirmed 后 global→canonical mapping SHALL 冻结。普通漏检、local track replacement、identity epoch reset 或 projected evidence MUST NOT 重排映射；修复只能恢复原物理球员的 mapping，并记录 before/after、证据和原因。

#### Scenario: P2 一路漏检
- **WHEN** P2 在 reference view 暂时缺失但 donor view 仍可见
- **THEN** P2 canonical mapping SHALL 保持
- **AND** P1/P3/P4 编号 SHALL 不重新排序

