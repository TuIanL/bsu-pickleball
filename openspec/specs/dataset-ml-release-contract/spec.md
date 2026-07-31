## ADDED Requirements

### Requirement: ML 标签 Profile 定义
系统 SHALL 通过 `model_label_profiles.yaml` 定义从 v3 源标注到不同训练任务标签的确定性映射规则。每个 Profile 声明其目标类型（flat_class / action_family / multitask）、类别列表和派生规则。

#### Scenario: 加载并校验 Profile 配置
- **WHEN** 系统启动时读取 `model_label_profiles.yaml`
- **THEN** 系统验证每个 Profile 的类别名称仅包含字母和下划线，且同一 Profile 内类别无重复

#### Scenario: 派生 action_family
- **WHEN** 源样本 `stroke_type` 为 `forehand_drive` 或 `backhand_drive`
- **THEN** 系统派生 `action_family` 为 `drive`，`stroke_side` 为 `forehand` 或 `backhand`

#### Scenario: 保留非融合标签的 stroke_type
- **WHEN** 源样本 `stroke_type` 为 `dink`、`volley`、`drop_shot`、`smash`、`lob`、`serve` 或 `other`
- **THEN** 系统将 `action_family` 设置为与 `stroke_type` 相同的值

#### Scenario: Profile 类别编号稳定性
- **WHEN** 对同一 `actions.v3.json` 重复执行 canonical 导出
- **THEN** 每个 Profile 的 class_id 分配顺序与 `model_label_profiles.yaml` 中声明的类别顺序一致

### Requirement: Canonical Manifest 生成
系统 SHALL 从 `actions.v3.json`、`video_meta`、provenance 和去重结果生成 `canonical_actions.jsonl`，每条记录同时保留源标签和派生标签。

#### Scenario: 基本记录结构
- **WHEN** 系统处理一条有效样本
- **THEN** 生成的 JSONL 记录包含 `sample_id`、`video`（含 fps/num_frames/duration/尺寸/decode_status）、`source_label`（原始 v3 标签）、`canonical_label`（派生 action_family/stroke_side/hand_usage）、`quality`、`provenance`、`dedup` 和 `eligibility` 字段

#### Scenario: 可重复生成
- **WHEN** 对同一版本的 `actions.v3.json` 和相同配置重复执行生成
- **THEN** 输出的 `canonical_actions.jsonl` 逐字节一致，SHA-256 哈希相同

#### Scenario: unknown side 样本的 eligibility
- **WHEN** 源样本 `stroke_side` 为 `unknown`
- **THEN** `eligibility.stroke_side_head` 设为 `masked`，`eligibility.action_family8` 和 `eligibility.legacy_full9` 仍为 `eligible`

#### Scenario: skipped 样本排除
- **WHEN** 样本在 `actions.skipped.json` 中
- **THEN** 该样本不出现在 `canonical_actions.jsonl` 中，但在审计报告中单独计数

#### Scenario: label_confidence=medium 样本标记
- **WHEN** 样本 `annotation.label_confidence` 为 `medium`
- **THEN** 该样本仍进入 `canonical_actions.jsonl`，但 `quality.review_status` 设为 `needs_review`，并出现在 `views/review_ids.txt` 中

### Requirement: 视频完整解码验证
系统 SHALL 对每个训练视频执行完整解码验证，不仅依赖容器元数据。

#### Scenario: 视频解码通过
- **WHEN** `ffmpeg -v error -i <video> -f null -` 返回零退出码且解码帧数与 `num_frames` 偏差在 ±2 帧以内
- **THEN** 系统记录 `decode_status: "passed"`

#### Scenario: 视频文件缺失
- **WHEN** `relative_video_path` 在 `--video-root` 下不存在
- **THEN** 系统记录 `decode_status: "missing_file"`，样本在 `canonical_actions.jsonl` 中保留但所有 eligibility 设为 `excluded`

#### Scenario: 视频解码错误
- **WHEN** ffmpeg 返回非零退出码或输出包含 error 级别日志
- **THEN** 系统记录 `decode_status: "decode_error"`，样本所有 eligibility 设为 `excluded`

#### Scenario: 解码帧数不匹配
- **WHEN** 解码帧数与 `num_frames` 偏差超过 ±2 帧
- **THEN** 系统记录 `decode_status: "frame_count_mismatch"` 并记录实际解码帧数

#### Scenario: 解码时长偏差
- **WHEN** 实际解码时长与 `duration_ms` 偏差超过 5%
- **THEN** 系统记录 `decode_status: "duration_mismatch"` 但样本仍可训练（仅发出 warning）

### Requirement: 内容级重复检测
系统 SHALL 对视频执行三层重复检测，区分完全重复、转码副本、同源片段和非重复。

#### Scenario: SHA-256 完全一致
- **WHEN** 两个视频文件 SHA-256 哈希完全相同
- **THEN** 系统将它们归入同一 `exact_duplicate` 组，仅保留一个作为训练主样本，其余在主样本的 `dedup.exact_duplicate_group` 中标记

