## ADDED Requirements

### Requirement: 统一比赛结构

系统 MUST 对新的单打和双打记分比赛统一采用五局三胜制，每局最高 21 分，任一方先赢得 3 局即赢得比赛。

#### Scenario: 一方取得第三局胜利
- **WHEN** A 方或 B 方赢得本场比赛中的第 3 局
- **THEN** 系统 SHALL 将 `match_status` 设为 `completed`
- **AND** 系统 SHALL 记录比赛胜方
- **AND** 系统 SHALL 拒绝继续开始新局或新分

#### Scenario: 比赛尚未决出
- **WHEN** 双方胜局均少于 3 且已完成局数少于 5
- **THEN** 系统 SHALL 将 `match_status` 保持为 `in_progress`
- **AND** 系统 SHALL 允许开始下一局

### Requirement: 21 分混合计分

系统 MUST 在每局 0:0 至进入 20:20 前采用每球得分制，并从 20:20 开始采用发球得分制；21 分为封顶分，不要求领先 2 分。

#### Scenario: 每球得分阶段发球方胜
- **WHEN** 当前比分不是 20:20
- **AND** 发球方赢得有效 rally
- **THEN** 系统 SHALL 为胜方增加 1 分
- **AND** 系统 SHALL 保持胜方为下一 rally 发球方

#### Scenario: 每球得分阶段接发方胜
- **WHEN** 当前比分不是 20:20
- **AND** 接发方赢得有效 rally
- **THEN** 系统 SHALL 为接发方增加 1 分
- **AND** 系统 SHALL 将接发方设为下一 rally 发球方

#### Scenario: 比分进入 20:20
- **WHEN** 一个有效 rally 使比分从 20:19 或 19:20 变为 20:20
- **THEN** 系统 SHALL 将 `scoring_phase` 设为 `serve_only`
- **AND** 下一 rally SHALL 按发球得分制处理

#### Scenario: 20:20 后发球方胜
- **WHEN** `scoring_phase` 为 `serve_only`
- **AND** 发球方赢得有效 rally
- **THEN** 系统 SHALL 为发球方增加 1 分至 21 分
- **AND** 系统 SHALL 立即判定发球方赢得本局

#### Scenario: 20:20 后接发方胜
- **WHEN** `scoring_phase` 为 `serve_only`
- **AND** 接发方赢得有效 rally
- **THEN** 系统 SHALL 不改变双方比分
- **AND** 系统 SHALL 将接发方设为下一 rally 发球方

### Requirement: 自动单局结束与胜局累计

系统 MUST 在一方合法达到 21 分时自动结束当前局、保存最终比分并且只累计一次胜局。

#### Scenario: 每球得分阶段以 21 分结束
- **WHEN** 一方在非 20:20 状态下通过有效 rally 从 20 分增加至 21 分
- **THEN** 系统 SHALL 自动关闭当前 game
- **AND** `game_end` 事件 SHALL 包含最终比分和胜方
- **AND** 胜方的 `games_won_a` 或 `games_won_b` SHALL 增加 1

#### Scenario: 已结束局不接受结果
- **WHEN** 当前 game 已结束且尚未开始下一 game
- **AND** 客户端提交 rally result action
- **THEN** 系统 SHALL 拒绝该 action
- **AND** 系统 SHALL 不重复累计胜局

### Requirement: 固定发球站位

系统 MUST 根据当前发球方自己的比分奇偶确定发球站位：奇数分为左区，偶数分（含 0 分）为右区；该规则同时适用于单打和双打。

#### Scenario: 奇数分发球站位
- **WHEN** 当前发球方的本队比分为奇数
- **THEN** 系统 SHALL 将 `serving_side` 派生为 `left`
- **AND** 单打 SHALL 表示该方从左区发球
- **AND** 双打 SHALL 表示该方左区队员发球

#### Scenario: 偶数分发球站位
- **WHEN** 当前发球方的本队比分为偶数或 0 分
- **THEN** 系统 SHALL 将 `serving_side` 派生为 `right`
- **AND** 单打 SHALL 表示该方从右区发球
- **AND** 双打 SHALL 表示该方右区队员发球

#### Scenario: 接发方取得发球权
- **WHEN** 接发方赢得 rally 并成为下一发球方
- **THEN** 系统 SHALL 使用新的发球方本队比分重新派生 `serving_side`

### Requirement: A/B 身份稳定

系统 MUST 在整场比赛中保持 A/B 身份、比分和胜局归属稳定，场地换边不得交换这些身份。

#### Scenario: 比赛中换边
- **WHEN** 用户执行 `change_side` action
- **THEN** 系统 SHALL 不改变 `score_a`、`score_b`、`games_won_a`、`games_won_b` 或 `server_team`
- **AND** 系统 SHALL 仅记录双方交换物理场地
