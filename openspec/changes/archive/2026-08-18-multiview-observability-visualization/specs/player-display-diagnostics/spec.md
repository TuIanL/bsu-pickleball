# player-display-diagnostics Delta Specification

## ADDED Requirements

### Requirement: 全时间范围序列获取

display-diagnostics 查询 SHALL 支持为前端热力图提供跨窗口的时间序列数据。客户端 SHALL 以分段窗口（如 `window_ms=2000`）多次调用现有 `timestamp_ms + window_ms` 查询并本地拼接为 `(stage × tick)` 矩阵；服务端 SHALL 对 `window_ms` 不设低于 2000ms 的硬限制，或在超限时返回结构化 `partial` 与 reason，MUST NOT 报错或伪造缺失行。

#### Scenario: 分段拉取拼接

- **WHEN** 前端以 `window_ms=2000` 从 `timestamp_ms=0` 开始逐段查询某球员显示诊断
- **THEN** 前端 SHALL 按 canonical tick 升序拼接各段结果
- **AND** 拼接矩阵 SHALL 覆盖视频全时长，缺失段以"未触发"占位且不伪造行

#### Scenario: 大窗口请求

- **WHEN** 客户端请求 `window_ms=10000` 或更大窗口
- **THEN** 服务端 SHALL 返回窗口内全部漏斗行（受现有产物存在性约束）
- **AND** 若服务端存在窗口上限，SHALL 返回结构化 `partial` 与 reason 而非 500

#### Scenario: 球员切换重取

- **WHEN** 热力图切换球员
- **THEN** 前端 SHALL 以新 `player_id` 重新分段拉取
- **AND** 旧球员热力图 SHALL 被替换，不残留旧数据