#### Scenario: 感知哈希检测转码副本
- **WHEN** 两个视频在采样帧位置的感知哈希向量相似度超过阈值
- **THEN** 系统将它们标记为候选 `probable_reencoded_duplicate`，并进入第三层 SSIM 复核

#### Scenario: SSIM 复核确认转码副本
- **WHEN** 候选组对应位置帧的 SSIM > 0.95
- **THEN** 系统确认为 `probable_reencoded_duplicate`，确保它们进入同一 split

#### Scenario: 不将背景相似的视频误判为重复
- **WHEN** 两个视频来自不同动作但拍摄于同一球场
- **THEN** 帧序列感知哈希比较应能区分（至少 2/5 采样帧差异显著），不被误判为重复

#### Scenario: sample_id 已通过 source_video_id 分组
- **WHEN** 两个样本共享同一 `source_video_id`
- **THEN** 它们不触发重复检测（已知是同源不同裁剪），仅依赖 source_video_id 防泄漏

### Requirement: Split 完整性校验
系统 SHALL 对现有 `baseline4` 和 `full9` splits 执行完整性校验。

#### Scenario: source_video_id 不跨集
- **WHEN** 同一 `source_video_id` 下的样本出现在 train + val、train + test 或 val + test 中
- **THEN** 系统报告跨集泄漏，列出泄漏的 source_video_id 和涉及的 split

#### Scenario: 重复文件不跨集
- **WHEN** `exact_duplicate` 或 `probable_reencoded_duplicate` 组中的样本分布在多个 split 中
- **THEN** 系统报告重复泄漏，建议将其全部归入同一 split

#### Scenario: skipped 样本不出现在 split 中
- **WHEN** split 文件中包含 `actions.skipped.json` 中的 sample_id
- **THEN** 系统报告 skipped 样本泄漏

#### Scenario: 未知 sample_id
- **WHEN** split 文件中包含不存在于 `actions.v3.json` 的 sample_id
- **THEN** 系统报告未知样本，列出具体 ID

#### Scenario: 重复 sample_id
- **WHEN** 同一 sample_id 出现在两个或更多 split 文件中
- **THEN** 系统报告重复分配

#### Scenario: Split 校验通过后继续使用
- **WHEN** 所有校验项通过
- **THEN** 系统直接使用现有 split 文件，不生成新版本

#### Scenario: Split 校验失败时生成版本化替代
- **WHEN** 任意校验项失败
- **THEN** 系统生成 `baseline4_v2_*.txt` 或 `full9_v2_*.txt`，保留旧版文件，并在审计报告中记录差异

### Requirement: 审计报告生成
系统 SHALL 生成完整数量核算审计报告，确保从 1084 条原始记录到各 Profile 可训练样本可完整追溯。

#### Scenario: 完整数量等式
- **WHEN** 系统生成审计报告
- **THEN** 报告包含从总记录数 → active → skipped → 各 Profile eligible 的完整层级分解，各层级数量可互相核算

#### Scenario: 类别分布统计
- **WHEN** 系统统计每个 action_family 的样本数
- **THEN** 报告列出每个类别的总数、good/medium 比例、正反手分布、平均时长和帧数分布

#### Scenario: 媒体统计
- **WHEN** 系统汇总视频媒体参数
- **THEN** 报告包含分辨率分布、FPS 分布、时长分布、编码格式分布

#### Scenario: 数据问题汇总
- **WHEN** 系统完成全部校验
- **THEN** 报告列出缺失视频、解码错误、重复 ID、中置信度样本、疑似重复组、source_video_id 和 split 泄漏

### Requirement: 不可变发布包生成
系统 SHALL 生成 `releases/v3.1.0/` 不可变发布包，包含 canonical manifest、Schema、splits、审计报告和校验和。

#### Scenario: 发布包目录结构
- **WHEN** 系统执行 `build_dataset_release.py`
- **THEN** 输出目录包含 `canonical_actions.jsonl`、`release_manifest.json`、`checksums.sha256`、`schemas/`、`splits/`、`views/` 和 `reports/` 子目录

#### Scenario: release_manifest.json 内容
- **WHEN** 系统生成发布清单
- **THEN** `release_manifest.json` 包含 `dataset_version: "3.1.0"`、`parent_version: "3.0.0"`、`sample_count`、`annotation_sha256`、`canonical_manifest_sha256`、`label_schema_sha256`、各 split 文件的 SHA-256、构建命令和 `created_at` 时间戳

#### Scenario: 训练代码只消费发布包
- **WHEN** 下游训练代码加载数据集
- **THEN** 训练代码只从 `releases/v3.1.0/` 读取，不直接访问 `annotations/`、`actions.v3.json` 或工作目录中的其他文件

#### Scenario: 发布包不可变
- **WHEN** `releases/v3.1.0/` 已存在
- **THEN** 系统拒绝覆盖，除非用户显式指定 `--force` 且二次确认
