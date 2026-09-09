# match-state-dataset-audit Specification

## Purpose
TBD - created by archiving change learned-match-state-segmentation. Update Purpose after archive.
## Requirements
### Requirement: 双摄视频资产盘点

系统 SHALL 只读扫描指定数据根目录中的 7-20 视频及其标注，识别每个视频的 `capture_take`、机位、文件 fingerprint、FPS、时长、分辨率、可解码状态和双摄配对关系。

#### Scenario: 发现双摄视频对

- **WHEN** 两个视频通过 CaptureTake、camera slot、source session 或 manifest provenance 关联到同一场次
- **THEN** 审计报告 SHALL 将它们归入同一双摄样本，并记录每个机位的独立媒体信息和同步资产状态

#### Scenario: 视频缺失或无法解码

- **WHEN** 视频文件缺失、FPS 无效或完整解码失败
- **THEN** 系统 SHALL 将样本标记为 `excluded` 或 `insufficient_evidence`，记录具体原因，且不得生成看似有效的训练 clip

### Requirement: 标注覆盖与时间基准审计

系统 SHALL 校验人工回合标注的时间单位、范围、排序、重叠、闭合边界和与源视频时长的关系，并记录人工标注与视频 provenance 的来源。

#### Scenario: 标注时间合法

- **WHEN** 回合起止时间使用声明的时间单位、位于视频有效范围内且 `start < end`
- **THEN** 审计报告 SHALL 将其保留为可转换的粗标注，并记录对应 capture take、rally ID 和原始来源

#### Scenario: 标注存在冲突

- **WHEN** 回合重叠、缺少结束点、时间倒置或超出视频范围
- **THEN** 系统 SHALL 标记冲突类型和涉及的标注 ID，并禁止该标注直接生成高可信逐窗标签

### Requirement: 标注不确定区间生成

系统 SHALL 根据配置的边界缓冲策略，从人工粗标注生成高可信区间、边界不确定区间和不可训练区间；边界缓冲值 SHALL 记录在数据集 manifest 中。

#### Scenario: 生成回合内部高可信区间

- **WHEN** 粗标注回合长度大于两侧缓冲区之和
- **THEN** 系统 SHALL 将回合内部区间标记为 `rally_active` 高可信候选，并将起止附近缓冲区标记为 `uncertain`

#### Scenario: 回合过短无法安全裁剪

- **WHEN** 粗标注回合长度不足以去除两侧边界不确定区间
- **THEN** 系统 SHALL 将该回合标记为 `boundary_only` 或 `excluded`，且不得伪造高可信内部标签

### Requirement: 数据切分防泄漏

系统 SHALL 按完整比赛或源视频组划分 train、validation、test，并校验同一 source video、双摄配对、重复文件和同一 CaptureTake 不跨 split。

#### Scenario: 切分无泄漏

- **WHEN** 每个源视频组仅出现在一个 split
- **THEN** 系统 SHALL 生成带 split 版本和分组依据的 manifest

#### Scenario: 检测到跨集泄漏

- **WHEN** 同一源视频组或双摄配对出现在多个 split
- **THEN** 系统 SHALL 报告具体泄漏组，并将数据集状态标记为不可训练，直到切分被修正

### Requirement: 审计报告可复现

系统 SHALL 生成版本化的 `match_state_dataset_audit.v1` 报告，包含扫描配置、输入清单哈希、媒体统计、标注统计、排除原因、边界缓冲策略和构建时间。

#### Scenario: 重复审计结果一致

- **WHEN** 输入文件 fingerprint、标注版本和审计配置不变
- **THEN** 系统 SHALL 生成内容一致的样本计数、问题列表和数据集 manifest 哈希

### Requirement: 工作台支持补录漏记回合

系统 SHALL 允许用户在双摄边界复核工作台中，通过共享 take 播放头创建一条此前未被记录的 `rally`，并将创建过程写入可追溯的 segment 编辑审计记录。

#### Scenario: 创建不重叠的新回合

- **WHEN** 用户设置了完整且合法的开始、结束时间，且该区间不与现有 active rally 重叠
- **THEN** 系统 SHALL 创建一条 `active/closed/manual` rally，按 take 时间顺序分配 ordinal，初始复核状态为 `pending`，并保留 start/end 与创建操作 provenance

#### Scenario: 新回合与已有回合重叠

- **WHEN** 用户提交的新回合区间与现有 active rally 有时间重叠
- **THEN** 系统 SHALL 拒绝创建并明确提示冲突回合，不得生成重复 segment

#### Scenario: 新回合边界不完整

- **WHEN** 用户只设置了起点、只设置了终点或结束时间早于起点
- **THEN** 工作台 SHALL 保持新增草稿，不提交后端，并提示用户补全或修正边界

### Requirement: 工作台支持修正视频内 rally 序号

系统 SHALL 将单个 CaptureTake 视为一局比赛，允许用户在双摄边界复核工作台中按 take 时间顺序修正 active rally 的 ordinal；序号修正不得修改 rally 的原始或已复核起止边界。

#### Scenario: 从当前分开始连续编号

- **WHEN** 用户选中一个 rally，输入其真实起始序号并提交“从当前分开始连续编号”
- **THEN** 系统 SHALL 保留当前分之前的 rally ordinal，将当前分及后续 active rally 按时间依次编号，并同步更新系统默认的“第 N 分”标签

#### Scenario: 整段视频从第一分统一编号

- **WHEN** 用户提交“整段视频从第 1 分统一编号”
- **THEN** 系统 SHALL 按有效起始时间对该 CaptureTake 的 active rally 从 1 开始连续编号，并保留自定义标签与所有 rally 边界

#### Scenario: 序号修正可追溯

- **WHEN** 一次序号修正至少改变了一条 rally
- **THEN** 系统 SHALL 在 `segment_edit_operations` 中记录操作模式、起始序号、受影响 segment 和每条 ordinal/标签的前后值

#### Scenario: 异常边界回合可修复

- **WHEN** rally 的有效结束时间早于开始时间、结束时间缺失或不满足最短时长
- **THEN** 工作台 SHALL 允许用户选中该 rally、播放安全上下文并分步重新标定边界；在边界完整合法前 SHALL 保持待复核，不得提交为已确认或已修正
