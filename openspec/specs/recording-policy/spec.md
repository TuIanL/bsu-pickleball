## ADDED Requirements

### Requirement: RecordingPolicy 可配置故障策略

系统 MUST 提供四种 RecordingPolicy：StrictSyncPolicy、PreservePrimaryPolicy、IndependentPolicy、SingleTrackRestartPolicy。策略对象实现 `decide(event, snapshot) -> list[CoordinatorAction]`。

#### Scenario: StrictSync 任一路失败全组重启

- **WHEN** 任一轨道 Fragment 意外退出
- **THEN** policy.decide() MUST 返回 [STOP_ALL, RESTART_ALL]
- **AND** 新的 rotation_index MUST 递增

#### Scenario: PreservePrimary 辅轨失败仅重启辅轨

- **WHEN** 辅轨（analysis_role=supplementary）Fragment 意外退出
- **THEN** policy.decide() MUST 返回 [RESTART_FAILED_TRACK]
- **AND** 主轨 MUST 继续录制不受影响
- **AND** rotation_index MUST NOT 递增

#### Scenario: PreservePrimary 主轨失败全组重启

- **WHEN** 主轨 Fragment 意外退出
- **THEN** policy.decide() MUST 返回 [STOP_ALL, RESTART_ALL]

#### Scenario: Independent 仅重启故障轨

- **WHEN** 任意轨道退出
- **THEN** policy.decide() MUST 返回 [RESTART_FAILED_TRACK]
- **AND** 不停止其他轨道

#### Scenario: 单轨退化为 SingleTrackRestartPolicy

- **WHEN** track_count == 1
- **THEN** 系统 MUST 统一解析为 SingleTrackRestartPolicy
- **AND** Three 策略 MUST 行为等价（仅重启当前轨）

#### Scenario: 重启预算

- **WHEN** 某轨 fragment 重启次数达到 max_restart_attempts（默认 5）
- **THEN** MUST 停止重试
- **AND** 退避序列 MUST 为 1s/2s/4s/8s/15s
