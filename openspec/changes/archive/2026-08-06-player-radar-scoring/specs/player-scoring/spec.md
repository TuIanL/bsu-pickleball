# player-scoring Specification

## Purpose

定义球员六维雷达评分面板的数据模型、后端契约与前端交互，确保评分以 canonical 球员身份为键、10 分制（1 位小数），且球员列表按分析结果自适应。

## ADDED Requirements

### Requirement: 系统定义球员六维评分数据模型

评分数据模型 SHALL 以 canonical player ID（`Player_1`..`Player_4`）为键，包含六个固定评分维度：发球（serve）、接发球（return_serve）、进攻能力（offense）、防守能力（defense）、敏捷（agility）、击球稳定性（shot_consistency）。每个维度评分 SHALL 取值 0–10、保留 1 位小数。评分数据源当前为 mock，但数据模型键 MUST 为 canonical player ID，为后续接入真实算法预留（不改键）。

#### Scenario: 评分按 canonical 球员键组织

- **WHEN** 前端读取球员评分数据
- **THEN** 评分以 `player_id`（`Player_1`..`Player_4`）为键组织
- **AND** 任意玩家的六维分值均可通过 canonical 键唯一索引

#### Scenario: 六维分值取值合法

- **WHEN** 读取某球员任意一维评分
- **THEN** 数值在 [0, 10] 区间
- **AND** 序列化为 1 位小数（如 `8.4`）

#### Scenario: mock 数据覆盖全部维度

- **WHEN** 使用内置 mock 评分数据
- **THEN** 每名球员含全部六个维度分值，无缺失维度

### Requirement: 视频分析页展示球员六维雷达评分面板

视频分析页（`VisionPage` jobId 视图）底部 SHALL 新增整行球员评分面板：左侧渲染六维雷达图，右侧提供球员切换 tab 与选中球员的六项分值列表。默认选中第一个球员。评分当前以 mock 填充，面板 SHALL 标注数据来源为演示数据。

#### Scenario: 面板出现在视频分析页底部

- **WHEN** 打开已完成分析的视频分析页
- **THEN** 页面底部出现整行球员评分面板，含雷达图与球员切换 tab

#### Scenario: 默认显示第一个球员

- **WHEN** 面板首次渲染
- **THEN** 雷达图与分值列表显示 roster 中第一个球员的六维评分

#### Scenario: 点击 tab 切换球员

- **WHEN** 用户点击某个球员 tab
- **THEN** 雷达图与分值列表切换为该球员的六维评分
- **AND** 该 tab 高亮为选中态

#### Scenario: 标注演示数据来源

- **WHEN** 面板使用 mock 评分数据
- **THEN** 面板 SHALL 显示"演示数据"类标注，不将 mock 分数呈现为真实分析结论

### Requirement: 球员评分面板按分析结果自适应球员列表

球员评分面板的 tab 列表 SHALL 按分析结果中实际检测到的 canonical 球员自适应生成：双打显示 4 人、单打显示 2 人，顺序为 canonical 自然序。当无真实分析结果（demo 或无轨迹数据）时 SHALL 兜底显示 4 个球员（或按 `match_context.expected_player_count` 决定 2/4）。

#### Scenario: 真实结果按检测球员显示

- **WHEN** 分析结果中存在 canonical 球员轨迹
- **THEN** tab 列表 SHALL 只包含结果中实际出现的球员（如单打 `Player_1`、`Player_2`）
- **AND** 顺序为 canonical 自然序（`Player_1` < `Player_2` < `Player_3` < `Player_4`）

#### Scenario: 无结果时兜底显示

- **WHEN** 无真实分析结果或轨迹数据缺失
- **THEN** 面板 SHALL 兜底显示 4 个球员（或按 `match_context.expected_player_count` 显示 2/4）

### Requirement: 雷达图以 10 分制渲染六维并保留 1 位小数

雷达图组件 SHALL 用 SVG 渲染六轴等角雷达：六轴分别对应六个评分维度，中心为 0、外缘为 10，环形网格指示分值刻度，顶点标注维度名称与分值。分值文本 SHALL 保留 1 位小数。选中球员的多边形 SHALL 使用该球员的 canonical 颜色填充。

#### Scenario: 渲染六轴雷达

- **WHEN** 渲染雷达图
- **THEN** 生成六轴等角网格，每轴标注对应维度中文名
- **AND** 网格刻度覆盖 0–10（如 0 / 2 / 4 / 6 / 8 / 10）

#### Scenario: 分值文本保留 1 位小数

- **WHEN** 某球员某维度分值为 8.4
- **THEN** 顶点分值文本 SHALL 显示 `8.4`

#### Scenario: 球员多边形使用 canonical 颜色

- **WHEN** 选中 `Player_2`
- **THEN** 雷达多边形使用 `Player_2` 的 canonical 颜色填充
