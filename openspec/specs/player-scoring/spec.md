# player-scoring Specification

## Purpose

定义球员六维雷达评分面板的数据模型、后端契约与前端交互，确保评分以 canonical 球员身份为键、10 分制（1 位小数），且球员列表按分析结果自适应。
## Requirements
### Requirement: 系统定义球员六维评分数据模型

评分数据模型 SHALL 以 canonical player ID（`Player_1`..`Player_4`）为键，包含六个固定评分维度：发球（serve）、接发球（return_serve）、进攻能力（offense）、防守能力（defense）、敏捷（agility）、击球稳定性（shot_consistency）。每个维度评分 SHALL 取值 0–10、保留 1 位小数。该旧模型可作为兼容类型保留，但 mock 数据 MUST NOT 在真实 job 的报告或数据分析页中冒充正式分析结论。

#### Scenario: 评分按 canonical 球员键组织

- **WHEN** 兼容代码读取球员评分数据
- **THEN** 评分以 `player_id`（`Player_1`..`Player_4`）为键组织
- **AND** 任意玩家的六维分值均可通过 canonical 键唯一索引

#### Scenario: 六维分值取值合法

- **WHEN** 读取某球员任意一维评分
- **THEN** 数值在 [0, 10] 区间
- **AND** 序列化为 1 位小数（如 `8.4`）

#### Scenario: mock 数据不得进入真实任务展示

- **WHEN** 当前任务为真实 job 且没有正式评分 artifact
- **THEN** 系统 SHALL 返回评分不可用状态
- **AND** MUST NOT 使用内置 mock 分值填充真实任务的用户界面

### Requirement: 报告页是评分的唯一用户界面承载位置

系统 SHALL 将评分相关用户界面集中在报告页的正式评分区域。数据分析页 SHALL 不再渲染旧的六维雷达评分面板；报告页 SHALL 使用现有 `PbSkillRatingSection` 作为评分入口，并在正式评分模型未生成时 fail-closed 显示不可用状态。

#### Scenario: 数据分析页不显示旧评分面板

- **WHEN** 用户打开带 jobId 的视频分析页
- **THEN** 页面 SHALL 不显示旧的六维雷达图、球员评分 tab 或 mock 分值列表
- **AND** 页面 SHALL 不因为删除评分面板而影响视频、球员轨迹和球路导航

#### Scenario: 报告页缺少正式评分模型

- **WHEN** 报告页对应真实 job 且没有正式 `player-skill-rating` artifact
- **THEN** `PbSkillRatingSection` SHALL 显示评分未生成的空态
- **AND** MUST NOT 显示旧模型或 mock 数值

#### Scenario: 报告页将来获得正式评分模型

- **WHEN** 报告页读取到通过契约校验的正式评分 artifact
- **THEN** 评分 SHALL 在 `PbSkillRatingSection` 中展示
- **AND** 数据分析页 SHALL 仍不恢复旧的独立评分面板

